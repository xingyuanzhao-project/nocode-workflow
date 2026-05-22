FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install root and server dependencies.
COPY requirements.txt /app/requirements.txt
COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /app/requirements.txt && \
    pip install -r /app/server/requirements.txt

# Copy application source so the image is runnable on its own (for
# example in a Render deploy without bind mounts). Local development
# overlays ./src, ./server, ./config, and ./.env via docker-compose
# bind mounts so edits on the host show up live in the container.
COPY src /app/src
COPY server /app/server
COPY config /app/config

ENV PYTHONPATH=/app

# Expose the FastAPI port for the web service. The worker service
# does not listen on a port; publishing is a no-op for it and harmless.
EXPOSE 8000

# No default CMD: docker-compose (dev) and Render service definitions
# (prod) each specify the command, so one image serves both the web
# (uvicorn) and the worker (celery) roles.
