# HEI Build Stages

This roadmap is the delivery contract for the public, cloud-hosted HEI platform. Complete and verify one stage before moving to the next. Preserve the existing production deployment and working user journeys throughout.

## Stage 1 — Cloud platform architecture (current)

**Outcome:** a documented, agreed architecture and stable domain boundaries.

- [x] Define cloud-first, multi-tenant product direction.
- [x] Define Home Assistant as optional input/output, not the platform's system of record.
- [x] Define provider adapter boundaries and consent requirements.
- [x] Define standard measurement semantics and security baseline.
- [ ] Review implementation against this architecture and record any schema gaps.

**Exit criteria:** architecture is documented; existing implementation and migration chain have been inspected; next schema changes are specified before coding.

## Stage 2 — Property, meter and consent foundation

**Outcome:** a household can register a property and its supply points without depending on Home Assistant or a supplier connector.

Expected domain concepts:
- Property linked to a household, with country and address fields.
- Address lookup provider reference kept separately from the human-readable address.
- Meter point for electricity (MPAN) or gas (MPRN), fuel, supplier and status.
- Provider connection with status and encrypted credential reference.
- Consent grant with purpose, scopes, provider, granted/expiry/revocation timestamps and audit history.

Requirements:
- Do not infer that an address lookup proves control of an energy account.
- Do not expose full MPAN/MPRN values in ordinary list responses or logs.
- Enforce household owner/admin permissions for linking and disconnecting.
- Add Alembic migrations and tests for household isolation, uniqueness, lifecycle and revocation.
- Existing households, energy accounts, readings and HA connections must remain intact.

**Exit criteria:** migrations run against a copy of the existing schema; tests cover permissions and isolation; API schemas are documented.

## Stage 3 — Provider adapter and ingestion framework

**Outcome:** providers can be added without changing core energy-domain code.

- Define typed provider capability and adapter contracts.
- Define normalised reading and tariff DTOs.
- Implement sync job records, idempotency, pagination, retries and backoff.
- Validate units, timestamps, interval direction and duplicate records.
- Record provenance and provider sync cursors.
- Add fake-provider tests so ingestion can be tested without external credentials.

**Exit criteria:** a deterministic fake provider can import, retry and safely re-import data without duplicate readings.

## Stage 4 — First live connector: Octopus

**Outcome:** an eligible customer can connect an Octopus account and import available historical consumption and tariff data.

- Verify current Octopus API authentication, permissions and limits.
- Store customer API credentials encrypted server-side.
- Import meter identifiers and available consumption intervals.
- Import tariff/product information where available.
- Add incremental sync and disconnect/revoke behaviour.
- Clearly label data freshness and interval resolution.

**Exit criteria:** an authorised test account imports real data; repeated sync is idempotent; secrets never appear in logs or API responses.

## Stage 5 — UK smart-meter data access

**Outcome:** HEI supports a commercially and legally authorised route to smart-meter data across eligible UK suppliers.

- Evaluate managed smart-meter data providers and their eligibility, coverage, cost, consent flow and contractual requirements.
- Verify current status and onboarding requirements of any DCC or government smart-data route.
- Implement property/supply-point matching only through supported sources.
- Obtain explicit customer authorisation before reading data.
- Handle consent expiry and withdrawal.
- Never promise universal address-only meter discovery.

**Exit criteria:** provider agreement/access is confirmed; end-to-end consent and retrieval works for a pilot customer; privacy and security review is complete.

## Stage 6 — Home Assistant cloud integration

**Outcome:** HA users can link an HEI account and receive cloud-derived sensor entities.

- Build the custom integration with config flow and secure HEI account linking.
- Fetch only household data authorised for that HEI user.
- Create entities only for measurements actually available.
- Expose availability, last-updated and data-quality attributes.
- Keep the existing HA-to-HEI read-only connector optional and separately permissioned.

**Exit criteria:** HA integration works when the HEI cloud is reachable; HA downtime does not stop provider sync; revoked HEI sessions stop access.

## Stage 7 — Energy intelligence and additional sources

**Outcome:** HEI provides useful analysis across multiple energy sources.

- Daily/monthly/yearly summaries and cost calculations.
- Tariff-aware cost calculations with standing charges and effective dates.
- Solar generation, export and battery flows.
- Heat-pump electrical consumption separate from delivered heat.
- Forecasts with transparent assumptions and confidence.
- Source attribution and safeguards against double-counting.

**Exit criteria:** calculation tests cover daylight-saving changes, missing intervals, tariff changes, export and multiple meters.

## Stage 8 — Public production readiness

**Outcome:** safe, supportable public service.

- UK GDPR/privacy assessment, terms, retention and deletion workflows.
- Threat model, penetration/security review and dependency scanning.
- Managed encryption keys, backups and restore drills.
- Monitoring, alerting, audit and incident procedures.
- Abuse protection, quotas and provider rate-limit handling.
- Public documentation, support process and staged rollout.

**Exit criteria:** operational and legal launch checklist signed off; no test-only credentials or unverified data-access claims remain.

## Release discipline

- Work on a feature branch and open a pull request for each substantial stage.
- Run CI and inspect the actual result before declaring a stage passed.
- Do not deploy migrations to the live LXC until the stage's migration and rollback plan has been reviewed.
- Keep the currently working sign-in, email verification, household creation and HA connection available.
