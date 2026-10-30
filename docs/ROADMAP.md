# HEI roadmap

## Phase 0 — Foundation
- [x] Establish FastAPI service and project structure
- [x] Add Docker Compose development environment
- [x] Define supplier adapter contract
- [x] Add Octopus provider placeholder
- [x] Add initial Alembic migration and tenant-aware data model
- [x] Add CI test execution workflow and verify migration + backend tests pass

## Phase 1 — Secure accounts and supplier data
- [ ] Threat model and privacy review
- [x] Require expiry and issued-at claims when validating access tokens
- [x] Return conflict only for genuine duplicate-registration database constraints
- [ ] User registration, authentication, and session management hardening
- [x] Household creation, membership listing, and tenant isolation baseline
- [x] Household member roles and permission checks
- [ ] Invitation acceptance
- [x] One-time email verification with expiring hashed tokens and SMTP delivery
- [x] Household authorization on energy account, meter, tariff, and reading endpoints (baseline)
- [ ] Secure supplier credential storage and revocation
- [ ] Octopus account linking with explicit consent
- [ ] Import tariffs, meter metadata, and historical consumption
- [ ] Idempotent ingestion and audit trail
- [x] Redis-backed rate limiting for registration and login (initial fixed-window controls)
- [x] Immediate access-token revocation on logout using Redis denylisting
- [x] Rotating refresh tokens with hashed database storage and replay detection
- [x] Account-wide logout with access-token version invalidation
- [x] Account recovery with hashed one-time password reset tokens and session invalidation

## Phase 2 — Energy intelligence
- [x] Bounded, deterministic pagination for electricity readings
- [x] Timezone-aware tariff and reading interval validation
- [ ] Half-hourly consumption timeline
- [ ] Cost calculation with tariff and standing-charge support
- [ ] Import/export and solar-ready data model
- [ ] Daily, weekly, and monthly summaries
- [ ] Data quality and missing-interval detection

## Phase 3 — Client applications
- [ ] Responsive web dashboard
- [ ] Home Assistant integration
- [ ] Android application
- [ ] Notifications and user-configurable insights

## Release principles
- Privacy and security before supplier account linking.
- Never assume a single tariff structure or meter configuration.
- Preserve raw source readings and record transformations.
- Make calculations reproducible and explainable.
- Keep provider-specific code behind the provider interface.
