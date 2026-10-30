# HEI cloud platform architecture

## Product boundary

HEI is a public, multi-tenant UK energy data platform. The cloud platform is the system of record for customer accounts, properties, supply points, provider consent, imported readings and energy intelligence. Home Assistant is an optional client/edge integration: it can contribute local telemetry where the customer enables it, and it can consume HEI cloud readings as sensors. HEI must continue collecting and serving cloud-connected data when a customer's Home Assistant instance is offline.

## Customer onboarding

1. Install the HEI Home Assistant integration or create an account in the HEI web app.
2. Authenticate/link the Home Assistant installation to the customer's HEI account using a short-lived, single-use linking flow (planned; never ask customers to paste long-lived cloud passwords into HA YAML).
3. Create or select a household.
4. Search for a property by postcode and select a verified address using an address-data provider.
5. Resolve electricity and gas supply points through an authorised meter-data provider or supplier connection. Address selection alone is not proof of account ownership and must never grant access to readings.
6. Present the provider's consent/authorisation flow and record provider, scopes, policy version, actor and timestamps.
7. Import available history, then schedule incremental synchronisation.
8. Expose only available, correctly-labelled measurements in the web app and optional HA entities.

## Cloud services

- FastAPI: authentication, household/property/meter APIs, consent and provider connection APIs.
- PostgreSQL: tenant-owned records, supply point metadata, standardised readings and audit/sync history.
- Redis and background workers: rate limits, scheduled ingestion, retries and provider throttling.
- Provider adapters: supplier- and data-access-provider-specific implementations behind a stable contract.
- Web application: account management, property onboarding, connections, dashboard and data-quality explanations.
- Home Assistant integration: customer-facing cloud account link and read-only sensor entities; optional local data ingestion is a separate consented capability.

## Data protection rules

- Address and supply-point identifiers are personal data. Store address and MPAN/MPRN values encrypted; use keyed HMAC fingerprints for exact matching and deduplication. Do not use plain, unsalted hashes for low-entropy identifiers.
- Provider credentials/tokens must be encrypted using a dedicated key-management design, with key rotation and no secrets in logs. The encrypted credential column is a storage slot only; no provider credential may be accepted until encryption, authorisation, revocation and tests are implemented.
- Consent is explicit, purpose/scope-specific and revocable. Keep an append-only consent event history.
- Every query is scoped to a household membership. Never trust a household, property, meter or connection ID supplied by a client without checking ownership.
- Store raw provider values and source references; calculations belong in derived records/services and must be reproducible.
- Distinguish interval energy (kWh) from instantaneous power (W/kW), import from export, and consumption from generation. Never manufacture live demand from half-hourly data.
- Provider access is read-only. Address lookup is not meter-data authorisation.
- Provide data export/deletion, retention limits, audit events and a documented incident response before public onboarding.

## Data model introduced in Stage 1

- Property: encrypted address, keyed postcode fingerprint, country and address-provider reference.
- MeterPoint: fuel, encrypted MPAN/MPRN and meter serial, keyed identifier fingerprint, smart-meter status and source.
- ProviderConnection: household/provider association, connection status and encrypted-credential storage slot.
- ConsentRecord: append-only grant/revoke event with purpose, scopes, policy version and actor.
- EnergyDataReading: provider-neutral interval measurement with unit, direction, quality and source record identity.
- SyncJob: durable import attempt and aggregate counts; never stores raw payloads or secrets.

The models are intentionally introduced before public APIs and supplier authorisation. The next stage must add encryption/HMAC services, household-scoped property and meter APIs, consent lifecycle endpoints, and tests before any personal property or meter identifiers are accepted.

## Planned provider layers

1. Address provider: postcode/address search only; no energy data access.
2. Meter-data access provider: property-to-MPAN/MPRN resolution and consented meter readings, subject to its legal/contractual route.
3. Supplier provider: account-specific tariff, billing and consumption data where supported.
4. Local telemetry provider: Home Assistant, inverter APIs, MQTT/CAD and future CT monitors.

Provider availability and data granularity must be explicit in capability metadata. A provider returning half-hourly readings cannot satisfy a live-power sensor.
