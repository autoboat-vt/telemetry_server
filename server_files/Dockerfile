FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Keep this path to match INSTANCE_DIR in src/autoboat_telemetry_server/__init__.py.
WORKDIR /home/ubuntu/telemetry_server

RUN useradd -m -d /home/ubuntu ubuntu

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install . \
    && mkdir -p /home/ubuntu/telemetry_server/src/instance \
    && chown -R ubuntu:ubuntu /home/ubuntu

USER ubuntu

EXPOSE 8000

CMD ["gunicorn", "-w", "1", "--bind", "0.0.0.0:8000", "autoboat_telemetry_server:create_app()"]

