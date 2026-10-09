# Project Truth framework adoption for VAN

This review branch adds the existing Project Truth checker, hooks, unchanged lineage
baselines, code-owner rules, original owner ledger decision and trusted-checker CI job
to current main. It carries no application/runtime implementation and mints no new
authorization record. Existing main CI jobs are preserved.

Current main lacks this framework. The existing Programme A baseline
12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af is already an ancestor of main and the
consolidation; no new enforcement baseline or history exemption is introduced.
The Programme B baseline and all recorded historical gaps remain unchanged.

This is a proposed initial owner adoption, not an adopted/trusted base. Per
tools/ci/README.md, the initial transition needs the owner's explicit review act.
Subsequent authorization intake must land separately before the application commits
it authorizes. This branch does not authorize PR #93, sign a release, deploy a
gateway, enroll a device, or qualify any handset case.

After adoption, enable the documented GitHub protections for main and gpt/**
requiring project-truth-ledger, code-owner review, pull requests and no bypass.
These settings are currently absent/unprotected; this branch does not claim they
have changed.
