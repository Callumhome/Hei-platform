from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")


class EnergyAccountCreate(BaseModel):
    provider: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9_-]+$")
    provider_account_ref: str = Field(min_length=1, max_length=160)
    label: str | None = Field(default=None, max_length=120)


class EnergyAccountResponse(BaseModel):
    id: str
    household_id: str
    provider: str
    provider_account_ref: str
    label: str | None
    is_active: bool


class MeterCreate(BaseModel):
    provider_meter_ref: str = Field(min_length=1, max_length=160)
    fuel: Literal["electricity", "gas"] = "electricity"
    meter_type: str | None = Field(default=None, max_length=32)


class MeterResponse(BaseModel):
    id: str
    energy_account_id: str
    provider_meter_ref: str
    fuel: str
    meter_type: str | None
    is_active: bool


class TariffCreate(BaseModel):
    provider_tariff_ref: str | None = Field(default=None, max_length=200)
    product_code: str | None = Field(default=None, max_length=80)
    tariff_name: str | None = Field(default=None, max_length=160)
    valid_from: datetime
    valid_to: datetime | None = None
    standing_charge_p_per_day: Decimal | None = Field(default=None, ge=0)
    unit_rate_p_per_kwh: Decimal | None = Field(default=None, ge=0)
    currency: Literal["GBP"] = "GBP"

    @model_validator(mode="after")
    def validate_validity(self):
        _require_timezone(self.valid_from, "valid_from")
        if self.valid_to is not None:
            _require_timezone(self.valid_to, "valid_to")
            if self.valid_to <= self.valid_from:
                raise ValueError("valid_to must be later than valid_from")
        return self


class TariffResponse(BaseModel):
    id: str
    meter_id: str
    provider_tariff_ref: str | None
    product_code: str | None
    tariff_name: str | None
    valid_from: datetime
    valid_to: datetime | None
    standing_charge_p_per_day: Decimal | None
    unit_rate_p_per_kwh: Decimal | None
    currency: str


class ElectricityReadingCreate(BaseModel):
    interval_start: datetime
    interval_end: datetime
    consumption_kwh: Decimal = Field(ge=0, max_digits=14, decimal_places=6)
    source_record_ref: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_interval(self):
        _require_timezone(self.interval_start, "interval_start")
        _require_timezone(self.interval_end, "interval_end")
        if self.interval_end <= self.interval_start:
            raise ValueError("interval_end must be later than interval_start")
        return self


class ElectricityReadingResponse(BaseModel):
    id: str
    meter_id: str
    interval_start: datetime
    interval_end: datetime
    consumption_kwh: Decimal
    source_record_ref: str | None
    imported_at: datetime | None
