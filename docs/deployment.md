# Deployment

## Container contract

The production image runs as the unprivileged user `appuser` (UID 10001), listens on port `8765`, disables Streamlit telemetry and file watching, and exposes `/_stcore/health` as its health check.

```powershell
docker build -t research-trust-workbench .
docker run --rm -p 8765:8765 research-trust-workbench
```

Open `http://localhost:8765`. A healthy container returns `ok` from:

```text
http://localhost:8765/_stcore/health
```

## Public hosting requirements

- Terminate TLS at the hosting platform; do not expose an unencrypted public endpoint.
- Keep the application stateless. Do not mount uploaded snapshots or user-specific storage.
- Allow outbound HTTPS to Yahoo Finance and `openapi.twse.com.tw`.
- Apply platform-level request limits and logs without recording uploaded file contents.
- Monitor health, restart failures, and upstream error rates.
- Preserve the visible `LIVE`, `部分連線`, `DEMO`, and `離線` states; never hide a fallback behind a live label.

The checked-in `.streamlit/config.toml` remains optimized for local port `8765`. The Docker command overrides the bind address to `0.0.0.0` for container networking.
