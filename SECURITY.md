# Security Policy

## Reporting a vulnerability

Do not open a public issue containing credentials, tokens, personal data, or exploit details.
Use GitHub's private vulnerability reporting feature when it is available for this repository. Otherwise, contact the repository owner privately and include only the minimum information needed to reproduce the issue.

## Secrets and local data

Never commit `.env`, API credentials, raw or processed market data, local caches, model artifacts, or generated reports. The repository `.gitignore` excludes these paths. Use `.env.example` only for empty variable names and documentation.

## Supported version

Security fixes are applied to the current `main` branch.
