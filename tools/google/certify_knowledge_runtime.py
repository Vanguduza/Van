#!/usr/bin/env python3
"""Run token-free VAN knowledge-provider canaries through the internal gateway."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.request


def read_env(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, value = line.split("=", 1)
        if k.strip() == key:
            return value.strip().strip("'\"")
    return ""


def call(base: str, token: str, method: str, path: str, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=data,
        method=method,
        headers={"X-Van-Internal-Token": token, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8")
        try:
            body = json.loads(payload)
        except Exception:
            body = {"detail": payload[:500]}
        return exc.code, body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8787")
    ap.add_argument("--gateway-env", default="~/.config/van/gateway.env")
    ap.add_argument("--vekl-mission")
    ap.add_argument("--vekl-query", default="VAN architecture")
    ap.add_argument("--obsidian", action="store_true")
    ap.add_argument("--notebook-enterprise", action="store_true")
    ap.add_argument("--notebook-consumer-id")
    ap.add_argument("--notebook-consumer-question", default="Reply with the title of this notebook and one grounded fact from its sources.")
    ap.add_argument("--output")
    args = ap.parse_args()

    token = os.environ.get("VAN_INTERNAL_CONTROL_TOKEN", "").strip() or read_env(Path(args.gateway_env).expanduser(), "VAN_INTERNAL_CONTROL_TOKEN")
    if not token:
        raise SystemExit("VAN_INTERNAL_CONTROL_TOKEN unavailable")
    report = {"base_url": args.base_url, "results": {}}
    status, payload = call(args.base_url, token, "GET", "/v1/runtime/knowledge/status")
    report["results"]["status"] = {"http": status, "payload": payload}
    if args.vekl_mission:
        status, payload = call(args.base_url, token, "POST", "/v1/runtime/knowledge/vekl/certify-canary", {
            "mission_id": args.vekl_mission, "query": args.vekl_query, "max_results": 8, "scope": "engineering",
        })
        report["results"]["vekl"] = {"http": status, "payload": payload}
    if args.obsidian:
        status, payload = call(args.base_url, token, "POST", "/v1/runtime/knowledge/obsidian/certify")
        report["results"]["obsidian"] = {"http": status, "payload": payload}
    if args.notebook_enterprise:
        status, payload = call(args.base_url, token, "POST", "/v1/runtime/knowledge/notebook/enterprise/certify")
        report["results"]["notebook_enterprise"] = {"http": status, "payload": payload}
    if args.notebook_consumer_id:
        status, payload = call(args.base_url, token, "POST", "/v1/runtime/knowledge/notebook/consumer/certify", {
            "notebook_id": args.notebook_consumer_id,
            "question": args.notebook_consumer_question,
            "scope": "certification",
        })
        report["results"]["notebook_consumer"] = {"http": status, "payload": payload}
    report["ok"] = all(item["http"] == 200 for item in report["results"].values())
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())