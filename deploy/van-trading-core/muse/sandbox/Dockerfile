# VAN Muse browser sandbox — ARM64 Trading Core.
# Debian bookworm base is digest-pinned; Chromium is security-version pinned for reproducibility.
FROM debian:bookworm-20260918-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251

ARG CHROMIUM_VERSION=154.0.8037.57-1~deb12u1
ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/root \
    VAN_MUSE_CONTROL_BIND=0.0.0.0 \
    VAN_MUSE_CONTROL_PORT=9230 \
    VAN_MUSE_CONTROL_TOKEN_FILE=/run/secrets/control-token

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      chromium="${CHROMIUM_VERSION}" \
      fonts-liberation \
      fonts-noto-core \
      python3-minimal \
      util-linux \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 10001 --gid users --create-home --shell /usr/sbin/nologin muse \
 && install -d -o 10001 -g users -m 0700 /home/muse/profile /home/muse/downloads \
 && install -d -m 0755 /etc/chromium/policies/managed /run/secrets

COPY policy.json /etc/chromium/policies/managed/van-muse.json
COPY supervisor.py /usr/local/bin/van-muse-supervisor
COPY entrypoint.sh /usr/local/bin/van-muse-entrypoint

RUN chmod 0555 /usr/local/bin/van-muse-supervisor /usr/local/bin/van-muse-entrypoint \
 && chmod 0444 /etc/chromium/policies/managed/van-muse.json

WORKDIR /root
ENTRYPOINT ["/usr/local/bin/van-muse-entrypoint"]
