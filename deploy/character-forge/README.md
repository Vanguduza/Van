# Netcup Character Forge authoring workstation

Run this only after the Netcup DIAL control bootstrap has completed.

The bootstrap installs the full VAN Character Forge production toolchain and exposes it to Desktop Commander through a bounded `vanforge` worker. It deliberately does not grant Commander owner-only acceptance authority.

Install an exact repository revision:

```bash
sudo VAN_COMMIT_SHA=<40-hex-commit> \
  bash deploy/character-forge/bootstrap-netcup-authoring.sh
```

Then Desktop Commander drives production only through the bounded worker (every path is
jailed to `visual-authority/character-forge/`; `W` below is
`sudo -n -u vanforge /usr/local/libexec/van-character-forge-worker`):

```bash
W qualify                      # machine-readable report, also written to qualification.json
W import-toolchain-lock        # pins rive_cli + inkscape (bare versions) in TOOLS.yaml
W source-admit                 # owner then confirms the source set (owner action, not Commander)
W remove-bg IN OUT | W vectorize IN OUT.svg        # candidates only, into 02-05 lane dirs
W vector-put van_layers.svg < file.svg             # cleaned layer sheet into 06-vectors-clean
W svg-lint FILE.svg | W vectors-admit FILE.svg AUTHOR_ID
W rive-create DIR | W rml-put DIR RELPATH < file | W rml-cat DIR/RELPATH
W rive-verify DIR | W rive-inspect DIR | W rive-test DIR | W rive-screenshot DIR
W rive-candidate DIR core|full N   # pinned build -> immutable 09-rive-working/van_runtime_<stage>_<N>.riv
W rive-receipt CANDIDATE DIR SVG_SHA AUTHOR_ID RIVE_CLI_VERSION
W rive-stage CANDIDATE core_rig|full_rig
W contact-sheet FRAMES_DIR NAME.png | W frames-to-webm FRAMES_DIR NAME.webm
W forge-push forge/BRANCH "message"   # only with the owner's git-push switch (below)
W emulator-up | W instrumentation | W emulator-down   # local iteration; CI is the validator of record
```

The qualifier returns red only for required workstation failures. Missing KVM is reported as a
warning because the worker can fall back to software Android-emulator acceleration. Bootstrap
qualifies strictly (exact clean SHA); Commander's `qualify` accepts descendant commits and
reports local authoring changes as a warning.

## Owner-held switches and actions

Nothing below is available to Commander or created by the bootstrap:

- **Rive login:** `sudo -u vanforge -H env HOME=/var/lib/dial-character-forge/rive-home rive login`
  run interactively by the owner. Commander can only read `rive-auth-status`.
- **Rive cloud push/publish:** `sudo touch /etc/van-character-forge/allow-rive-cloud-write`.
  The worker refuses unless the file and its directory are root-owned.
- **Pushing candidates for CI:** provision a GitHub credential for `vanforge` limited to
  `forge/*` branches (protect `main`), then `sudo touch /etc/van-character-forge/allow-git-push`.
- Owner source confirmation, core visual verdict, independent full-rig review, physical S24
  qualification, biometric acceptance and M5 release remain separate owner/evidence gates.
