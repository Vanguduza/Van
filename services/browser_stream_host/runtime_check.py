"""Side-effect-free source/dependency check. Never opens files containing keys or sockets."""
from __future__ import annotations
import importlib.metadata
import json
import platform
import sys

REQUIRED = {'aiohttp': '3.13.5', 'aiortc': '1.14.0', 'av': '16.1.0', 'Pillow': '12.3.0', 'cryptography': '50.0.0', 'aiosqlite': '0.22.1'}


def check_runtime():
    missing = []
    for name, version in REQUIRED.items():
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            installed = None
        if installed != version:
            missing.append(name)
    ready = not missing and sys.version_info[:2] == (3, 12) and platform.machine() == 'x86_64'
    return {'service': 'van-browser-runtime', 'ready': ready, 'error': None if ready else 'RUNTIME_NOT_INSTALLED', 'missing_or_unpinned': missing, 'check': 'dependencies_only_no_network_or_listener', 'live_qualified': False}


def main():
    result = check_runtime()
    print(json.dumps(result, sort_keys=True))
    return 0 if result['ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
