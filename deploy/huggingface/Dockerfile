# ATHAR on a Hugging Face Docker Space: one container serves the built single-page app and the API on one origin (no CORS).
# This file is copied to the ROOT of the Space repository by scripts/make_hf_space.py (Spaces require a root Dockerfile).
# Public READ-ONLY demo (ATHAR_MODE=demo): no admin token is configured, so nobody can write; simulations are not stored.

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Empty API base => the browser calls /api on the origin that served the page.
ENV VITE_API_BASE=""
RUN npm run build

FROM python:3.12-slim
# Spaces run the container as user 1000 and route traffic to app_port (7860, see README.md).
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=7860 \
    ATHAR_MODE=demo ATHAR_STATIC_DIR=/home/user/app/static ATHAR_DB=/tmp/athar.db ATHAR_HSTS=1 \
    ATHAR_FRAME_ANCESTORS="https://huggingface.co https://*.hf.space" \
    ATHAR_RATE_READ=3000 ATHAR_RATE_WRITE=600 ATHAR_RATE_EXPLAIN=300
# The traffic reaches the container through the platform's proxies, whose chain length is not documented here, so forwarded
# headers are NOT trusted (ATHAR_TRUST_PROXY unset) and the per-client rate limits are therefore shared; they are raised above.
WORKDIR /home/user/app
COPY --chown=user backend/requirements.prod.txt ./
RUN pip install --no-cache-dir --user -r requirements.prod.txt
COPY --chown=user backend/app ./app
COPY --chown=user --from=web /web/dist ./static
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:7860/api/ready', timeout=4)"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --no-server-header"]
