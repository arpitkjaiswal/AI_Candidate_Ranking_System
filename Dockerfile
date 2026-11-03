# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm ci --no-audit --no-fund
COPY frontend/ ./
ENV VITE_API_BASE_URL=""
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/var/data PORT=8000 DEMO_MODE=true
WORKDIR /app
COPY requirements.lock ./requirements.lock
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.lock
COPY backend/ ./backend/
COPY src/ ./src/
COPY rank.py validate_submission.py candidate_schema.json ./
COPY --from=frontend /build/dist/ ./frontend/dist/
RUN useradd --create-home --uid 10001 app && mkdir -p /var/data && chown app:app /var/data && chmod -R a+rX /app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/health', timeout=4)"
ENTRYPOINT ["python", "-m", "backend.container_entrypoint"]
CMD ["sh", "-c", "exec python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
