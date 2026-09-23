# Netcup Character Forge authoring workstation

Run this only after the Netcup DIAL control bootstrap has completed.

The bootstrap installs the full VAN Character Forge production toolchain and exposes it to Desktop Commander through a bounded `vanforge` worker. It deliberately does not grant Commander owner-only acceptance authority.

Install an exact repository revision:

```bash
sudo VAN_COMMIT_SHA=<40-hex-commit> \
  bash deploy/character-forge/bootstrap-netcup-authoring.sh
```

Then Desktop Commander can use:

```bash
sudo -n -u vanforge /usr/local/libexec/van-character-forge-worker qualify
sudo -n -u vanforge /usr/local/libexec/van-character-forge-worker toolchain-lock
sudo -n -u vanforge /usr/local/libexec/van-character-forge-worker import-toolchain-lock
sudo -n -u vanforge /usr/local/libexec/van-character-forge-worker source-admit
sudo -n -u vanforge /usr/local/libexec/van-character-forge-worker rive --help
sudo -n -u vanforge /usr/local/libexec/van-character-forge-worker emulator-up
sudo -n -u vanforge /usr/local/libexec/van-character-forge-worker instrumentation
```

The qualifier returns red only for required workstation failures. Missing KVM is reported as a warning because the worker can fall back to software Android-emulator acceleration.

Owner source confirmation, core visual verdict, physical S24 qualification, biometric acceptance and M5 release remain separate owner/evidence gates.
