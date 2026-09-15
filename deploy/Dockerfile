FROM python:3.13.9-slim-bookworm

ARG RELEASE_REVISION=unknown
ARG PYPI_INDEX_URL=https://pypi.org/simple
LABEL org.opencontainers.image.title="AI Learning Studio" \
      org.opencontainers.image.source="https://github.com/LuxUmbra697/ai-knowledge-learning-miniapp" \
      org.opencontainers.image.revision=$RELEASE_REVISION

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ANONYMIZED_TELEMETRY=false \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MALLOC_ARENA_MAX=2 \
    AI_LEARN_ENV_FILE="" \
    H5_STATIC_DIR=/app/h5 \
    CHROMA_PERSIST_DIR=/data/chroma \
    KB_UPLOAD_DIR=/data/uploads

WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --index-url "$PYPI_INDEX_URL" uv==0.12.5 && \
    UV_CONCURRENT_DOWNLOADS=2 UV_CONCURRENT_INSTALLS=1 uv pip install --system --no-cache --index-url "$PYPI_INDEX_URL" --require-hashes -r /app/requirements.txt && \
    uv pip check --system && \
    groupadd --gid 10001 studio && useradd --uid 10001 --gid studio --no-create-home studio && \
    mkdir /data && chown 10001:10001 /data
COPY backend/app /app/app
COPY frontend/dist/h5 /app/h5
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/ready', timeout=3)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log", "--no-proxy-headers"]
