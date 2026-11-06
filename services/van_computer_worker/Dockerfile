# OpenMuse-derived computer image baseline.
# Upstream: CopilotKit/openmuse@34b15bc80340e582fb8c25573646cfb0bbc5184d
# Source: apps/computer/Dockerfile, MIT. VAN adds its own bounded file helper.
FROM node:22.22.0-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash python3 git coreutils \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/van /workspace \
    && chown 1000:1000 /workspace

COPY files.py /opt/van/files.py
RUN chmod 0555 /opt/van/files.py

ENV HOME=/workspace LANG=C.UTF-8
WORKDIR /workspace
USER 1000:1000
VOLUME ["/workspace"]
ENTRYPOINT ["/usr/bin/sleep"]
CMD ["infinity"]
