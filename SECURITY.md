# Security Policy

## Reporting a vulnerability

Do not open a public issue containing credentials, tokens, personal data, or exploit details.
Use GitHub's private vulnerability reporting feature when it is available for this repository. Otherwise, contact the repository owner privately and include only the minimum information needed to reproduce the issue.

## Secrets and local data

Never commit `.env`, API credentials, raw or processed market data, local caches, model artifacts, or generated reports. The repository `.gitignore` excludes these paths. Use `.env.example` only for empty variable names and documentation.

## Supported version

Security fixes are applied to the current `main` branch.

## Application hardening

The snapshot comparison endpoint treats uploaded JSON as untrusted input. It enforces a 2 MiB file limit, rejects excessive nesting, duplicate keys, non-standard numeric constants, invalid schema, cross-symbol comparisons, and failed SHA-256 integrity checks. External market／FX／TWSE reads are timeout-bounded and response-size limited; error messages redact credential-like URL query values. External numeric/date normalization also rejects non-scalar values, malformed dates, oversized numeric text, invalid numeric syntax, and non-finite results. Dynamic dashboard/export HTML escapes external asset and source text before rendering.

The project has no authentication or authorization layer. Public deployments must add TLS, edge rate limiting, platform firewall controls, health monitoring, and a logging policy that excludes uploaded content and credential-bearing query strings.
