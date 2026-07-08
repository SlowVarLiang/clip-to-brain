# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only deps (no NVIDIA CUDA wheels)
COPY video-parser/requirements.txt /tmp/vp-reqs.txt
RUN grep -v nvidia /tmp/vp-reqs.txt > /tmp/vp-cpu.txt \
    && pip install --no-cache-dir -r /tmp/vp-cpu.txt

COPY content-archiver-skill/requirements.txt /tmp/ca-reqs.txt
RUN pip install --no-cache-dir -r /tmp/ca-reqs.txt

COPY . /app/

ENV PYTHONUNBUFFERED=1
ENV SERVE_WEB_UI=false
ENV DOCS_ENABLED=false
ENV API_HOST=0.0.0.0
ENV API_PORT=8765
ENV WHISPER_MODEL=small
ENV INGEST_CONFIG=/app/content-archiver-skill/config.json

WORKDIR /app/video-parser
EXPOSE 8765

RUN chmod +x /app/clip-to-brain/docker-entrypoint.sh
ENTRYPOINT ["/app/clip-to-brain/docker-entrypoint.sh"]
