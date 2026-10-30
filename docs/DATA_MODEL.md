# HEI initial data model

This first relational model is designed around a household tenant, not a single global user.

## Entities

- **User** — an individual login identity. Authentication credentials are intentionally not implemented in this milestone.
- **Household** — the tenant boundary for a home and its energy data.
- **HouseholdMembership** — associates users with households and records a role.
- **EnergyAccount** — a supplier account reference linked to one household.
- **Meter** — an electricity meter belonging to a supplier account.
- **Tariff** — a time-bounded tariff record for a meter, including standing charge and a simple unit rate.
- **ElectricityReading** — an interval reading with kWh consumption and UTC-capable timestamps.

## Important design decisions

- IDs are UUID strings so records can be created independently by different clients.
- All supplier and meter data is reached through a household-owned energy account.
- Readings have a uniqueness constraint on meter and interval to support safe repeat imports.
- Tariffs are time-bounded because rates can change. A later iteration will add multiple time-of-use rates and export rates.
- Currency is explicit; monetary rates are stored as decimal values, not floating point.
- Supplier secrets, passwords, MPANs, addresses, and payment details are not stored in this initial schema.

## Before real users or supplier linking

This model is not by itself tenant security. Every query must be authorized against the active user's household membership. Add authentication, database migrations, tenant-isolation tests, encrypted credential storage, audit events, and data deletion workflows before connecting live supplier accounts.
