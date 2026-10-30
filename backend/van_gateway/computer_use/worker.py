"""Docker-backed subordinate VAN computer worker.

Behavior and isolation patterns adapted from CopilotKit/openmuse
@34b15bc80340e582fb8c25573646cfb0bbc5184d, apps/server/src/computer.ts and
apps/computer/Dockerfile (MIT).

VAN deliberately does not copy OpenMuse's free-form terminal command primitive. The only
host child process is Docker and the only in-container operations are VAN's closed
OperationType set.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
import os
import re
from typing import Any

from .fabric import OperationRequest, OperationType
from .lease import ComputerWorkerLease

_IMAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,250}$")
_ALIAS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_OUTPUT_BYTES = 128 * 1024
MAX_TEXT_BYTES = 256 * 1024


class ComputerWorkerError(RuntimeError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


class ComputerWorkerOutcomeUnknown(ComputerWorkerError):
    pass


@dataclass(frozen=True)
class ComputerWorkerResult:
    result: dict[str, Any]
    output_sha256: str
    exit_code: int | None
    truncated: bool = False


@dataclass(frozen=True)
class DockerComputerConfig:
    enabled: bool = False
    image: str = "van-computer:openmuse-r1"
    deployment_id: str = "default"
    timeout_seconds: int = 60
    qualification_file: str = ""

    def validate(self) -> None:
        if not _IMAGE.fullmatch(self.image):
            raise ComputerWorkerError("COMPUTER_IMAGE_INVALID")
        if not _ALIAS.fullmatch(self.deployment_id):
            raise ComputerWorkerError("COMPUTER_DEPLOYMENT_ID_INVALID")
        if self.timeout_seconds < 1 or self.timeout_seconds > 600:
            raise ComputerWorkerError("COMPUTER_TIMEOUT_INVALID")


@dataclass(frozen=True)
class _Run:
    stdout: bytes
    stderr: bytes
    exit_code: int | None
    timed_out: bool
    truncated: bool


class DockerComputerWorker:
    surface = "TERMINAL"

    def __init__(self, config: DockerComputerConfig) -> None:
        config.validate()
        self.config = config

    def _qualification(self) -> dict[str, Any]:
        if not self.config.qualification_file:
            raise ComputerWorkerError("COMPUTER_QUALIFICATION_REQUIRED")
        path = os.path.abspath(os.path.expanduser(self.config.qualification_file))
        try:
            raw = json.loads(open(path, "r", encoding="utf-8").read())
        except (OSError, ValueError, TypeError) as exc:
            raise ComputerWorkerError("COMPUTER_QUALIFICATION_UNAVAILABLE") from exc
        if (
            raw.get("status") != "PASS"
            or raw.get("qualified") is not True
            or raw.get("image") != self.config.image
            or not str(raw.get("image_id") or "").startswith("sha256:")
        ):
            raise ComputerWorkerError("COMPUTER_QUALIFICATION_INVALID")
        return raw

    async def _assert_qualified(self) -> dict[str, Any]:
        evidence = self._qualification()
        image = await self._docker(
            ["image", "inspect", self.config.image, "--format", "{{.Id}}"],
            timeout_seconds=5,
        )
        if image.timed_out or image.exit_code != 0:
            raise ComputerWorkerError("COMPUTER_IMAGE_UNAVAILABLE")
        current = image.stdout.decode("utf-8", errors="replace").strip()
        if current != str(evidence["image_id"]):
            raise ComputerWorkerError("COMPUTER_QUALIFICATION_IMAGE_DRIFT")
        return evidence

    @staticmethod
    def _identity(deployment: str, workspace: str) -> tuple[str, str]:
        deployment_hash = hashlib.sha256(deployment.encode()).hexdigest()[:12]
        workspace_hash = hashlib.sha256(workspace.encode()).hexdigest()[:20]
        stem = f"van-{deployment_hash}-{workspace_hash}"
        return f"{stem}-computer", f"{stem}-workspace"

    @staticmethod
    def _container_path(raw: str | None) -> str:
        path = str(raw or "/workspace")
        if "\x00" in path or len(path) > 2048 or not path.startswith("/workspace"):
            raise ComputerWorkerError("COMPUTER_PATH_INVALID")
        parts = [p for p in path.split("/") if p]
        if ".." in parts:
            raise ComputerWorkerError("COMPUTER_PATH_INVALID")
        normalized = "/" + "/".join(parts)
        if normalized != "/workspace" and not normalized.startswith("/workspace/"):
            raise ComputerWorkerError("COMPUTER_PATH_INVALID")
        return normalized

    async def _docker(
        self, args: list[str], *, input_bytes: bytes = b"", timeout_seconds: int | None = None
    ) -> _Run:
        env = {
            key: value for key, value in os.environ.items()
            if key in {
                "PATH", "HOME", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG",
                "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH",
            }
        }
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except OSError as exc:
            raise ComputerWorkerError("COMPUTER_DOCKER_UNAVAILABLE") from exc
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input_bytes),
                timeout=timeout_seconds or self.config.timeout_seconds,
            )
            timed_out = False
        except asyncio.TimeoutError:
            timed_out = True
            proc.kill()
            stdout, stderr = await proc.communicate()
        truncated = len(stdout) + len(stderr) > MAX_OUTPUT_BYTES
        remaining = MAX_OUTPUT_BYTES
        out = stdout[:remaining]
        remaining -= len(out)
        err = stderr[:max(0, remaining)]
        return _Run(out, err, proc.returncode, timed_out, truncated)

    async def _checked(self, args: list[str], *, input_bytes: bytes = b"") -> _Run:
        result = await self._docker(args, input_bytes=input_bytes, timeout_seconds=10)
        if result.timed_out:
            raise ComputerWorkerError("COMPUTER_DOCKER_TIMEOUT")
        if result.exit_code != 0 or result.truncated:
            raise ComputerWorkerError("COMPUTER_DOCKER_CONTROL_FAILED")
        return result

    async def status(self) -> dict[str, Any]:
        if not self.config.enabled:
            return {"enabled": False, "ready": False, "state": "UNCONFIGURED"}
        try:
            info = await self._docker(["info", "--format", "{{.ServerVersion}}"], timeout_seconds=5)
            image = await self._docker(["image", "inspect", self.config.image], timeout_seconds=5)
        except ComputerWorkerError as exc:
            return {"enabled": True, "ready": False, "state": "UNAVAILABLE", "reason": exc.code}
        ready = (
            not info.timed_out and info.exit_code == 0 and
            not image.timed_out and image.exit_code == 0
        )
        if not ready:
            return {
                "enabled": True, "ready": False, "state": "UNAVAILABLE",
                "image": self.config.image, "network": "disabled",
            }
        try:
            evidence = await self._assert_qualified()
        except ComputerWorkerError as exc:
            return {
                "enabled": True, "ready": False, "state": "UNQUALIFIED",
                "reason": exc.code, "image": self.config.image, "network": "disabled",
            }
        return {
            "enabled": True, "ready": True, "state": "READY",
            "image": self.config.image, "image_id": evidence["image_id"],
            "qualified_at": evidence.get("qualified_at"),
            "network": "disabled",
        }

    async def _inspect(self, container: str, volume: str) -> dict[str, Any] | None:
        listed = await self._checked([
            "container", "ls", "--all", "--filter", f"name=^/{container}$", "--format", "{{.ID}}"
        ])
        if not listed.stdout.strip():
            return None
        raw = await self._checked(["container", "inspect", container])
        try:
            item = json.loads(raw.stdout)[0]
        except (ValueError, IndexError, TypeError) as exc:
            raise ComputerWorkerError("COMPUTER_ISOLATION_INSPECTION_FAILED") from exc
        host = item.get("HostConfig") or {}
        config = item.get("Config") or {}
        mounts = item.get("Mounts") or []
        safe = (
            item.get("Name") == f"/{container}"
            and config.get("Image") == self.config.image
            and config.get("User") == "1000:1000"
            and config.get("WorkingDir") == "/workspace"
            and host.get("ReadonlyRootfs") is True
            and host.get("Privileged") is False
            and "ALL" in (host.get("CapDrop") or [])
            and not (host.get("CapAdd") or [])
            and "no-new-privileges" in (host.get("SecurityOpt") or [])
            and host.get("NetworkMode") == "none"
            and int(host.get("Memory") or 0) > 0
            and int(host.get("Memory") or 0) <= 536_870_912
            and int(host.get("MemorySwap") or 0) == int(host.get("Memory") or 0)
            and 0 < int(host.get("PidsLimit") or 0) <= 128
            and not (host.get("Binds") or [])
            and not (host.get("Devices") or [])
            and len(mounts) == 1
            and mounts[0].get("Type") == "volume"
            and mounts[0].get("Name") == volume
            and mounts[0].get("Destination") == "/workspace"
            and mounts[0].get("RW") is True
        )
        if not safe:
            raise ComputerWorkerError("COMPUTER_ISOLATION_MISMATCH")
        return item

    async def _ensure_running(self, workspace: str) -> str:
        if not self.config.enabled:
            raise ComputerWorkerError("COMPUTER_UNCONFIGURED")
        container, volume = self._identity(self.config.deployment_id, workspace)
        existing = await self._inspect(container, volume)
        if existing is None:
            labels = [
                "--label", "dev.dial.van.managed=computer-v1",
                "--label", f"dev.dial.van.deployment={self.config.deployment_id}",
                "--label", f"dev.dial.van.workspace={hashlib.sha256(workspace.encode()).hexdigest()[:20]}",
            ]
            found = await self._checked([
                "volume", "ls", "--filter", f"name=^{volume}$", "--format", "{{.Name}}"
            ])
            if not found.stdout.strip():
                await self._checked(["volume", "create", *labels, volume])
            await self._checked([
                "container", "create", "--name", container, *labels,
                "--network", "none", "--read-only", "--user", "1000:1000",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--memory", "512m", "--memory-swap", "512m", "--pids-limit", "128",
                "--cpus", "1.0",
                "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777",
                "--mount", f"type=volume,src={volume},dst=/workspace",
                "--workdir", "/workspace", "--env", "HOME=/workspace", "--env", "LANG=C.UTF-8",
                "--entrypoint", "/usr/bin/sleep", self.config.image, "infinity",
            ])
            await self._checked(["container", "start", container])
            existing = await self._inspect(container, volume)
        elif not (existing.get("State") or {}).get("Running"):
            await self._checked(["container", "start", container])
            existing = await self._inspect(container, volume)
        if existing is None or not (existing.get("State") or {}).get("Running"):
            raise ComputerWorkerError("COMPUTER_START_FAILED")
        return container

    async def execute(
        self, operation_id: str, request: OperationRequest, lease: ComputerWorkerLease
    ) -> ComputerWorkerResult:
        await self._assert_qualified()
        workspace = request.target_application.strip()
        container = await self._ensure_running(workspace)
        scope = request.scope
        path = self._container_path(scope.get("path", "/workspace"))
        stdin = b""

        if request.operation_type is OperationType.LIST_FILES:
            argv = ["exec", container, "python3", "/opt/van/files.py", "list", "--path", path]
        elif request.operation_type is OperationType.READ_TEXT:
            argv = ["exec", container, "python3", "/opt/van/files.py", "read", "--path", path]
        elif request.operation_type is OperationType.WRITE_TEXT:
            text = str(scope.get("text", ""))
            stdin = text.encode("utf-8")
            if len(stdin) > MAX_TEXT_BYTES:
                raise ComputerWorkerError("COMPUTER_TEXT_TOO_LARGE")
            argv = ["exec", "-i", container, "python3", "/opt/van/files.py", "write", "--path", path]
        elif request.operation_type is OperationType.RUN_PYTHON_FILE:
            argv = ["exec", container, "python3", path]
        elif request.operation_type is OperationType.RUN_NODE_FILE:
            argv = ["exec", container, "node", path]
        elif request.operation_type is OperationType.GIT_STATUS:
            argv = ["exec", container, "git", "-C", path, "status", "--short", "--branch"]
        elif request.operation_type is OperationType.GIT_DIFF:
            argv = ["exec", container, "git", "-C", path, "--no-pager", "diff", "--"]
        elif request.operation_type is OperationType.GIT_APPLY_PATCH:
            patch = str(scope.get("patch", "")).encode("utf-8")
            if not patch or len(patch) > MAX_TEXT_BYTES:
                raise ComputerWorkerError("COMPUTER_PATCH_INVALID")
            checked = await self._docker(
                ["exec", "-i", container, "git", "-C", path, "apply", "--check", "-"],
                input_bytes=patch,
            )
            if checked.timed_out or checked.exit_code != 0 or checked.truncated:
                raise ComputerWorkerError("COMPUTER_PATCH_CHECK_FAILED")
            stdin = patch
            argv = ["exec", "-i", container, "git", "-C", path, "apply", "-"]
        else:
            raise ComputerWorkerError("COMPUTER_OPERATION_UNSUPPORTED", request.operation_type.value)

        run = await self._docker(argv, input_bytes=stdin)
        if run.timed_out:
            # A timeout during a mutating external process is not safe to classify as failed:
            # the process may have changed the workspace before being killed.
            if request.operation_type.mutates:
                raise ComputerWorkerOutcomeUnknown("COMPUTER_OUTCOME_UNKNOWN")
            raise ComputerWorkerError("COMPUTER_OPERATION_TIMEOUT")
        if run.exit_code != 0:
            raise ComputerWorkerError(
                "COMPUTER_OPERATION_FAILED",
                run.stderr.decode("utf-8", errors="replace")[:500],
            )
        payload = {
            "operation_id": operation_id,
            "lease_id": lease.lease_id,
            "generation": lease.generation,
            "stdout": run.stdout.decode("utf-8", errors="replace"),
            "stderr": run.stderr.decode("utf-8", errors="replace"),
            "exit_code": run.exit_code,
            "truncated": run.truncated,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return ComputerWorkerResult(
            result=payload, output_sha256=digest, exit_code=run.exit_code, truncated=run.truncated
        )
