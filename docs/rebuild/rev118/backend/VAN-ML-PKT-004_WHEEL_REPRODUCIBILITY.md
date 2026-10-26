# VAN-ML-PKT-004: strict wheel build recovery

Status: candidate correction; ML004 remains IN_PROGRESS and unit acceptance NOT_ISSUED.

Exact published156473fc fresh workflow40272681283 fails while verifying the Gym0.26.2 wheel. Actual hosted digestfa1203bd25f6067d28e96b07174bc220806be86770629fe760d4dcba46a56624 differs from the earlier locally tested artifactea83044099fc7582a48a282b834928d3a5636d53b520dbcbb4ca2214cd9f48c1. Research and inference steps were skipped. The failure is retained, and every wheel hash remains mandatory.

An isolated pinned interpreter/build-tool experiment builds Gym three times from the unchanged hash-verified upstream source. Two independent builds with PYTHONHASHSEED0 produce identical827728-byte wheels, SHA-25662ee4cd5b252e1bd45211a7ab59823446575e91062db8503faf9c2744de1e3e1. Seed1 changes the wheel. Comparison against both seed1 and the actual exported original tested wheel identifies only dependency-metadata line ordering and its RECORD checksum; all other212 archive members are byte-identical and metadata line multisets match. This is actual artifact comparison, not an inferred cause or a model-performance result.

The source recipe now pins Python hash seed0 alongside the existing build epoch; both are build-process settings. The candidate wheel lock, wheel manifest and source software inventory target the reproducible artifact. Upstream source, build tools, package versions, the other231 wheel artifacts and strict verification remain unchanged. Earlier model receipts retain their original profile hashes. Fresh complete image installation/train/export/load/cold-inference qualification for this new profile is pending a new exact committed hosted run; the local artifact experiment cannot issue it.

Evidence: receipts/FORECAST_BUILD_RECOVERY_20261026.json and ci/forecast_build_recovery_20261026. Native infrastructure admission, full parser/production artifact lifecycle, research grants/dataset entitlements, T0 capacity and independent/owner/economic/device gates remain mandatory.
