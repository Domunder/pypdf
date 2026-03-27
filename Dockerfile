# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build deps and wheel dependencies into a prefix directory
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

LABEL org.opencontainers.image.title="pypdf-extractor" \
      org.opencontainers.image.description="OpenWebUI external document extraction engine (PyPDFLoader / single mode)" \
      org.opencontainers.image.version="1.0.0"

# OpenShift runs containers with a random UID in group 0 (root group).
# We create a dedicated non-root user but ensure group-0 ownership so
# the random-UID OpenShift assigns can still write to needed paths.
ENV APP_HOME=/app \
    APP_USER=appuser \
    APP_UID=1001

RUN groupadd -g 0 -o appgroup 2>/dev/null || true && \
    useradd -u ${APP_UID} -g 0 -M -d ${APP_HOME} -s /sbin/nologin ${APP_USER}

WORKDIR ${APP_HOME}

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY app.py .

# Temp dir used by the service for PDF processing — must be writable
# by the root group (for OpenShift's arbitrary UID policy).
RUN mkdir -p /tmp/pypdf-work && \
    chown -R ${APP_UID}:0 ${APP_HOME} /tmp/pypdf-work && \
    chmod -R g=u ${APP_HOME} /tmp/pypdf-work

USER ${APP_UID}

# OpenShift convention: use port 8080 (no privileges needed)
EXPOSE 8080

# Environment variable defaults — all overridable at deploy time
ENV PYPDF_MODE=single \
    PAGES_DELIMITER="\n" \
    EXTRACT_IMAGES=false \
    MAX_FILE_SIZE_MB=20 \
    MAX_TASK_TIMEOUT=60 \
    API_KEY="" \
    PORT=8080 \
    HOST=0.0.0.0 \
    WORKERS=2

# Use shell form so the PORT env-var is expanded correctly
CMD uvicorn app:app \
        --host "$HOST" \
        --port "$PORT" \
        --workers "$WORKERS" \
        --log-level info \
        --no-access-log
