# VAN subordinate computer worker — OMV-002

This package builds and qualifies the persistent Linux workspace used beneath
`ComputerInteractionFabric`. It is an executor, never an agent or authority plane.

The gateway refuses execution unless all of these are true:

1. `VAN_COMPUTER_WORKER_ENABLED=true`;
2. the configured image exists locally;
3. `VAN_COMPUTER_WORKER_QUALIFICATION_FILE` names a PASS receipt;
4. the receipt's exact Docker image ID still matches the configured image;
5. the per-operation durable lease generation remains current through completion.

Build and qualify:

```bash
sudo bash deploy/van-computer-worker/bootstrap.sh
sudo bash deploy/van-computer-worker/qualify.sh
```

The scripts do not enable the gateway feature. After a green qualification, configure:

```text
VAN_COMPUTER_WORKER_ENABLED=true
VAN_COMPUTER_WORKER_IMAGE=van-computer:openmuse-r1
VAN_COMPUTER_WORKER_QUALIFICATION_FILE=/var/lib/van/computer-worker/qualification.json
```

The worker is deliberately **network-none**. It supports only VAN's typed file,
Python-file, Node-file, git-status/diff/apply operations. There is no arbitrary shell
operation, no Docker socket mount, no host bind mount, and no provider/owner credential
inside the image.

Repository completeness does not certify a deployment host. A real host must run
`qualify.sh`; image rebuilds invalidate the receipt automatically because the image ID
changes.
