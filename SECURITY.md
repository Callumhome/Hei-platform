# Security policy

HEI is an early-stage project. Do not connect real supplier accounts or upload personal energy data to this scaffold.

## Reporting
Do not publish credentials, account identifiers, meter identifiers, or personal data in GitHub issues. Report suspected vulnerabilities privately to the repository maintainer.

## Development requirements
- Keep secrets in environment variables or a dedicated secret manager; never commit them.
- Rotate any secret that is accidentally committed.
- Require authentication and per-user authorization before exposing account, meter, tariff, or reading data.
- Enforce tenant isolation in database queries and tests.
- Encrypt supplier credentials at rest and support revocation.
- Minimize personal data collection and define retention/deletion behavior.
- Redact credentials and personal identifiers from logs and error reports.
- Use HTTPS in deployed environments.
- Treat supplier API responses as untrusted input.

The current scaffold does not yet implement authentication, tenant isolation, supplier credential storage, or supplier API access. It is not suitable for production deployment.
