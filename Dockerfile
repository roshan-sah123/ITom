# Multi-stage production build for ITOM FastAPI Backend
FROM python:3.11-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev curl
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim AS runner
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl && rm -rf /var/lib/apt/lists/*
RUN groupadd -g 10001 itom && useradd -u 10001 -g itom -m -s /bin/bash itom
COPY --from=builder /root/.local /home/itom/.local
ENV PATH=/home/itom/.local/bin:$PATH
ENV PYTHONPATH=/app
COPY --chown=itom:itom . /app
USER itom
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 CMD curl -f http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
