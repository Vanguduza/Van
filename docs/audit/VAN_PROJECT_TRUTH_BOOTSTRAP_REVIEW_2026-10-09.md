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

## Exact application intake review

The companion JSON review manifest binds application commit
4ad31883d57ab518ba9af414aa849db6e240eb71 to the existing checker at the
proposed framework base ff820b04aee0b418f3db28073536a13e18fcafd9.
That proposed base has not been adopted. This is a prospective review, not
admission or an authorization record. The baseline registry is unchanged.

The prospective checker reports 791 findings: 362 missing ledger rows,
212 untrusted authorization references, 182 uncovered-file findings and
35 findings where proposed changes expose gaps in the base history.
The manifest supplies exact parents, first-parent diff digests and changed
paths for 580 implicated commits, plus hashes and paths of 28 existing
authorization files requiring separate intake review. Counts of findings
are not counts of independent authorization records or unique commits.

The committed application audit reports 214 findings. Current main still
cannot serve as a trusted enforcement base because it lacks the baseline
registry/checker framework. These results remain failed in the review packet.
No ledger row was edited/deleted, no authorization was minted, and no
checker, baseline, trust rule or history exemption was weakened. The next
review acts are initial framework adoption and separate exact-scope intake,
followed by append-only coverage rows and successful admission verification.
