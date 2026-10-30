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
- [ ] User registration, authentication, and session management
- [x] Household creation, membership listing, and tenant isolation baseline
- [x] Household member roles and permission checks
- [ ] Invitation acceptance and account email verification
- [ ] Apply household authorization to every energy account, meter, tariff, and reading endpoint
- [ ] Secure supplier credential storage and revocation
- [ ] Octopus account linking with explicit consent
- [ ] Import tariffs, meter metadata, and historical consumption
- [ ] Idempotent ingestion and audit trail

## Phase 2 — Energy intelligence
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
