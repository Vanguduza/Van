"""Launch native Artemis with the explicit VAN ChatGPT subscription binding."""
import os
from pathlib import Path
import sys

ROOT = Path(os.environ.get("VAN_ARTEMIS_ROOT", "/opt/hermes-mobile-fabric/artemis/current")).resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["ARTEMIS_ARTEMIS_JSONC"] = str(Path(__file__).with_name("profile.json"))
os.environ.setdefault("ARTEMIS_APP_DIR", "/home/ubuntu/.local/share/van/artemis-subscription")
os.environ.setdefault("ARTEMIS_TRACES_DIR", "/home/ubuntu/.local/share/van/artemis-subscription/traces")
for name in ("ARTEMIS_FAKE_LLM", "OPENAI_API_KEY", "OPENAI_BASE_URL"):
    os.environ.pop(name, None)

from provider import bind_native_artemis
bind_native_artemis()

from mcp_server.server import main
if __name__ == "__main__":
    main()
