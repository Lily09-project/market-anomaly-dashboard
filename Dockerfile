# Stage 1: fetch and validate real public market data for the production snapshot.
# Python stays on 3.12 to match CI, Pages and .python-version (dependabot ignores minor/major bumps).
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS data
ENV PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements-runtime.lock.txt ./
RUN python -m pip install --no-cache-dir "pip>=26.2" \
    && python -m pip install --no-cache-dir -r requirements-runtime.lock.txt
COPY config.yaml run_all.py ./
COPY src ./src
RUN python run_all.py --mode api --require-api

# Stage 2: build the static site.
FROM node:22-slim@sha256:4b150b48b4116e2a22f2c39cc27025fbf4f153e2078fd3b14d159fdb5c7279da AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web ./
COPY --from=data /app/web/public/data ./public/data
RUN npm run build && npm run size

# Stage 3: serve it from an unprivileged nginx.
FROM nginx/nginx-unprivileged:1.31.8-alpine@sha256:16de44aff58d6a3906f4eb1499d930378b7f0fa96fdebc7d10962d2b2a4e794b
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=web /app/web/dist /usr/share/nginx/html
USER 101
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
