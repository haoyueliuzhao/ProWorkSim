"""Independent v055 clones of already qualified, immutable v054 image templates."""
import json
from pathlib import Path
import subprocess
from .software_benchmark_native_rootfs_v054 import canonical, digest

def clone_prepared_rootfs(environment_manifest, destination):
    """Fresh episode root; preserve mapped numeric owners without SDK mounts."""
    environment_manifest = Path(environment_manifest).resolve()
    public = json.loads(environment_manifest.read_bytes())
    source_manifest = Path(public["rootfs_manifest"])
    raw = source_manifest.read_bytes()
    if digest(raw) != public["rootfs_manifest_sha256"]:
        raise ValueError("Rootfs template manifest identity changed")
    manifest = json.loads(raw)
    if manifest.get("numeric_ownership_equivalence_admitted") is not True:
        raise ValueError("Template lacks exact numeric ownership preparation")
    destination = Path(destination).resolve()
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    helper = Path(__file__).resolve().parents[2] / "tools/native_uid_bootstrap_v055.py"
    subprocess.run(["sudo", "-n", "/usr/bin/python3", str(helper), "clone",
                    str(source_manifest), digest(raw), str(destination / "rootfs")], check=True)
    manifest.update(prepared_root=str(destination / "rootfs"),
                    cloned_from_manifest_sha256=digest(raw),
                    cloned_from_environment_sha256=digest(environment_manifest.read_bytes()))
    path = destination / "rootfs-manifest.json"
    path.write_bytes(canonical(manifest))
    public.update(rootfs_manifest=str(path), rootfs_manifest_sha256=digest(path.read_bytes()))
    env = destination / "public-environment.json"
    env.write_bytes(canonical(public))
    return {"rootfs": str(destination / "rootfs"), "environment_manifest": str(env),
            "rootfs_manifest": str(path), "rootfs_manifest_sha256": digest(path.read_bytes())}
