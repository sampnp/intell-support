FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FASTEMBED_CACHE_PATH=/opt/fastembed

WORKDIR /app

# Dependencies first so code changes don't invalidate this layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image (outside /app, which is bind-mounted in dev).
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('${EMBEDDING_MODEL}', cache_dir='/opt/fastembed')"

COPY . .

RUN useradd --create-home --uid 1000 app && chown -R app:app /app /opt/fastembed
USER app

EXPOSE 8000

# Request lines are logged by RequestIdMiddleware, so uvicorn's access log is off.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
