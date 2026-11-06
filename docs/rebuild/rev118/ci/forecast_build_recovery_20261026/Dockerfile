FROM python@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70 AS builder
WORKDIR /build
COPY build.lock gym.lock ./
RUN --mount=type=secret,id=system_ca,required=true PIP_CERT=/run/secrets/system_ca python -m pip install --no-deps --require-hashes -r build.lock
RUN --mount=type=secret,id=system_ca,required=true export SOURCE_DATE_EPOCH=315532800 PIP_CERT=/run/secrets/system_ca && \
    PYTHONHASHSEED=0 python -m pip wheel --no-cache-dir --no-deps --no-build-isolation --require-hashes -r gym.lock --wheel-dir /out/seed0a && \
    PYTHONHASHSEED=0 python -m pip wheel --no-cache-dir --no-deps --no-build-isolation --require-hashes -r gym.lock --wheel-dir /out/seed0b && \
    PYTHONHASHSEED=1 python -m pip wheel --no-cache-dir --no-deps --no-build-isolation --require-hashes -r gym.lock --wheel-dir /out/seed1
FROM scratch AS export
COPY --from=builder /out/ /
