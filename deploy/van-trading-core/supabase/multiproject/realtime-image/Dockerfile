# Build candidate only. ARM64 and production admission remain separate gates.
# Context must contain the exact generated replication_connection.ex and
# compile_patch.exs from this source revision. No network acquisition at build.
FROM supabase/realtime@sha256:6769b99a2a9d2e028f1bce6e99d9e9ef5ac0b8141c53f2c8bdc1e9eb3a952cc9
WORKDIR /app
COPY --chown=nobody:nogroup replication_connection.ex /tmp/dial-replication-connection.ex
COPY --chown=nobody:nogroup compile_patch.exs /tmp/dial-compile-patch.exs
USER nobody
# Non-production build placeholders. This expression compiles one module;
# it never starts the application or connects to a database.
RUN APP_NAME=dial_realtime_build \
    SECRET_KEY_BASE=build-only-placeholder-never-a-runtime-secret-key-base \
    API_JWT_SECRET=build-only-placeholder-never-an-api-credential \
    METRICS_JWT_SECRET=build-only-placeholder-never-a-metrics-credential \
    DB_ENC_KEY=build-only-key16 \
    DB_HOST=127.0.0.1 DB_PORT=1 DB_NAME=not_connected DB_USER=not_connected DB_PASSWORD=not_connected \
    DB_IP_VERSION=ipv4 DB_SSL=false REGION=local RUN_JANITOR=false DNS_NODES= \
    ERL_AFLAGS='-proto_dist inet_tcp' ERL_FLAGS='+S 2:2 +SDcpu 1 +SDio 1' \
    /app/bin/realtime eval 'Code.eval_file("/tmp/dial-compile-patch.exs")'
# Preserve upstream entrypoint/cmd. Runtime must supply admitted private config;
# SEED_SELF_HOST=false is mandatory. This Dockerfile does not qualify the image.
