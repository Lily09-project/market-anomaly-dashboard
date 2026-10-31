# Stage 1: fetch and validate real public market data for the production snapshot.
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS data
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
FROM nginx/nginx-unprivileged:1.31.8-alpine@sha256:03df07e5931f8374d440bd62243a5ce9b24719715ef6fc4c9c626a5f1dbef417
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=web /app/web/dist /usr/share/nginx/html
USER 101
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
