# van-private-core — deployment package

Owner decision 2026-09-29 §3. The VAN private plane: a dedicated trust zone holding what VAN
knows about how its owner works, and nothing that acts on the world.

Nothing in this directory has ever been run. There is no host yet (external gate G-PC-1 in
`docs/project-state/VAN_PRIVATE_CORE_TOPOLOGY_20260929.md`). `qualify.sh` is what decides
whether an installed host is what it claims to be.

```text
  van-gateway / Hermes (callers)
        │  mutual TLS (private-core CA) + scoped internal token (understanding)
        ▼
  ┌───────────────────────────────────────────────────────────┐
  │  VAN-PRIVATE-CORE                                          │
  │                                                            │
  │  private overlay interface                                 │
  │    van-private-core.service  :9140                         │
  │      GET /v1/private-core/owner-model/revision             │
  │      GET /v1/private-core/personal-context  (fenced)       │
  │                                                            │
  │  /var/lib/van-private-core (not mounted by any other zone) │
  │    owner-model.sqlite3   Owner Cognitive Model,            │
  │                          owner_model_revision, outbox      │
  │    hindsight-owner/      owner-private Hindsight   (G-PC-5)│
  │    openviking-owner/     owner-private OpenViking  (G-PC-5)│
  └───────────────────────────────────────────────────────────┘
```

| Component | Where | Notes |
|---|---|---|
| Bounded API | `systemd/van-private-core.service` → `van_gateway.private_core.app:create_private_core_app` | only the two routes above; mTLS required; any bind outside 10/8, 172.16/12, 192.168/16, 100.64/10, fc00::/7 refused |
| Owner Cognitive Model, `owner_model_revision`, outbox | `backend/van_gateway/understanding/owner_model*.py` | SQLite under `/var/lib/van-private-core` |
| Personal-context resolver | `backend/van_gateway/understanding/personal_context_resolver.py` | requested revision must equal the live authoritative revision, else `PERSONAL_CONTEXT_UNAVAILABLE` |
| Owner-private Hindsight / OpenViking | declared placement only | loopback on this host; outbox targets exist, services do not |

## Must not host

Generic browser automation, Stagehand, Chromium, Jev browser execution, VATI order execution,
broker adapters. The repository names of each are listed in `topology.json` (`must_not_host`)
and enforced by `tests/contracts/test_van_private_core_topology.py`; `qualify.sh` checks a
live host for the same.

## Run (once a host exists)

```bash
sudo install -d -o van-private -g van-private -m 0700 /var/lib/van-private-core /var/log/van-private-core
sudo install -m 0600 deploy/van-private-core/runtime.env.example /etc/van-private-core/runtime.env  # then fill in
sudo install -m 0644 deploy/van-private-core/systemd/van-private-core.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now van-private-core.service
sudo bash deploy/van-private-core/qualify.sh   # exits 0 only when every check is GREEN
```
