from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    ConsentGrant, ElectricityReading, EnergyAccount, Meter, OctopusConnection,
    Property, SupplyPoint, SyncJob, Tariff,
)
from app.db.session import SessionLocal
from app.services.ingestion import (
    create_sync_job, ingest_reading_page, mark_sync_failed, mark_sync_started,
    mark_sync_succeeded,
)

OCTOPUS_BASE = "https://api.octopus.energy/v1/"
REQUIRED_SCOPES = {"account_details", "electricity_consumption", "tariff_data"}
PAGE_SIZE = 25_000
AUTO_SYNC_HOURS = 0.5


class OctopusSyncError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = True):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _fernet(purpose: bytes) -> Fernet:
    secret = get_settings().secret_key.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret + purpose).digest())
    return Fernet(key)


def _decrypt(value: str, purpose: bytes) -> str:
    try:
        return _fernet(purpose).decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        raise OctopusSyncError("CREDENTIAL_DECRYPTION_FAILED", "Stored Octopus credentials could not be decrypted.", False)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _client(api_key: str) -> httpx.Client:
    return httpx.Client(
        base_url=OCTOPUS_BASE,
        auth=httpx.BasicAuth(api_key, ""),
        timeout=httpx.Timeout(45.0, connect=10.0),
        follow_redirects=False,
        trust_env=False,
        headers={"Accept": "application/json", "User-Agent": "HEI/1.0"},
    )


def _safe_endpoint_label(url: str) -> str:
    """Describe the Octopus endpoint without retaining account or meter identifiers."""
    parts = urlsplit(url)
    segments = [segment for segment in parts.path.split("/") if segment]
    for index, segment in enumerate(segments[:-1]):
        if segment in {"accounts", "electricity-meter-points", "gas-meter-points", "meters"}:
            segments[index + 1] = "[redacted]"
    return "/" + "/".join(segments)


def _safe_provider_detail(response: httpx.Response) -> str:
    """Extract a short provider explanation while removing long numeric identifiers."""
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("message") or payload.get("error")
    else:
        detail = None
    if not isinstance(detail, str) or not detail.strip():
        detail = response.reason_phrase or "No provider explanation supplied"
    detail = re.sub(r"\s+", " ", detail).strip()
    # Do not persist MPANs, meter serials, account numbers, or other long numeric IDs.
    detail = re.sub(r"\b\d{8,}\b", "[redacted]", detail)
    return detail[:220]


def _get_json(client: httpx.Client, url: str, params: dict | None = None) -> dict:
    for attempt in range(4):
        try:
            response = client.get(url, params=params)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 3:
                    retry_after = response.headers.get("Retry-After")
                    delay = min(30, int(retry_after)) if retry_after and retry_after.isdigit() else 2 ** attempt
                    time.sleep(delay)
                    continue
            if response.status_code == 401:
                raise OctopusSyncError("OCTOPUS_AUTH_FAILED", "Octopus rejected the stored API key.", False)
            if response.status_code == 403:
                raise OctopusSyncError("OCTOPUS_ACCESS_DENIED", "Octopus denied access to an account or meter endpoint.", False)
            if response.status_code == 404:
                raise OctopusSyncError("OCTOPUS_RESOURCE_NOT_FOUND", "An Octopus account, meter or tariff resource was not found.", False)
            if 400 <= response.status_code < 500:
                endpoint = _safe_endpoint_label(str(response.request.url))
                detail = _safe_provider_detail(response)
                raise OctopusSyncError(
                    "OCTOPUS_BAD_REQUEST",
                    f"Octopus HTTP {response.status_code} at {endpoint}: {detail}",
                    False,
                )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise OctopusSyncError("INVALID_PROVIDER_RESPONSE", "Octopus returned an unexpected response.", True)
            return payload
        except OctopusSyncError:
            raise
        except (httpx.HTTPError, ValueError):
            if attempt == 3:
                raise OctopusSyncError("OCTOPUS_REQUEST_FAILED", "Octopus could not be reached or returned invalid data.")
            time.sleep(2 ** attempt)
    raise OctopusSyncError("OCTOPUS_REQUEST_FAILED", "Octopus request failed.")


def _pages(client: httpx.Client, path: str, params: dict | None = None):
    url = path
    query = params
    pages = 0
    while url:
        payload = _get_json(client, url, query)
        yield payload
        next_url = payload.get("next")
        if not next_url:
            break
        parsed = urlsplit(next_url)
        if parsed.scheme != "https" or parsed.hostname != "api.octopus.energy":
            raise OctopusSyncError("INVALID_PAGINATION_URL", "Octopus returned an unsafe pagination URL.", False)
        url = next_url
        query = None
        pages += 1
        if pages > 20_000:
            raise OctopusSyncError("PAGINATION_LIMIT", "Octopus pagination exceeded the safety limit.", False)


def _rows(client: httpx.Client, path: str, params: dict | None = None) -> list[dict]:
    values: list[dict] = []
    for page in _pages(client, path, params):
        results = page.get("results")
        if not isinstance(results, list):
            raise OctopusSyncError("INVALID_PROVIDER_RESPONSE", "Octopus returned an invalid paginated response.")
        values.extend(item for item in results if isinstance(item, dict))
    return values


def _consent_ok(db: Session, household_id: str) -> None:
    grant = db.scalar(select(ConsentGrant).where(
        ConsentGrant.household_id == household_id,
        ConsentGrant.provider == "octopus",
    ).order_by(ConsentGrant.created_at.desc(), ConsentGrant.id.desc()))
    if grant is None or grant.status != "granted":
        raise OctopusSyncError("CONSENT_REQUIRED", "The latest Octopus consent is not granted. Grant a current consent before importing data.", False)
    try:
        scopes = set(json.loads(grant.scopes_json))
    except (TypeError, ValueError):
        scopes = set()
    if not REQUIRED_SCOPES.issubset(scopes):
        raise OctopusSyncError("CONSENT_SCOPE_MISMATCH", "The latest Octopus consent does not include all required data permissions.", False)
    if grant.expires_at and grant.expires_at <= datetime.now(timezone.utc):
        raise OctopusSyncError("CONSENT_EXPIRED", "The latest Octopus consent has expired.", False)


def _account_record(db: Session, household_id: str, account_hash: str) -> EnergyAccount:
    item = db.scalar(select(EnergyAccount).where(
        EnergyAccount.household_id == household_id,
        EnergyAccount.provider == "octopus",
        EnergyAccount.provider_account_ref == account_hash,
    ))
    if item is None:
        item = EnergyAccount(
            household_id=household_id, provider="octopus",
            provider_account_ref=account_hash, label="Octopus Energy",
        )
        db.add(item)
        db.flush()
    return item


def _property_record(db: Session, household_id: str, raw: dict) -> Property | None:
    source_id = str(raw.get("id") or "").strip()
    address1 = str(raw.get("address_line_1") or "").strip()
    town = str(raw.get("town") or "").strip()
    postcode = str(raw.get("postcode") or "").strip().upper()
    if not source_id or not address1 or not town or not postcode:
        return None
    prop = db.scalar(select(Property).where(
        Property.household_id == household_id,
        Property.property_ref == "octopus:" + source_id,
    ))
    if prop is None:
        prop = db.scalar(select(Property).where(
            Property.household_id == household_id,
            Property.address_line_1 == address1,
            Property.postcode == postcode,
        ))
    if prop is None:
        prop = Property(
            household_id=household_id, property_ref="octopus:" + source_id,
            address_line_1=address1,
            address_line_2=str(raw.get("address_line_2") or raw.get("address_line_3") or "").strip() or None,
            town=town, county=str(raw.get("county") or "").strip() or None,
            postcode=postcode, country_code="GB", address_source="octopus",
            address_source_ref=source_id,
        )
        db.add(prop)
        db.flush()
    else:
        prop.address_source = prop.address_source or "octopus"
        prop.address_source_ref = prop.address_source_ref or source_id
    return prop


def _supply_point(db: Session, property_id: str, mpan: str) -> None:
    mpan = re.sub(r"\s+", "", mpan)
    if not mpan.isdigit() or len(mpan) not in {13, 21}:
        return
    # Keep the same deterministic key derivation used by the property API.
    secret = get_settings().secret_key.encode("utf-8")
    hash_key = base64.urlsafe_b64encode(hashlib.sha256(secret + b":hei-supply-point-hash:v1").digest())
    digest = hmac.new(hash_key, mpan.encode(), hashlib.sha256).hexdigest()
    existing = db.scalar(select(SupplyPoint).where(
        SupplyPoint.property_id == property_id,
        SupplyPoint.fuel == "electricity",
        SupplyPoint.identifier_hash == digest,
    ))
    if existing is None:
        encrypted = _fernet(b":hei-supply-point-encryption:v1").encrypt(mpan.encode()).decode()
        db.add(SupplyPoint(
            property_id=property_id, fuel="electricity",
            identifier_encrypted=encrypted, identifier_hash=digest,
            identifier_last4=mpan[-4:], supplier_name="Octopus Energy",
            status="verified",
        ))
        db.flush()


def _tariff_product_code(tariff_code: str) -> str | None:
    match = re.match(r"^E-\d+R-(.+)-[A-P]$", tariff_code)
    return match.group(1) if match else None


def _rate_value(row: dict) -> Decimal | None:
    value = row.get("value_inc_vat")
    if value is None:
        value = row.get("value_exc_vat")
    return Decimal(str(value)) if value is not None else None


def _has_valid_period(valid_from: datetime | None, valid_to: datetime | None) -> bool:
    """Return whether an agreement describes a non-empty time interval."""
    return valid_from is not None and (valid_to is None or valid_to > valid_from)


def _tariff_rate_endpoints(tariff_code: str) -> dict[str, str]:
    """Return the correct public rate feeds for single- or dual-register tariffs."""
    if tariff_code.startswith("E-2R-"):
        return {
            "day": "day-unit-rates/",
            "night": "night-unit-rates/",
        }
    return {"standard": "standard-unit-rates/"}


def _upsert_tariffs(
    db: Session, client: httpx.Client, meter: Meter, agreement: dict,
    cache: dict[str, tuple[dict[str, list[dict]], list[dict], str | None]],
) -> int:
    tariff_code = str(agreement.get("tariff_code") or "").strip()
    product_code = _tariff_product_code(tariff_code)
    valid_from = _parse_dt(agreement.get("valid_from"))
    valid_to = _parse_dt(agreement.get("valid_to"))
    if not tariff_code or not product_code or not _has_valid_period(valid_from, valid_to):
        return 0
    if tariff_code not in cache:
        prefix = f"products/{quote(product_code, safe='')}/electricity-tariffs/{quote(tariff_code, safe='')}/"
        params = {"period_from": _iso(valid_from), "page_size": 5000}
        if valid_to:
            params["period_to"] = _iso(valid_to)
        elif datetime.now(timezone.utc) > valid_from:
            params["period_to"] = _iso(datetime.now(timezone.utc))
        rate_rows: dict[str, list[dict]] = {}
        for rate_type, endpoint in _tariff_rate_endpoints(tariff_code).items():
            try:
                rate_rows[rate_type] = _rows(client, prefix + endpoint, params)
            except OctopusSyncError as exc:
                if exc.code in {"OCTOPUS_RESOURCE_NOT_FOUND", "OCTOPUS_ACCESS_DENIED"}:
                    rate_rows[rate_type] = []
                else:
                    raise
        try:
            standing = _rows(client, prefix + "standing-charges/", params)
        except OctopusSyncError as exc:
            if exc.code in {"OCTOPUS_RESOURCE_NOT_FOUND", "OCTOPUS_ACCESS_DENIED"}:
                standing = []
            else:
                raise
        try:
            product = _get_json(client, f"products/{quote(product_code, safe='')}/")
            product_name = product.get("full_name") or product.get("display_name") or product_code
        except OctopusSyncError:
            product_name = product_code
        cache[tariff_code] = (rate_rows, standing, str(product_name))
    rate_rows, standing, product_name = cache[tariff_code]
    inserted = 0
    for rate_type, units in rate_rows.items():
        for unit in units:
            start = _parse_dt(unit.get("valid_from"))
            end = _parse_dt(unit.get("valid_to"))
            rate = _rate_value(unit)
            if not start or rate is None:
                continue
            if start < valid_from:
                start = valid_from
            if valid_to and (end is None or end > valid_to):
                end = valid_to
            charge = None
            for row in standing:
                charge_start = _parse_dt(row.get("valid_from"))
                charge_end = _parse_dt(row.get("valid_to"))
                if charge_start and charge_start <= start and (charge_end is None or start < charge_end):
                    charge = _rate_value(row)
                    break
            # Store day and night rates as separate tariff rows. Keep the
            # standing charge on the day row only so analytics counts it once.
            tariff_ref = tariff_code if rate_type == "standard" else f"{tariff_code}:{rate_type}"
            existing = db.scalar(select(Tariff).where(
                Tariff.meter_id == meter.id,
                Tariff.provider_tariff_ref == tariff_ref,
                Tariff.valid_from == start,
            ))
            values = {
                "product_code": product_code,
                "tariff_name": product_name if rate_type == "standard" else f"{product_name} ({rate_type.title()})",
                "valid_from": start,
                "valid_to": end,
                "unit_rate_p_per_kwh": rate,
                "standing_charge_p_per_day": charge if rate_type != "night" else None,
                "currency": "GBP",
            }
            if existing is None:
                db.add(Tariff(meter_id=meter.id, provider_tariff_ref=tariff_ref, **values))
            else:
                for key, value in values.items():
                    setattr(existing, key, value)
            inserted += 1
    db.flush()
    return inserted


def _import_meter_readings(
    db: Session, client: httpx.Client, meter: Meter, mpan: str, serial: str,
    is_export: bool, period_from: datetime,
) -> tuple[int, int]:
    existing_rows = db.execute(select(
        ElectricityReading.interval_start, ElectricityReading.interval_end,
    ).where(ElectricityReading.meter_id == meter.id)).all()
    known = {(row[0], row[1]) for row in existing_rows}
    path = (
        f"electricity-meter-points/{quote(mpan, safe='')}/meters/"
        f"{quote(serial, safe='')}/consumption/"
    )
    params = {
        "period_from": _iso(period_from),
        "period_to": _iso(datetime.now(timezone.utc)),
        "page_size": PAGE_SIZE,
        "order_by": "period",
    }
    inserted = duplicates = pending = 0
    for page in _pages(client, path, params):
        results = page.get("results")
        if not isinstance(results, list):
            raise OctopusSyncError("INVALID_CONSUMPTION_RESPONSE", "Octopus returned invalid consumption data.")
        for row in results:
            if not isinstance(row, dict):
                continue
            start = _parse_dt(row.get("interval_start"))
            end = _parse_dt(row.get("interval_end"))
            value = row.get("consumption")
            if not start or not end or value is None or end <= start:
                continue
            key = (start, end)
            if key in known:
                duplicates += 1
                continue
            kwh = Decimal(str(value))
            if kwh < 0:
                continue
            db.add(ElectricityReading(
                meter_id=meter.id, interval_start=start, interval_end=end,
                consumption_kwh=Decimal("0") if is_export else kwh,
                export_kwh=kwh if is_export else Decimal("0"),
                source_record_ref=start.isoformat(),
                source_provider="octopus", quality="unknown",
            ))
            known.add(key)
            inserted += 1
            pending += 1
            if pending >= 1000:
                db.commit()
                pending = 0
        db.flush()
    if pending:
        db.commit()
    return inserted, duplicates


def _sync_household(db: Session, household_id: str) -> dict:
    connection = db.scalar(select(OctopusConnection).where(
        OctopusConnection.household_id == household_id,
        OctopusConnection.is_active.is_(True),
    ))
    if connection is None:
        raise OctopusSyncError("NOT_CONNECTED", "Octopus is not connected to this household.", False)
    job = create_sync_job(db, household_id=household_id, provider="octopus", job_type="full_sync", max_attempts=5)
    mark_sync_started(db, job)
    db.commit()
    counts = {"properties": 0, "meters": 0, "tariffs": 0, "readings_inserted": 0, "readings_existing": 0}
    try:
        _consent_ok(db, household_id)
        account_number = _decrypt(connection.account_number_encrypted, b":hei-octopus-credentials:v1")
        api_key = _decrypt(connection.api_key_encrypted, b":hei-octopus-credentials:v1")
        with _client(api_key) as client:
            account = _get_json(client, f"accounts/{quote(account_number, safe='')}/")
            if not account.get("number"):
                raise OctopusSyncError("INVALID_ACCOUNT_RESPONSE", "Octopus account response was incomplete.")
            account_record = _account_record(db, household_id, connection.account_number_hash)
            property_cache: dict[str, tuple[Property, datetime]] = {}
            tariff_cache: dict[str, tuple[list[dict], list[dict], str | None]] = {}
            for raw_property in account.get("properties") or []:
                if not isinstance(raw_property, dict):
                    continue
                prop = _property_record(db, household_id, raw_property)
                if prop is None:
                    continue
                counts["properties"] += 1
                moved_in = _parse_dt(raw_property.get("moved_in_at"))
                default_from = moved_in or (datetime.now(timezone.utc) - timedelta(days=730))
                for point in raw_property.get("electricity_meter_points") or []:
                    if not isinstance(point, dict):
                        continue
                    mpan = str(point.get("mpan") or "").strip()
                    if not mpan:
                        continue
                    _supply_point(db, prop.id, mpan)
                    export = bool(point.get("is_export", False))
                    agreements = point.get("agreements") or []
                    earliest = min(
                        (_parse_dt(a.get("valid_from")) for a in agreements if isinstance(a, dict) and a.get("valid_from")),
                        default=default_from,
                    ) or default_from
                    period_from = min(default_from, earliest)
                    for raw_meter in point.get("meters") or []:
                        if not isinstance(raw_meter, dict):
                            continue
                        serial = str(raw_meter.get("serial_number") or "").strip()
                        if not serial:
                            continue
                        provider_ref = f"{mpan}:{serial}"
                        meter = db.scalar(select(Meter).where(
                            Meter.energy_account_id == account_record.id,
                            Meter.provider_meter_ref == provider_ref,
                        ))
                        if meter is None:
                            meter = Meter(
                                energy_account_id=account_record.id,
                                provider_meter_ref=provider_ref,
                                fuel="electricity",
                                meter_type="export" if export else "import",
                                is_active=True,
                            )
                            db.add(meter)
                            db.flush()
                        else:
                            meter.meter_type = "export" if export else "import"
                            meter.is_active = True
                        counts["meters"] += 1
                        for agreement in agreements:
                            if isinstance(agreement, dict):
                                counts["tariffs"] += _upsert_tariffs(db, client, meter, agreement, tariff_cache)
                        latest_reading = db.scalar(select(func.max(ElectricityReading.interval_start)).where(
                            ElectricityReading.meter_id == meter.id,
                        ))
                        # First run imports the full available history. Later
                        # refreshes overlap the last three days to catch Octopus
                        # corrections without re-downloading years of readings.
                        incremental_from = period_from
                        if latest_reading is not None:
                            latest_aware = latest_reading.replace(tzinfo=timezone.utc) if latest_reading.tzinfo is None else latest_reading.astimezone(timezone.utc)
                            incremental_from = max(period_from, latest_aware - timedelta(days=3))
                        inserted, duplicates = _import_meter_readings(
                            db, client, meter, mpan, serial, export, incremental_from,
                        )
                        counts["readings_inserted"] += inserted
                        counts["readings_existing"] += duplicates
                        db.commit()
            mark_sync_succeeded(db, job, cursor=json.dumps(counts, separators=(",", ":"))[:500])
            connection = db.scalar(select(OctopusConnection).where(OctopusConnection.id == connection.id))
            connection.verified_at = datetime.now(timezone.utc)
            db.commit()
            return counts
    except OctopusSyncError as exc:
        db.rollback()
        job = db.scalar(select(SyncJob).where(SyncJob.id == job.id))
        if job and job.status == "running":
            mark_sync_failed(db, job, error_code=exc.code, error_message=str(exc), retryable=exc.retryable)
        db.commit()
        raise
    except Exception:
        db.rollback()
        job = db.scalar(select(SyncJob).where(SyncJob.id == job.id))
        if job and job.status == "running":
            mark_sync_failed(db, job, error_code="SYNC_INTERNAL_ERROR", error_message="An unexpected error interrupted the Octopus import.")
        db.commit()
        raise


def sync_octopus_household(household_id: str) -> None:
    db = SessionLocal()
    try:
        active = db.scalar(select(SyncJob).where(
            SyncJob.household_id == household_id,
            SyncJob.provider == "octopus",
            SyncJob.job_type == "full_sync",
            SyncJob.status == "running",
        ).order_by(SyncJob.created_at.desc()))
        if active is not None:
            return
        _sync_household(db, household_id)
    except OctopusSyncError:
        # The sanitized failure is recorded on the SyncJob; never log supplier credentials or identifiers.
        return
    except Exception:
        return
    finally:
        db.close()


def sync_due_octopus_connections() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        connections = db.scalars(select(OctopusConnection).where(OctopusConnection.is_active.is_(True))).all()
        due_ids = []
        for connection in connections:
            latest = db.scalar(select(SyncJob).where(
                SyncJob.household_id == connection.household_id,
                SyncJob.provider == "octopus",
                SyncJob.job_type == "full_sync",
            ).order_by(SyncJob.created_at.desc()))
            if latest is None:
                due_ids.append(connection.household_id)
            elif latest.status == "succeeded":
                last_run = latest.finished_at or latest.created_at
                if last_run.tzinfo is None:
                    last_run = last_run.replace(tzinfo=timezone.utc)
                if last_run < now - timedelta(hours=AUTO_SYNC_HOURS):
                    due_ids.append(connection.household_id)
            elif latest.status == "retry":
                retry_at = latest.next_attempt_at
                if retry_at is None or (retry_at.replace(tzinfo=timezone.utc) if retry_at.tzinfo is None else retry_at) <= now:
                    due_ids.append(connection.household_id)
    finally:
        db.close()
    for household_id in due_ids:
        sync_octopus_household(household_id)



def octopus_energy_analytics(db: Session, household_id: str, days: int = 30) -> dict:
    """Return tariff-aware household electricity summaries for the dashboard."""
    from collections import defaultdict
    from datetime import date, time
    from zoneinfo import ZoneInfo

    from app.db.models import Household

    household = db.get(Household, household_id)
    zone = ZoneInfo(household.timezone if household else "Europe/London")
    now = datetime.now(timezone.utc)
    local_today = now.astimezone(zone).date()
    start_local = datetime.combine(local_today - timedelta(days=days - 1), time.min, tzinfo=zone)
    start_utc = start_local.astimezone(timezone.utc)

    accounts = db.scalars(select(EnergyAccount).where(
        EnergyAccount.household_id == household_id,
        EnergyAccount.provider == "octopus",
        EnergyAccount.is_active.is_(True),
    )).all()
    account_ids = [item.id for item in accounts]
    meters = db.scalars(select(Meter).where(
        Meter.energy_account_id.in_(account_ids),
        Meter.is_active.is_(True),
        Meter.fuel == "electricity",
    )).all() if account_ids else []
    meter_ids = [item.id for item in meters]
    readings = db.scalars(select(ElectricityReading).where(
        ElectricityReading.meter_id.in_(meter_ids),
        ElectricityReading.interval_start >= start_utc,
        ElectricityReading.interval_start <= now,
    ).order_by(ElectricityReading.interval_start)).all() if meter_ids else []
    tariffs = db.scalars(select(Tariff).where(Tariff.meter_id.in_(meter_ids))).all() if meter_ids else []

    tariffs_by_meter: dict[str, list[Tariff]] = defaultdict(list)
    for tariff in tariffs:
        tariffs_by_meter[tariff.meter_id].append(tariff)

    def aware(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    def active_tariffs(meter_id: str, at: datetime) -> list[Tariff]:
        at = aware(at)
        matches = []
        for item in tariffs_by_meter.get(meter_id, []):
            valid_from = aware(item.valid_from)
            valid_to = aware(item.valid_to) if item.valid_to else None
            if valid_from <= at and (valid_to is None or at < valid_to):
                matches.append(item)
        if not matches:
            return []
        latest_start = max(aware(item.valid_from) for item in matches)
        return [item for item in matches if aware(item.valid_from) == latest_start]

    daily = defaultdict(lambda: {"import_kwh": Decimal("0"), "export_kwh": Decimal("0"), "cost_gbp": Decimal("0"), "standing_charge_gbp": Decimal("0"), "export_credit_gbp": Decimal("0"), "cost_complete": True})
    meter_days: set[tuple[str, date]] = set()
    half_hourly = []
    total_import = Decimal("0")
    total_export = Decimal("0")
    total_cost = Decimal("0")
    total_export_credit = Decimal("0")
    cost_complete = True

    for reading in readings:
        start = aware(reading.interval_start)
        day = start.astimezone(zone).date()
        imported = Decimal(reading.consumption_kwh or 0)
        exported = Decimal(reading.export_kwh or 0)
        row = daily[day]
        row["import_kwh"] += imported
        row["export_kwh"] += exported
        total_import += imported
        total_export += exported
        active_rates = active_tariffs(reading.meter_id, start)
        # A dual-register Economy 7 tariff has separate day/night rates. The
        # consumption feed gives total kWh, not a register label, so do not
        # invent a rate assignment or publish a misleading estimated cost.
        dual_register = any(
            item.provider_tariff_ref and item.provider_tariff_ref.endswith((":day", ":night"))
            for item in active_rates
        )
        tariff = active_rates[0] if len(active_rates) == 1 and not dual_register else None
        unit_cost = None
        if imported > 0:
            if tariff is None or tariff.unit_rate_p_per_kwh is None:
                row["cost_complete"] = False
                cost_complete = False
            else:
                billable = imported.quantize(Decimal("0.01"), rounding=__import__("decimal").ROUND_HALF_EVEN)
                unit_cost = billable * tariff.unit_rate_p_per_kwh / Decimal("100")
                row["cost_gbp"] += unit_cost
                total_cost += unit_cost
        if exported > 0 and tariff is not None and tariff.unit_rate_p_per_kwh is not None:
            export_billable = exported.quantize(Decimal("0.01"), rounding=__import__("decimal").ROUND_HALF_EVEN)
            export_credit = export_billable * tariff.unit_rate_p_per_kwh / Decimal("100")
            row["export_credit_gbp"] += export_credit
            total_export_credit += export_credit
        half_hourly.append({
            "start": _iso(start),
            "import_kwh": float(imported),
            "export_kwh": float(exported),
            "unit_rate_p_per_kwh": float(tariff.unit_rate_p_per_kwh) if tariff and tariff.unit_rate_p_per_kwh is not None else None,
            "cost_gbp": float(unit_cost) if unit_cost is not None else None,
        })
        meter_days.add((reading.meter_id, day))

    # Apply each meter's standing charge once per local calendar day while a
    # tariff agreement was active, including days with zero consumption.
    standing_total = Decimal("0")
    for meter in meters:
        for offset in range(days):
            day = local_today - timedelta(days=offset)
            day_start = datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc)
            active = active_tariffs(meter.id, day_start)
            tariff = next((item for item in active if item.standing_charge_p_per_day is not None), None)
            if tariff is None:
                continue
            charge = tariff.standing_charge_p_per_day / Decimal("100")
            daily[day]["standing_charge_gbp"] += charge
            standing_total += charge

    daily_rows = []
    for offset in reversed(range(days)):
        day = local_today - timedelta(days=offset)
        row = daily[day]
        daily_rows.append({
            "date": day.isoformat(),
            "import_kwh": round(float(row["import_kwh"]), 3),
            "export_kwh": round(float(row["export_kwh"]), 3),
            "cost_gbp": round(float(row["cost_gbp"] + row["standing_charge_gbp"] - row["export_credit_gbp"]), 2),
            "export_credit_gbp": round(float(row["export_credit_gbp"]), 2),
            "cost_complete": bool(row["cost_complete"]),
        })

    today = daily[local_today]
    week_start = local_today - timedelta(days=6)
    week_import = sum((item["import_kwh"] for item in daily_rows if item["date"] >= week_start.isoformat()), 0.0)
    month_import = float(total_import)
    return {
        "currency": "GBP",
        "period_days": days,
        "today": {
            "import_kwh": round(float(today["import_kwh"]), 3),
            "export_kwh": round(float(today["export_kwh"]), 3),
            "cost_gbp": round(float(today["cost_gbp"] + today["standing_charge_gbp"] - today["export_credit_gbp"]), 2),
            "export_credit_gbp": round(float(today["export_credit_gbp"]), 2),
            "cost_complete": bool(today["cost_complete"]),
        },
        "last_7_days_import_kwh": round(week_import, 3),
        "period_import_kwh": round(month_import, 3),
        "period_export_kwh": round(float(total_export), 3),
        "period_energy_cost_gbp": round(float(total_cost + standing_total - total_export_credit), 2),
        "period_export_credit_gbp": round(float(total_export_credit), 2),
        "cost_complete": cost_complete,
        "daily": daily_rows,
        "half_hourly": half_hourly[-48:],
        "meter_count": len(meters),
        "reading_count": len(readings),
    }


def octopus_sync_status(db: Session, household_id: str) -> dict:
    latest = db.scalar(select(SyncJob).where(
        SyncJob.household_id == household_id,
        SyncJob.provider == "octopus",
        SyncJob.job_type == "full_sync",
    ).order_by(SyncJob.created_at.desc()))
    if latest is None:
        return {"status": "not_started", "last_synced_at": None, "error": None, "counts": None}
    counts = None
    if latest.cursor:
        try:
            counts = json.loads(latest.cursor)
        except ValueError:
            counts = None
    return {
        "status": latest.status,
        "last_synced_at": latest.finished_at or latest.started_at or latest.created_at,
        "error": latest.error_message,
        "error_code": latest.error_code,
        "attempts": latest.attempts,
        "counts": counts,
    }
