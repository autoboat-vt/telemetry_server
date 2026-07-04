# Dockerfile for the Autoboat telemetry server.
#
# The app's create_app() locates its instance directory by scanning /home for
# a single user directory and resolving HOME_DIR/telemetry_server/src/instance.
# To preserve that behavior we create an "ubuntu" user (matching the original
# supervisor-based deployment) and lay the source out under /home/ubuntu.

FROM python:3.12-slim

# Create the ubuntu user and install runtime dependencies.
RUN useradd -m -s /bin/bash ubuntu \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /home/ubuntu/telemetry_server

# WORKDIR creates the directory owned by root; chown it so the ubuntu user
# can create the venv and write into it during the build.
RUN chown -R ubuntu:ubuntu /home/ubuntu/telemetry_server

# Copy project metadata and source.
COPY --chown=ubuntu:ubuntu pyproject.toml README.md ./
COPY --chown=ubuntu:ubuntu src/ ./src/

# Back up the default config.py. When a named volume is mounted over the
# instance directory at runtime, config.py will be hidden, so the entrypoint
# restores it from this backup on first start.
RUN mkdir -p /opt \
    && cp /home/ubuntu/telemetry_server/src/instance/config.py /opt/config.py

# Build the virtual environment and install the package as the ubuntu user.
USER ubuntu
RUN python -m venv /home/ubuntu/telemetry_server/venv \
    && /home/ubuntu/telemetry_server/venv/bin/pip install --upgrade pip \
    && /home/ubuntu/telemetry_server/venv/bin/pip install .

# Install the entrypoint script (needs root to place it in /opt, then drop back).
USER root
COPY docker/app-entrypoint.sh /opt/app-entrypoint.sh
RUN chmod +x /opt/app-entrypoint.sh

USER ubuntu

EXPOSE 8000

ENTRYPOINT ["/opt/app-entrypoint.sh"]
CMD ["/home/ubuntu/telemetry_server/venv/bin/gunicorn", "-w", "1", "--bind", "0.0.0.0:8000", "autoboat_telemetry_server:create_app()"]
