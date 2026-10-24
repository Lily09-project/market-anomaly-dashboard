# Security Policy

## Reporting a vulnerability

Do not open a public issue containing credentials, tokens, personal data, or exploit details.
Use GitHub's private vulnerability reporting feature when it is available for this repository. Otherwise, contact the repository owner privately and include only the minimum information needed to reproduce the issue.

## Secrets and local data

Never commit `.env`, API credentials, raw or processed market data, local caches, model artifacts, or generated reports. The repository `.gitignore` excludes these paths. Use `.env.example` only for empty variable names and documentation.

## Supported version

Security fixes are applied to the current `main` branch.

## Application hardening

The site is static: it makes no third-party requests at runtime, ships a strict Content-Security-Policy with no inline scripts, and the container serves it from an unprivileged nginx (UID 101) with `nosniff`, `frame-ancestors 'none'` and a no-referrer policy.

Research snapshots uploaded for comparison are treated as untrusted input and never leave the browser. Files over 64 KB are rejected before they are read; the JSON must be an object of the expected kind and version, every field is type-checked (the symbol must match `^[A-Za-z0-9._-]{1,16}$`), and the SHA-256 fingerprint over the canonical JSON must match, otherwise the file is rejected with a stated reason. Uploaded text is only ever rendered as text.

The optional API mode (`--mode api`) requires HTTPS, rejects redirects, validates the response origin, bounds timeouts and response size, and redacts credential-like query values from error messages. CSV exports neutralise spreadsheet formulas.

The project has no authentication layer. A public deployment beyond static hosting must add TLS, edge rate limiting and a logging policy that excludes credential-bearing query strings.
