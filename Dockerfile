# ATHAR single-service image: the FastAPI backend also serves the built single-page app (same origin, no CORS needed).
# Build:  docker build -t athar .
# Run:    docker run --rm -p 8000:8000 -e ATHAR_ADMIN_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')" athar
# The default mode is the public READ-ONLY demo (ATHAR_MODE=demo). See docs/DEPLOYMENT.md.

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Empty API base => the browser calls /api on the same origin that served the page.
ENV VITE_API_BASE=""
RUN npm run build

FROM python:3.12-slim AS run
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    ATHAR_MODE=demo ATHAR_TRUST_PROXY=1 ATHAR_STATIC_DIR=/app/static ATHAR_DB=/data/athar.db
WORKDIR /app
COPY backend/requirements.prod.txt ./
RUN pip install --no-cache-dir -r requirements.prod.txt \
 && useradd --system --uid 10001 --home /app athar \
 && mkdir -p /data && chown athar /data
COPY backend/app ./app
COPY --from=web /web/dist ./static
USER athar
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/api/ready' % os.environ.get('PORT','8000'), timeout=4)"
# PORT is provided by most hosting platforms; 8000 otherwise.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-server-header"]
