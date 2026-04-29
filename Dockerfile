FROM python:3.12

ARG USERNAME=ubuntu
ARG USER_UID=1000
ARG USER_GID=$USER_UID

WORKDIR /home/${USERNAME}/telemetry_server

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME

RUN apt update && apt install nginx supervisor git -y && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

COPY . /home/${USERNAME}/telemetry_server/

COPY server_files/supervisor_autoboat.conf /etc/supervisor/conf.d/

RUN cp /home/${USERNAME}/telemetry_server/server_files/nginx_autoboat_nossl.conf /etc/nginx/sites-available/ \
    && ln -sf /etc/nginx/sites-available/nginx_autoboat_nossl.conf /etc/nginx/sites-enabled/nginx_autoboat.conf \
    && nginx -t

RUN python3 -m venv /home/${USERNAME}/telemetry_server/venv \
    && /home/${USERNAME}/telemetry_server/venv/bin/pip install --upgrade pip \
    && /home/${USERNAME}/telemetry_server/venv/bin/pip install /home/${USERNAME}/telemetry_server

RUN git clone https://github.com/autoboat-vt/telemetry_server /home/${USERNAME}/telemetry_server_testing \
    && cd /home/${USERNAME}/telemetry_server_testing && git checkout testing \
    && python3 -m venv /home/${USERNAME}/telemetry_server_testing/venv \
    && /home/${USERNAME}/telemetry_server_testing/venv/bin/pip install --upgrade pip \
    && /home/${USERNAME}/telemetry_server_testing/venv/bin/pip install /home/${USERNAME}/telemetry_server_testing

RUN chown -R ${USERNAME}:${USERNAME} /home/${USERNAME}

EXPOSE 80

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]