FROM python@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70
ENV PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
    PYTHONPATH=/opt/van
WORKDIR /bootstrap
COPY locks/ ./locks/
COPY verify_wheels.py ./verify_wheels.py
# The caller provides the current combined CA as a BuildKit secret. No session
# certificate, registry credential, broker profile or repository is copied.
RUN --mount=type=secret,id=system_ca,required=true \
    export SOURCE_DATE_EPOCH=315532800 PYTHONHASHSEED=0 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_PROGRESS_BAR=off && \
    PIP_CERT=/run/secrets/system_ca python -m pip install --no-deps --require-hashes \
      -r locks/build-cp312-linux-x86_64.lock && \
    PIP_CERT=/run/secrets/system_ca python -m pip wheel --no-deps --no-build-isolation --require-hashes \
      --wheel-dir /wheelhouse -r locks/research-cp312-linux-x86_64.source.lock && \
    python verify_wheels.py /wheelhouse locks/wheel-manifest-cp312-linux-x86_64.json && \
    python -m pip install --no-index --no-deps --require-hashes --find-links /wheelhouse \
      -r locks/research-cp312-linux-x86_64.wheel.lock && \
    python -m pip check && \
    rm -rf /wheelhouse /root/.cache/pip
COPY . /opt/van/vati_forecast_worker/
WORKDIR /work
