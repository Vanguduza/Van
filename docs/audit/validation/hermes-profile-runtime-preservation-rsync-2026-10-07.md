The previously skipped Hermes profile installation test passed with actual rsync: **1 passed, 0 skipped, 0 failures**. The test used a temporary Hermes home and checked preservation of its secret file, database, sessions, memories, logs, pairing state, cache, and runtime-installed skill while replacing source-managed provider files.

The cloud image lacked rsync and libpopt0. Debian 13 packages `rsync 3.4.1+ds1-5+deb13u4` and `libpopt0 1.19+dfsg-2` were downloaded over HTTPS, checked against the package hashes in the already signature-verified Debian archive index, and extracted with `dpkg-deb -x` into `/workspace/.onboarding/browser-parser/rsync-root`. Package scripts and global installation were not used. The JSON receipt records package hashes, index trust, binary hash, test input hashes, and exact outcomes; the signature transcript is retained beside it.

To reproduce in this prepared workspace, run from the Van repository:

```bash
PATH="/workspace/.onboarding/browser-parser/rsync-root/usr/bin:$PATH" \
LD_LIBRARY_PATH="/workspace/.onboarding/browser-parser/rsync-root/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
PYTHONPATH=backend:. \
/workspace/.onboarding/van-venv/bin/python -m pytest -q \
  tests/hermes/test_profile_layout.py::test_install_profile_preserves_runtime_state_and_secrets
```

This is isolated installer preservation evidence. Production source, registry hashes, and qualification receipts were unchanged; no production Hermes host or handset was exercised.
