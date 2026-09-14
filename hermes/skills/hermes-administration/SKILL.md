---
name: hermes-administration
description: >-
  Installs, verifies, and maintains the Hermes van profile pack, skills, and
  policy hook. Use when installing the profile, running doctor checks, updating
  skills, or verifying Hermes policy registration.
---

# Hermes Administration

## Profile identity

- Name must be exactly **`van`**
- Hermes owns execution — do not install parallel agent runtimes
- Pack root in repo: `hermes/`

## Install (Hermes host)

From VAN repo root:

```bash
chmod +x tools/hermes/install_van_profile.sh tools/hermes/doctor_van_profile.sh
./tools/hermes/install_van_profile.sh
```

Target directory: `$HERMES_HOME` if set, else `~/.hermes/profiles/van`.

Installer properties:

- **Idempotent** — safe to re-run
- **Fail closed** — exits non-zero on layout/verification failure
- **Secret safe** — never copies `.env`, `*.pem`, OAuth client JSON, or token files

## Verify (read-only)

```bash
./tools/hermes/doctor_van_profile.sh
```

Also run repo test:

```bash
pytest tests/hermes/test_profile_layout.py -q
```

## Policy hook registration

Ensure Hermes loads `van_policy_hook.evaluate` from installed `policy/van_policy_hook.py`:

- Deny A5 (including audit/truth/security bypass attempts)
- Require approval for A4
- Protect audit and Project Truth mutation without authority

Run policy unit tests:

```bash
pytest hermes/policy/tests/test_van_policy_hook.py -q
```

## Skill updates

Skills live in `hermes/skills/<name>/SKILL.md`. After install, confirm each skill directory exists under `$HERMES_HOME/profiles/van/skills/`.

## Versioning

Pack version: `hermes/VERSION` — keep aligned with repo `VERSION` when releasing.

## Fail closed

Install/doctor failure → report stderr, do not claim profile is active. Missing Hermes home → instruct owner to set `HERMES_HOME` or create `~/.hermes`.
