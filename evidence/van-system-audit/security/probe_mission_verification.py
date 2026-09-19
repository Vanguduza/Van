import asyncio, json, os, sys, tempfile
from cryptography.fernet import Fernet
TMP = tempfile.mkdtemp()
os.environ.update({"VAN_DATABASE_PATH": f"{TMP}/p4.sqlite3",
    "VAN_GOOGLE_TOKEN_FERNET_KEY": Fernet.generate_key().decode(),
    "VAN_DEVICE_SECRET_FERNET_KEY": Fernet.generate_key().decode(),
    "VAN_INGRESS_TOKEN": "probe-ingress-token-0123456789abcdef",
    "VAN_INTERNAL_CONTROL_TOKEN": "probe-internal-token",
    "VAN_HERMES_BASE_URL": "http://127.0.0.1:9"})
sys.path.insert(0, "/home/user/Van/backend")
from httpx import AsyncClient, ASGITransport
from van_gateway.app import create_app
from van_gateway.config import get_settings
get_settings.cache_clear()
INT = {"X-Van-Internal-Token": "probe-internal-token"}
async def main():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        async with app.router.lifespan_context(app):
            body = {"owner_principal_id":"owner","origin":"OWNER_TEXT","origin_channel":"UI",
                    "title":"probe","goal":"prove verification","project_id":"van",
                    "success_contract":{"postconditions":{"notebook_exists":"api_readback"},"verifier_class":"API_READBACK","evidence_required":True}}
            r = await c.post("/v1/missions", json=body, headers=INT)
            print("POST /v1/missions ->", r.status_code, json.dumps(r.json())[:300])
            mid = r.json().get("mission_id")
            print("\n-- what does a caller need to reach VERIFIED_SUCCESS? --")
            from van_gateway.mission.models import MissionState, LEGAL_TRANSITIONS
            st = MissionState.CAPTURED
            path = ["UNDERSTOOD","PLANNED","AUTHORIZED","RUNNING","VERIFYING"]
            for t in path:
                rr = await c.post(f"/v1/missions/{mid}/transition", json={"target": t}, headers=INT)
                print(f"  -> {t}: {rr.status_code} {json.dumps(rr.json())[:110]}")
            fake = {"target":"VERIFIED_SUCCESS","verification":{
                "status":"VERIFIED","evidence_refs":["evidence://trust-me"],
                "observed_postconditions":{"notebook exists": True},"missing_postconditions":[],
                "verifier_version":"i-say-so/1.0","verified_at_ms":1789740000000}}
            rr = await c.post(f"/v1/missions/{mid}/transition", json=fake, headers=INT)
            print("  -> VERIFIED_SUCCESS with a SELF-ASSERTED receipt:", rr.status_code, json.dumps(rr.json())[:400])
            g = await c.get(f"/v1/missions/{mid}", headers={"X-Van-Ingress-Token":"probe-ingress-token-0123456789abcdef"})
            print("  mission read back ->", g.status_code, json.dumps(g.json())[:300] if g.status_code==200 else g.text[:200])
asyncio.run(main())
