# Isolated CPU forecast runtime source

This is a candidate VAN-ML-PKT-004 component. No market/economic admission, native unit acceptance, deployment or order authority is supplied by this worker. The fixed synthetic data are not market evidence. The remaining forecast units and their independent/owner gates remain mandatory.

The Linux x86-64/CPython3.12.15 profile locks Qlib, LightGBM, NeuralForecast, CPU XGBoost, Optuna, Feast, MLflow, CPU Torch and all232 selected transitive distributions. Source artifacts, tested wheel artifacts and the build-tool chain have separate hash locks. Gym0.26.2 is built from its pinned source with a fixed build epoch; all resulting wheels must match the tested manifest. The interpreter image is pinned by digest. Other architectures are explicitly unexecuted and unqualified.

The CPU Torch runtime initializes its pinned bundled OpenMP before LightGBM. The initial missing-libgomp import failure is retained in the execution evidence. No package is silently omitted to make the stack import. The Docker build receives the caller's combined CA as a BuildKit secret and keeps TLS verification enabled. Neither the current repository nor account/credential directories enter the build context.

Build from this directory, supplying the current CA:

```sh
docker build --secret id=system_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -t van-forecast-source trading/vati_forecast_worker
docker image inspect van-forecast-source --format '{{.Id}}'
```

Run the fixed source test using the exact resulting image ID and a new private output directory:

```sh
python3 tools/rebuild/run_forecast_runtime_smoke.py \
  --image sha256:<actual-image-id> --output /tmp/van-model-source-run
```

The harness creates separate research and inference containers. Both are offline, have read-only roots, drop capabilities, use no-new-privileges and an init reaper, and run as the task's non-root UID. CPU, memory and PID limits are independently read from the actual kernel before framework imports. Host environment variables are never copied into the model worker; fixed empty proxy/key variables override Docker defaults. Unknown worker variables refuse without echoing values. Source code and model artifacts are separate read-only mounts; only a new private output directory is writable. Parent logs, model artifacts and execution time have explicit limits. A slow container creation is recorded separately from model execution; an unknown creation result retains its original identity for reconciliation and is never blindly retried.

The research fixture exercises actual Qlib/LightGBM, XGBoost and N-HiTS train/export/load APIs, native Optuna SQLite trials, Feast Parquet-to-SQLite materialization/readback and MLflow SQLite/artifact readback. The independent inference process loads only the four verified fixture model files, checks prediction parity and executes no training. NeuralForecast requires its v2 JSON/safetensors format, with pickle and remote loading disabled. Extra/linked files, unknown schemas, nonfinite vectors, hash mismatches and excessive bytes refuse before native loaders. Native readers receive a private verified byte snapshot. These are fixture loader compatibility checks, not general production artifact admission.

The real `vati serve` entrypoint installs a model import guard before configuration, lease or service construction. Preloaded model modules refuse startup. Existing execution-worker credential and owner-authority contracts remain intact. The Python import guard is not an operating-system sandbox; model workers are separate processes and never VATI risk/order authority.

The library prototype and its creation/import failures remain distinct from later curated-worker tests. Original one-shot timeout attempts remain failed/incomplete even when their original stopped container is subsequently reconciled. Fresh hosted qualification for the exact committed source is additive in `van-forecast-runtime-source.yml`; all original workflows and gates remain. General granted research jobs, real dataset entitlements, complete model adapters, safe production artifact lifecycle, native host capacity/noninterference and independent acceptance remain in the canonical programme.
