# VAN Muse browser sandbox — ARM64 Trading Core.
# Multi-arch Debian bookworm-slim index pinned to the 2026-09-18 release set.
FROM debian:bookworm-20260918-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251

ARG CHROMIUM_VERSION=154.0.8037.57-1~deb12u1
ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/home/muse \
    XDG_CONFIG_HOME=/home/muse/.config \
    XDG_CACHE_HOME=/home/muse/.cache

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      chromium="${CHROMIUM_VERSION}" \
      fonts-liberation \
      fonts-noto-core \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 10001 --gid users --create-home --shell /usr/sbin/nologin muse \
 && install -d -o 10001 -g users -m 0700 /home/muse/profile /home/muse/.cache \
 && install -d -m 0755 /etc/chromium/policies/managed

COPY policy.json /etc/chromium/policies/managed/van-muse.json
COPY entrypoint.sh /usr/local/bin/van-muse-browser

RUN chmod 0555 /usr/local/bin/van-muse-browser \
 && chmod 0444 /etc/chromium/policies/managed/van-muse.json

USER 10001:100
WORKDIR /home/muse
ENTRYPOINT ["/usr/local/bin/van-muse-browser"]
