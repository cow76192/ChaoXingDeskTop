"""Verify the build environment against the checked-in dependency lock."""
from importlib.metadata import distributions
from pathlib import Path
import platform
import struct
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def verify(root):
    if sys.platform != "win32" or struct.calcsize("P") != 8 or platform.python_version() != "3.13.9":
        raise RuntimeError("Release builds require Windows x64 and Python 3.13.9")
    locked = {}
    for line in (root / "requirements-lock.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        req = Requirement(line)
        pins = list(req.specifier)
        if len(pins) != 1 or pins[0].operator != "==" or "*" in pins[0].version:
            raise RuntimeError(f"Dependency must have an exact version: {line}")
        name = canonicalize_name(req.name)
        if name in locked:
            raise RuntimeError(f"Duplicate locked dependency: {name}")
        locked[name] = pins[0].version

    installed = {canonicalize_name(d.metadata["Name"]): d for d in distributions()}
    errors = []
    for name, version in locked.items():
        dist = installed.get(name)
        if dist is None or dist.version != version:
            errors.append(f"{name}: expected {version}, installed {dist.version if dist else 'missing'}")
            continue
        # --no-deps installation must still provide the entire runtime closure.
        for item in dist.requires or []:
            req = Requirement(item)
            if req.marker and not req.marker.evaluate({"extra": ""}):
                continue
            dependency = canonicalize_name(req.name)
            if dependency not in locked or locked[dependency] not in req.specifier:
                errors.append(f"{name}: unlocked or incompatible dependency {req}")

    for filename in ("requirements.txt", "requirements-build.txt"):
        for line in (root / filename).read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            req = Requirement(line)
            if req.marker and not req.marker.evaluate({"extra": ""}):
                continue
            name = canonicalize_name(req.name)
            if name not in locked or locked[name] not in req.specifier:
                errors.append(f"Lock does not satisfy {filename}: {req}")

    # pip bootstraps the environment but is not part of the application closure.
    extras = set(installed) - set(locked) - {"pip"}
    if extras:
        errors.append("Unexpected build packages: " + ", ".join(sorted(extras)))
    if errors:
        raise RuntimeError("\n".join(errors))
    print(f"Verified {len(locked)} locked dependencies; no extra application packages.")


if __name__ == "__main__":
    verify(Path(__file__).resolve().parents[1])
