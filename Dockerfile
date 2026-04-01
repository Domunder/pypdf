# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Build-time system deps needed to compile some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

LABEL org.opencontainers.image.title="openwebui-loaders" \
    org.opencontainers.image.description="OpenWebUI external document loaders" \
    org.opencontainers.image.version="2.0.0"

# Runtime system libraries required by loaders:
#   libmagic1       → python-magic (MIME sniffing used by unstructured)
#   libxml2 / libxslt → XML/HTML parsing (BSHTMLLoader, UnstructuredXMLLoader)
#   libreoffice     → ODT support via unstructured (remove if you don't need ODT)
#   pandoc          → RST conversion via unstructured (remove if you don't need RST)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# OpenShift runs containers with a random UID in group 0 (root group).
ENV APP_HOME=/app \
    APP_USER=appuser \
    APP_UID=1001

RUN groupadd -g 0 -o appgroup 2>/dev/null || true && \
    useradd -u ${APP_UID} -g 0 -M -d ${APP_HOME} -s /sbin/nologin ${APP_USER}

WORKDIR ${APP_HOME}

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY app.py .

# Writable temp dir — root-group accessible for OpenShift arbitrary UIDs
RUN mkdir -p /tmp/doc-work && \
    chown -R ${APP_UID}:0 ${APP_HOME} /tmp/doc-work && \
    chmod -R g=u ${APP_HOME} /tmp/doc-work

USER ${APP_UID}

EXPOSE 8080

# Environment variable defaults — all overridable at deploy time
ENV PORT=5001 \
    HOST=0.0.0.0

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5001", "--log-level", "info", "--no-access-log"]