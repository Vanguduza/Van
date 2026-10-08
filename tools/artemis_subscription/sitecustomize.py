"""Scoped bootstrap inherited only by VAN's native Artemis task runners."""
import os

if os.environ.get("VAN_ARTEMIS_SUBSCRIPTION_BINDING") == "1":
    try:
        from provider import bind_native_artemis
        bind_native_artemis()
    except BaseException:
        # Python normally swallows sitecustomize failures. This binding must
        # instead fail closed before any unbound native task can run.
        import sys
        sys.stderr.write("VAN Artemis subscription bootstrap failed\n")
        os._exit(78)
