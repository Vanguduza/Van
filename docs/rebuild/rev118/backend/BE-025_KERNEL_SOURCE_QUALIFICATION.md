# Browser kernel source qualification

The six checks previously requiring root, nftables, network namespaces and real socket-user IDs executed on an isolated Ubuntu 24.04 Actions VM at source `169053c9a45f820aa3123bbe46fcb91384963f78`. Run `39898232618` passed all six with no skips. The tested merge tree equals the source tree. The artifact receipt is `receipts/KERNEL_SOURCE_169053c9.json`.

Five existing firewall tests load the actual deployment ruleset into disposable network namespaces. They check browser and Stagehand UDP/direct-TCP confinement, the DNS exception, unaffected other users and kernel-generated packets, the real qualification script with and without the ruleset, and that a kernel-generated reset alone cannot falsely prove firewall enforcement. The sixth runs the actual egress proxy and verifies that only its configured client UID reaches the upstream fixture.

The workflow uses a minimal pinned dependency lock, no DIAL/provider credentials, a read-only repository token and no persisted checkout credentials. It refuses any skip or missing case. It preserves logs, XML and kernel/tool versions even on failure. The host network namespace is not modified by the firewall fixtures.

This closes six source execution gaps. It does not qualify the production DIAL firewall, deployed services, a native browser host, S24, an entire Rev1.18 unit or release. The independent native provisioning and release gates remain required.
