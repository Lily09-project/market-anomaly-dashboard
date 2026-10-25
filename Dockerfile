# Stage 1: generate the reproducible analysis.
FROM python:3.12-slim AS data
ENV PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements-runtime.lock.txt ./
RUN python -m pip install --no-cache-dir "pip>=26.2" \
    && python -m pip install --no-cache-dir -r requirements-runtime.lock.txt
COPY config.yaml run_all.py ./
COPY src ./src
RUN python run_all.py --mode sample

# Stage 2: build the static site.
FROM node:22-slim AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web ./
COPY --from=data /app/web/public/data ./public/data
RUN npm run build && npm run size

# Stage 3: serve it from an unprivileged nginx.
FROM nginxinc/nginx-unprivileged:1.31-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=web /app/web/dist /usr/share/nginx/html
USER 101
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
