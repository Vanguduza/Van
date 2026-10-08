"""Launch native Artemis with the explicit VAN ChatGPT subscription binding."""
import os
from pathlib import Path
import sys

ROOT = Path(os.environ.get("VAN_ARTEMIS_ROOT", "/opt/hermes-mobile-fabric/artemis/current")).resolve()
PROFILE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PROFILE_DIR))
os.environ["ARTEMIS_ARTEMIS_JSONC"] = str(PROFILE_DIR / "profile.json")
os.environ["ARTEMIS_CONFIG_DIR"] = str(PROFILE_DIR)
os.environ.setdefault("ARTEMIS_APP_DIR", "/home/ubuntu/.local/share/van/artemis-subscription")
os.environ.setdefault("ARTEMIS_TRACES_DIR", "/home/ubuntu/.local/share/van/artemis-subscription/traces")
os.environ["VAN_ARTEMIS_SUBSCRIPTION_BINDING"] = "1"
os.environ["PYTHONPATH"] = os.pathsep.join(
    [str(PROFILE_DIR), str(ROOT)] + ([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else []))
# Use native standalone task runners so an unrelated existing daemon cannot
# receive this owner's task with a different model binding.
os.environ["ARTEMIS_STANDALONE"] = "1"
# Keep native clients and task children on the qualified private ADB server.
os.environ["ARTEMIS_ADB_PATH"] = os.environ.get(
    "VAN_ARTEMIS_ADB_PATH", "/home/ubuntu/.local/share/van/artemis-subscription/toolchain/adb")
os.environ["ADB_HOST"] = "127.0.0.1"
os.environ["ADB_PORT"] = "5039"
os.environ["ADB_SERVER_SOCKET"] = "tcp:127.0.0.1:5039"
for name in ("ARTEMIS_FAKE_LLM", "OPENAI_API_KEY", "OPENAI_BASE_URL"):
    os.environ.pop(name, None)

from provider import bind_native_artemis
bind_native_artemis()

from mcp_server.server import main
if __name__ == "__main__":
    main()
