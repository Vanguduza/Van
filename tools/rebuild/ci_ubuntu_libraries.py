#!/usr/bin/env python3
"""Install CI graphics libraries from the runner's signed Ubuntu sources.

An unrelated preinstalled Microsoft feed returned HTTP 403 during apt update,
preventing Android instrumentation from starting. No third-party feed is needed
for these Ubuntu libraries. Preserve the runner's official security suites and
signature configuration; never alter package sources or ignore update errors.
"""
from pathlib import Path
import shlex
import subprocess

LIBRARIES = ("libgl1", "libegl1", "libgles2", "libx11-6", "libxkbcommon0",
             "libfontconfig1", "libfreetype6", "libxcb1")


def commands(release: str, sources: str, *, source_path="/etc/apt/sources.list.d/ubuntu.sources"):
    values = {}
    for line in release.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key,value = line.split("=",1)
            parsed = shlex.split(value)
            values[key] = parsed[0] if len(parsed) == 1 else ""
    codename = values.get("VERSION_CODENAME", "")
    if values.get("ID") != "ubuntu" or not codename:
        raise ValueError("CI library installer requires the supported Ubuntu runner")
    suites = set()
    blocks = [b for b in sources.split("\n\n") if b.strip()]
    for block in blocks:
        fields = {}
        current = None
        for line in block.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if line.startswith((" ","\t")) and current is not None:
                fields[current] += " "+line.strip()
            elif ":" in line:
                current,value = line.split(":",1)
                fields[current] = value.strip()
        if not fields or fields.get("Enabled", "yes").lower() == "no":
            continue
        if "Suites" not in fields or not fields.get("Signed-By", "").strip():
            raise ValueError("Ubuntu CI sources must retain signed suite definitions")
        suites.update(fields["Suites"].split())
    if codename not in suites or codename+"-security" not in suites:
        raise ValueError("Ubuntu CI source selection must include the release and security suites")
    options = ["sudo", "apt-get", "-o", "Dir::Etc::sourcelist="+source_path,
               "-o", "Dir::Etc::sourceparts=-"]
    return [options+["update"], options+["install", "-y", "--no-install-recommends", *LIBRARIES]]


def main():
    source = Path("/etc/apt/sources.list.d/ubuntu.sources")
    for command in commands(Path("/etc/os-release").read_text(), source.read_text()):
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
