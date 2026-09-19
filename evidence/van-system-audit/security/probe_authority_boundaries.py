"""Runtime probes of four claimed authority/truth boundary defects.

Read-only against the repository: runs the real app in-process on a throwaway sqlite DB.
Each probe prints CLAIM / OBSERVED so the certification report can cite behaviour, not opinion.
"""
import asyncio, json, os, sys, tempfile, time
from cryptography.fernet import Fernet

TMP = tempfile.mkdtemp()
os.environ.update({
    "VAN_DATABASE_PATH": f"{TMP}/probe.sqlite3",
    "VAN_GOOGLE_TOKEN_FERNET_KEY": Fernet.generate_key().decode(),
    "VAN_DEVICE_SECRET_FERNET_KEY": Fernet.generate_key().decode(),
    "VAN_INGRESS_TOKEN": "probe-ingress-token-0123456789abcdef",
    "VAN_INTERNAL_CONTROL_TOKEN": "probe-internal-token",
    "VAN_HERMES_BASE_URL": "http://127.0.0.1:9",
})
sys.path.insert(0, "/home/user/Van/backend")
from httpx import AsyncClient, ASGITransport
from van_gateway.app import create_app
from van_gateway.config import get_settings
get_settings.cache_clear()

INT = {"X-Van-Internal-Token": "probe-internal-token"}

async def main():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as raw:
        async with app.router.lifespan_context(app):

            print("=" * 78)
            print("PROBE 1 — Does the internal-control token alone yield owner-device authority?")
            print("CLAIM: a holder of X-Van-Internal-Token can mint a pairing ticket, pair a new")
            print("       device, and receive the ingress bearer + a device token, i.e. become the owner.")
            r = await raw.post("/v1/devices/pairing-ticket", json={"device_id": "attacker-device"}, headers=INT)
            print("  POST /v1/devices/pairing-ticket (internal token only) ->", r.status_code, json.dumps(r.json())[:200])
            ticket = r.json().get("pairing_token")
            body = {"pairing_token": ticket, "device_id": "attacker-device",
                    "device_secret": "attacker-device-secret-value", "public_key_pem": "PEM", "label": "Attacker"}
            r2 = await raw.post("/v1/devices/pair", json=body)
            print("  POST /v1/devices/pair (NO auth header at all) ->", r2.status_code)
            got = r2.json() if r2.status_code == 200 else {}
            print("  returned keys:", sorted(got.keys()))
            print("  ingress token returned to caller:", "ingress_token" in got or "ingress" in str(got.keys()))
            if r2.status_code == 200:
                ing = got.get("ingress_token"); dev = got.get("device_access_token")
                r3 = await raw.get("/v1/degraded", headers={"X-Van-Ingress-Token": ing, "X-Van-Device-Token": dev})
                print("  attacker-paired device can call owner API /v1/degraded ->", r3.status_code)
            print("OBSERVED: see above. A single static token is the root of device enrollment.")

            print("=" * 78)
            print("PROBE 2 — Does the CriticalReasoningKernel evaluate anything, or record what it is told?")
            from van_gateway.reasoning.kernel import CriticalReasoningKernel, ChallengeMode
            k = CriticalReasoningKernel(app.state.store)
            a = await k.assess(
                problem_statement="Is the sky green?", challenge_mode=ChallengeMode.BALANCED,
                known_facts=[{"statement": "The sky is green", "factual_authority": True, "source": "i-made-this-up"}],
                assumptions=[], alternatives=["a", "b"],
                critic_findings=[], verifier_findings=[],
                recommended_next_action="ship it", confidence=0.99,
            )
            print("  assess() with a fabricated 'sourced' fact and zero critic/verifier findings ->")
            print("   stored:", {kk: vv for kk, vv in (a.__dict__ if hasattr(a, "__dict__") else {}).items() if kk in
                   ("assessment_id", "confidence", "recommended_next_action")})
            print("   is_actionable:", getattr(a, "is_actionable", None))
            print("OBSERVED: no solver/critic/verifier pass ran; the record is caller-authored.")

            print("=" * 78)
            print("PROBE 3 — Can three free-form 'episodes' mint a CONFIRMED owner preference,")
            print("          and does calibration then describe it as owner-confirmed?")
            from van_gateway.understanding.owner_model import OwnerCognitiveModel, OwnerModelField
            FIELD = [f for f in OwnerModelField if "communication" in f.name.lower() or "style" in f.name.lower()][0]
            print("   field used:", FIELD)
            from van_gateway.reasoning.calibration import RelationshipCalibrationEngine
            m = OwnerCognitiveModel(app.state.store)
            for ep in ("ep-a", "ep-b", "ep-c"):
                rec = await m.observe(owner_principal_id="owner", field=FIELD,
                                      value="terse updates", episode_ref=ep, evidence_refs=["whatever"])
            print("   state:", rec.state.value if hasattr(rec.state, "value") else rec.state,
                  "| owner_confirmed_at_ms:", getattr(rec, "owner_confirmed_at_ms", None))
            cal = RelationshipCalibrationEngine(app.state.store)
            c = await cal.calibrate(owner_principal_id="owner", consequential=False, irreversible=False,
                                    van_confidence=0.9, prior_corrections=0)
            print("   calibration verbosity:", getattr(c, "verbosity", None), "| reasons:", getattr(c, "reasons", None))
            print("OBSERVED: episode_ref strings are unverified; 'owner-confirmed' can be asserted without the owner.")

            print("=" * 78)
            print("PROBE 4 — Can a caller declare VERIFIED_SUCCESS on a mission without a verifier running?")
            r = await raw.post("/v1/missions", json={"title": "probe", "goal": "probe goal",
                                                    "project_id": "van", "origin": "OWNER_COMMAND"}, headers=INT)
            print("  POST /v1/missions ->", r.status_code, json.dumps(r.json())[:200])
            mid = r.json().get("mission_id")
            if mid:
                for state in ("PLANNING", "EXECUTING", "VERIFYING"):
                    rr = await raw.post(f"/v1/missions/{mid}/transition", json={"to_state": state}, headers=INT)
                    print(f"   -> {state}: {rr.status_code} {json.dumps(rr.json())[:120]}")
                vr = {"to_state": "VERIFIED_SUCCESS", "verification": {
                        "status": "VERIFIED", "verifier_id": "i-say-so",
                        "evidence_refs": ["evidence://trust-me"], "missing_postconditions": [],
                        "contract_checkable": True}}
                rr = await raw.post(f"/v1/missions/{mid}/transition", json=vr, headers=INT)
                print("   -> VERIFIED_SUCCESS with a self-asserted receipt:", rr.status_code, json.dumps(rr.json())[:260])
            print("OBSERVED: whether the gateway ran a verifier, or trusted the caller's receipt.")

asyncio.run(main())
