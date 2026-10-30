# HEI roadmap

## Stage 0 — Existing application foundation
- [x] FastAPI, PostgreSQL, Redis, Docker Compose and CI
- [x] Account lifecycle, email verification and password recovery
- [x] Household membership and tenant isolation baseline
- [x] Optional read-only Home Assistant discovery

## Stage 1 — Cloud energy domain foundation
- [x] Define public cloud-first product boundary and customer onboarding architecture
- [x] Add property, meter-point, provider-connection, consent, generic-reading and sync-job models
- [x] Add additive Alembic migration for cloud energy domain
- [x] Document personal-data encryption, consent and provider boundaries
- [ ] Add keyed HMAC/encryption services and key-rotation strategy
- [ ] Add household-scoped property and meter-point APIs
- [ ] Add tenant-isolation and sensitive-data handling tests

## Stage 2 — Provider and consent framework
- [ ] Formalise provider capability and connector contracts
- [ ] Implement provider connection lifecycle and revocation
- [ ] Implement append-only consent event API
- [ ] Add durable background sync workers and retry policy
- [ ] Select and validate a UK authorised smart-meter data access route

## Stage 3 — First production data connector
- [ ] Implement Octopus account authorisation and API adapter
- [ ] Import half-hourly consumption history idempotently
- [ ] Import tariffs and meter metadata
- [ ] Add data-quality and sync-status views

## Stage 4 — Property and meter discovery
- [ ] Integrate UK postcode/address lookup
- [ ] Integrate authorised MPAN/MPRN discovery and verification
- [ ] Add gas and electricity supply support
- [ ] Complete consent, privacy and deletion workflows

## Stage 5 — Home Assistant cloud integration
- [ ] HEI cloud account linking flow
- [ ] Cloud-backed sensor entities and availability
- [ ] Optional local HA telemetry ingestion
- [ ] HACS packaging and documentation

## Stage 6 — Energy intelligence and public release
- [ ] Consumption, cost and tariff calculations
- [ ] Solar, export, battery and heat-pump data sources
- [ ] Forecasting and explainable insights
- [ ] Security/privacy review, operational monitoring and public onboarding
