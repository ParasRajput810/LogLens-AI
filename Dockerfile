# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder

WORKDIR /build
RUN pip install --no-cache-dir build hatchling

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m build --wheel --outdir /dist

FROM python:3.12-slim AS runtime

ARG INSTALL_DEEP=0

LABEL org.opencontainers.image.title="LogLens AI" \
      org.opencontainers.image.description="AI-powered log anomaly detection & incident grouping: local, fast, explainable." \
      org.opencontainers.image.url="https://loglensai.com" \
      org.opencontainers.image.source="https://github.com/ParasRajput810/LogLens-AI" \
      org.opencontainers.image.documentation="https://loglensai.com/docs" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.vendor="LogLens AI"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    LOGLENS_IN_DOCKER=1 \
    XDG_CACHE_HOME=/data/.cache

RUN useradd --create-home --uid 1000 loglens

COPY --from=builder /dist/*.whl /tmp/

RUN if [ "$INSTALL_DEEP" = "1" ]; then \
        pip install --no-cache-dir "$(ls /tmp/*.whl)[deep]"; \
    else \
        pip install --no-cache-dir /tmp/*.whl; \
    fi && \
    rm -f /tmp/*.whl

RUN mkdir -p /data && chown -R loglens:loglens /data
USER loglens
WORKDIR /data
VOLUME ["/data"]

ENTRYPOINT ["loglens"]
CMD ["--help"]