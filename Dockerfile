# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc g++ \
    && rm -rf /var/lib/apt/lists/*

ARG INSTALL_DEEP=0

ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip build hatchling

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# Build the wheel, then install it (plus the optional deep extra) INTO the venv.
RUN python -m build --wheel --outdir /dist && \
    if [ "$INSTALL_DEEP" = "1" ]; then \
        pip install --no-cache-dir "$(ls /dist/*.whl)[deep]"; \
    else \
        pip install --no-cache-dir /dist/*.whl; \
    fi


FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="LogLens AI" \
      org.opencontainers.image.description="AI-powered log anomaly detection & incident grouping: local, fast, explainable." \
      org.opencontainers.image.url="https://loglensai.com" \
      org.opencontainers.image.source="https://github.com/ParasRajput810/LogLens-AI" \
      org.opencontainers.image.documentation="https://loglensai.com/docs" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.vendor="LogLens AI"

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    LOGLENS_IN_DOCKER=1 \
    XDG_CACHE_HOME=/data/.cache

COPY --from=builder /opt/venv /opt/venv

RUN useradd --create-home --uid 1000 loglens && \
    mkdir -p /data && chown -R loglens:loglens /data

USER loglens
WORKDIR /data
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --retries=2 \
    CMD ["loglens", "version"]

ENTRYPOINT ["loglens"]
CMD ["--help"]