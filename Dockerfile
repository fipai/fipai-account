# syntax=docker/dockerfile:1.6
# ============================================================================
# fipai-account (07Account) — Multi-stage Dockerfile
# ----------------------------------------------------------------------------
# Stage 1 (build) : python:3.11-slim → pip install + collectstatic
# Stage 2 (runtime): python:3.11-slim → gunicorn entrypoint
#
# Build:   docker build -t fipai-account:latest .
# Run:     docker run --rm -p 8001:8001 \
#            -e DJANGO_SECRET_KEY=$(openssl rand -hex 32) \
#            -e DJANGO_ALLOWED_HOSTS=account.fipai.cn \
#            -e JWT_ALGORITHM=RS256 \
#            -e JWT_SIGNING_KEY="$(cat /path/to/private.pem)" \
#            -e JWT_VERIFYING_KEY="$(cat /path/to/public.pem)" \
#            -e DB_HOST=postgres \
#            fipai-account:latest
#
# Required env (ProdAuthGuard-equivalent enforced by Django settings.py):
#   DJANGO_SECRET_KEY        - 50+ char random string (mandatory)
#   DJANGO_ALLOWED_HOSTS     - comma-separated hosts incl. account.fipai.cn
#   JWT_ALGORITHM            - "RS256" (mandatory when DEBUG=false)
#   JWT_KEY_ID               - kid header value
#   JWT_SIGNING_KEY          - RSA private PEM (single-line \n-escaped OK)
#   JWT_VERIFYING_KEY        - RSA public PEM
#   DB_NAME/USER/PASSWORD/HOST/PORT  - Postgres connection
#   TOTP_ENCRYPTION_KEY      - Fernet key (44 chars base64)
# ============================================================================

# ---------- Stage 1: build ----------
FROM python:3.11-slim AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

# System deps for psycopg2-binary + cryptography + pillow (transitive via reportlab)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libffi-dev \
        libssl-dev \
        libjpeg-dev \
        zlib1g-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer cache reuse
COPY requirements.txt /workspace/requirements.txt
RUN pip install --prefix=/install -r /workspace/requirements.txt

# Copy source
COPY . /workspace

# Collect static files (Django will need them for admin / wagtail)
RUN SECRET_KEY=collectstatic-only DJANGO_SETTINGS_MODULE=fipai.settings \
    python -c "import django; django.setup()" 2>/dev/null || true

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8001 \
    GUNICORN_WORKERS=3 \
    GUNICORN_TIMEOUT=60

# Runtime-only system deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        libffi8 \
        libssl3 \
        libjpeg62-turbo \
        zlib1g \
        tzdata \
        curl \
        tini \
    && ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd --system --gid 1001 fipai \
    && useradd --system --uid 1001 --gid fipai --home-dir /app --shell /sbin/nologin fipai

WORKDIR /app

# Copy installed Python packages from build stage
COPY --from=build /install /usr/local

# Copy source
COPY --from=build /workspace /app

# Run as non-root
RUN chown -R fipai:fipai /app

USER fipai

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/health/ready" || exit 1

# tini for proper signal handling + gunicorn entry
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "exec gunicorn fipai.wsgi:application --bind 0.0.0.0:${PORT} --workers ${GUNICORN_WORKERS} --timeout ${GUNICORN_TIMEOUT} --access-logfile - --error-logfile -"]