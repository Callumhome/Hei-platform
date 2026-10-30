# HEI Cloud Platform Architecture

## Product direction

Home Energy Intelligence (HEI) is a public, multi-tenant UK energy-data platform. The HEI cloud is the system of record for customer accounts, properties, meter connections, consent, imported readings, tariffs and energy analytics.

Home Assistant is an optional integration and presentation surface. It is not a prerequisite for cloud ingestion or the HEI web application. The platform must continue collecting and processing authorised data when a customer's Home Assistant instance is offline.

## Core principles

1. **Cloud-first, supplier-neutral:** integrations feed a common HEI data model through provider adapters.
2. **Consent before access:** address lookup is property discovery only. It does not prove account authority or grant access to meter data.
3. **One source of truth:** validated readings are stored once in HEI, with provenance and quality metadata.
4. **Optional Home Assistant:** HA may provide additional local telemetry and may consume HEI cloud sensors, but is not required.
5. **No fabricated live data:** half-hourly readings must never be presented as instantaneous power.
6. **Multi-tenant isolation:** every property, connection, consent and reading is scoped to a household and authorised membership.
7. **Secrets stay server-side:** supplier credentials and provider tokens are encrypted at rest and never returned to browsers or HA.
8. **Incremental deployment:** preserve existing authentication, households, email verification and the working read-only HA connector.

## Logical architecture

```text
HEI Web App       Home Assistant Integration       Future Mobile App
      |                       |                            |
      +-----------------------+----------------------------+
                              |
                        HEI API (FastAPI)
                              |
       +----------------------+-----------------------+
       |                      |                       |
   Identity &             Property /              Consent &
   households             meter registry          connections
       |                      |                       |
       +----------------------+-----------------------+
                              |
                     Provider adapter layer
                  /          |            \
             Octopus     Smart-meter     Other suppliers
               API      data provider     / providers
                  \          |            /
                    Ingestion workers
                            |
                Validation / normalisation
                            |
                       PostgreSQL
                            |
                  HEI energy intelligence
                            |
                 HEI web app + HA cloud sensors
```

Redis is used for background job coordination, rate limits and short-lived operational state. PostgreSQL remains the durable source of truth.

## Bounded modules

- **Identity:** registration, verification, login, refresh sessions and household membership.
- **Property registry:** country, postcode, address, address lookup reference and verified supply-point associations.
- **Meter registry:** fuel, MPAN/MPRN or provider-specific meter identifier, meter metadata and lifecycle.
- **Consent and connections:** provider, granted scopes, status, timestamps, expiry, revocation and encrypted credential references.
- **Provider adapters:** supplier- or data-provider-specific authentication, property/meter discovery and reading retrieval.
- **Ingestion:** scheduled sync, pagination, idempotency, retries, validation and provenance.
- **Energy model:** normalised interval consumption, export, gas, generation, tariffs and optional instantaneous power.
- **Intelligence:** costs, trends, forecasts and later optimisation.
- **Home Assistant:** optional local telemetry input and cloud-to-HA sensor output.

## Data-access constraints

A postcode or address can locate a property, but cannot authorise access to a customer's consumption data. HEI must use a legitimate provider route and an explicit customer authorisation process. Provider onboarding, data-controller/processor responsibilities, permitted purposes, retention and UK GDPR obligations must be reviewed before public production launch.

The connector interface must support different access models. Some providers may use customer API keys; others may use an OAuth-style redirect/consent flow; a managed smart-meter data provider may require a commercial relationship and separate onboarding.

Do not assume that a proposed UK smart-data repository or consent service is already generally available as a production integration. Provider availability and eligibility must be verified before implementation.

## Standard reading semantics

Every observation must carry:

- household and meter identifiers;
- source/provider and provider record reference where available;
- measurement type and direction;
- numeric value and explicit unit;
- interval start/end or observation timestamp;
- import timestamp;
- quality/validation status.

Use separate measurement types for interval energy (kWh) and instantaneous power (W). Keep import and export distinct. Gas readings must retain their source unit and conversion metadata. Store UTC timestamps and render using the household timezone.

## Security and privacy baseline

- Enforce household membership and role checks on every household-scoped operation.
- Encrypt provider credentials with a managed key strategy; keep encryption keys outside source control and database backups.
- Use short-lived access tokens and revocable refresh sessions.
- Never log authorisation headers, API keys, meter credentials or full consent payloads.
- Keep provider callbacks state-bound, replay-resistant and strictly validated.
- Apply rate limits to discovery, authorisation and sync endpoints.
- Support consent withdrawal, provider disconnection, data export and deletion workflows.
- Maintain audit events for connection, consent, access and deletion actions.
- Avoid exposing full MPAN/MPRN values unnecessarily in the UI and logs.

## Existing implementation to preserve

The repository already has FastAPI, SQLAlchemy, Alembic, PostgreSQL, Redis, household membership, energy accounts, meters, tariffs, interval electricity readings and an encrypted read-only Home Assistant connection. Extend these foundations through migrations; do not replace the working authentication or deployment stack.

## Delivery strategy

Build in independently testable stages:

1. Architecture and domain contracts.
2. Property and meter registry, consent and connection lifecycle.
3. Provider adapter framework and deterministic ingestion pipeline.
4. First provider connector (Octopus API) with historical readings and tariffs.
5. Authorised smart-meter data-provider integration and broader UK discovery.
6. HEI cloud API and Home Assistant sensor output.
7. Energy intelligence, additional fuels, solar, batteries and heat pumps.
8. Production hardening, privacy review, operations and public release.

Each stage must include migrations, tests, API documentation and a deploy/rollback note. Do not enable public meter-data onboarding until the access provider and consent route are contractually and technically confirmed.
