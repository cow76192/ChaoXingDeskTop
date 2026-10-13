"""Record the installed dependency closure for the declared runtime/build tools."""
from importlib.metadata import distribution
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

root = Path(__file__).resolve().parents[1]
pending = [Requirement(line) for file in ("requirements.txt", "requirements-build.txt")
           for line in (root / file).read_text(encoding="utf-8").splitlines()
           if line.strip() and not line.startswith("#")]
resolved = {}
while pending:
    req = pending.pop()
    if req.marker and not req.marker.evaluate({"extra": ""}):
        continue
    name = canonicalize_name(req.name)
    if name in resolved:
        continue
    dist = distribution(req.name)
    if req.specifier and dist.version not in req.specifier:
        raise RuntimeError(f"Installed {req.name} does not satisfy {req.specifier}")
    resolved[name] = dist.version
    pending.extend(Requirement(item) for item in dist.requires or [])
(root / "requirements-lock.txt").write_text("\n".join(f"{name}=={version}" for name, version in sorted(resolved.items())) + "\n", encoding="utf-8")
print(f"Recorded {len(resolved)} installed runtime and build dependencies.")
