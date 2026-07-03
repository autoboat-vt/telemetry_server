FROM alpine:3.20

RUN apk add --no-cache curl

COPY cron-entrypoint.sh /opt/cron-entrypoint.sh
RUN chmod +x /opt/cron-entrypoint.sh

ENTRYPOINT ["/opt/cron-entrypoint.sh"]
