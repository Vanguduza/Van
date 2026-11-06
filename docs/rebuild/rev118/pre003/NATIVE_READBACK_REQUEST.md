# Native read-only readback request: VAN project identity and F15 inputs

**Why this request exists.** On 2026-10-21 this session searched its tools for a DIAL/Oracle/Commander entrypoint and found none: no `dial_*` or `dial-oracle-*` tools, and the only connector was Desktop Commander. A read-only `list_devices` call through Desktop Commander was **refused by the session's permission policy** (containment boundary), and it was not retried or worked around. The registry therefore has to be read by an operator on the DIAL control host, or by an enrolled `dial-oracle-status` / `dial-oracle-control` session.

**Scope.** Read-only. No registration, pack edit, rebaseline, certification or signing.

## Commands (run on the DIAL control host as the control-plane user)

```sh
export DIAL_CONTROL_HOME=/var/lib/dial-control      # or the deployed value
cd /path/to/dial-development-system                 # deployed DDS checkout
git rev-parse HEAD                                  # (1) DDS revision used for the readback

# (2) VAN registry record
python3 - <<'PY'
import json, os
reg = json.load(open(os.path.join(os.environ["DIAL_CONTROL_HOME"], "operations/project-registry.json")))
items = reg.get("projects", reg) if isinstance(reg, dict) else reg
rows = [p for p in (items.values() if isinstance(items, dict) else items)
        if p.get("slug") == "van" or p.get("project_id") in ("van", "16f2f43a-8d8b-4f18-a6ac-5bd8df620414")]
print(json.dumps([{k: p.get(k) for k in ("slug", "project_id", "name", "repo_dir", "repository_mode", "classification", "registered_at", "updated_at")} for p in rows], indent=2))
PY

# (3) pack presence and identity (no write)
P="$DIAL_CONTROL_HOME/projects/van/development-pack/pack.json"
test -f "$P" && python3 -c "import json,sys;p=json.load(open('$P'));print(json.dumps({'pack_id':p.get('pack_id'),'revision':p.get('revision'),'project_id':(p.get('project') or {}).get('project_id'),'baseline_sha':((p.get('artifacts') or {}).get('baseline') or {}).get('repository_sha'),'maturity':p.get('maturity_state')},indent=2))" || echo "PACK_ABSENT"

# (4) registered repo_dir HEAD and remote
R=$(python3 -c "import json,os;r=json.load(open(os.path.join(os.environ['DIAL_CONTROL_HOME'],'operations/project-registry.json')));i=r.get('projects',r) if isinstance(r,dict) else r;i=i.values() if isinstance(i,dict) else i;print(next(p['repo_dir'] for p in i if p.get('slug')=='van'))")
git -C "$R" rev-parse HEAD; git -C "$R" remote get-url origin; git -C "$R" status --porcelain | wc -l

# (5) current certifier result (read-only evaluation; prints, writes nothing)
node agent-system/bin/predevelopment-forensic-gate.mjs --project van | python3 -c "import json,sys;d=json.load(sys.stdin);print(json.dumps({k:d.get(k) for k in ('ok','state','project_id','reasons','certificate_hash')},indent=2))"
```

## Fields required back, with evidence

| # | Field | Decides |
|---|---|---|
| 1 | DDS HEAD on the host | which certifier/registry code produced the answer |
| 2 | `slug`, `project_id`, `repo_dir`, `repository_mode`, timestamps for every matching record | whether `project_id` is `van` (mapping in F15_AND_IDENTITY_REQUIREMENTS.md §2) or the UUID (mapping inverts) |
| 3 | pack `project.project_id`, `baseline_sha`, `revision`, maturity, or PACK_ABSENT | whether a pack exists and which identity it carries |
| 4 | `repo_dir` HEAD, origin URL, dirty-file count | whether the registered checkout is the `Vanguduza/Van` repository and at which commit |
| 5 | certifier `ok`, `state`, `reasons` | the current blocker list |

Return the raw command output with the host name and UTC time. A screenshot or summary is not sufficient. The lead will record it under `docs/rebuild/rev118/pre003/` and update the identity determination without renaming any identifier.
