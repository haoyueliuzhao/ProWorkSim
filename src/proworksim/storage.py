"""Single-writer world persistence, immutable file versions and crash recovery."""

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from .freshness import refresh_freshness


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, prefix=".tmp-", delete=False) as f:
        tmp = Path(f.name)
        try:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    os.replace(tmp, path)


def read_json(path: Path):
    return json.loads(path.read_text())


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.control = self.root / "control"
        self.workspace = self.root / "workspace"

    @contextmanager
    def lock(self):
        with (self.control / "world.lock").open("a+") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def load(self) -> dict:
        return read_json(self.control / "state.json")

    def save(self, state: dict):
        atomic_write(self.control / "state.json", json_bytes(state))

    def version_path(self, artifact: dict, version_id: str) -> Path:
        if version_id not in artifact["versions"]:
            raise ValueError("Unknown artifact version")
        return (
            self.control / "versions" / artifact["artifact_id"] / version_id / artifact["filename"]
        )

    def current_path(self, artifact: dict) -> Path:
        placement = artifact.get("materialization")
        public = placement == "workspace" if placement else "analyst" in artifact["readers"]
        base = self.workspace if public else self.control / "role_files"
        return base / artifact["filename"]

    def content(self, artifact: dict, version_id: str | None = None) -> bytes:
        version_id = version_id or artifact["current_version"]
        path = (
            self.current_path(artifact)
            if version_id == artifact["current_version"]
            else self.version_path(artifact, version_id)
        )
        return path.read_bytes()

    def put(
        self,
        state: dict,
        artifact_id: str,
        content: bytes,
        owner: str,
        dependencies: list[dict] | None = None,
    ) -> dict:
        artifact = state["artifacts"][artifact_id]
        version_id = f"v{len(artifact['versions']) + 1}"
        version = {
            "artifact_id": artifact_id,
            "version_id": version_id,
            "owner": owner,
            "sha256": digest(content),
            "logical_time": state["clock"],
            "derived_from": dependencies if dependencies is not None else [],
            "status": "draft",
            "review_status": "unreviewed",
        }
        artifact["versions"][version_id] = version
        artifact["current_version"] = version_id
        atomic_write(self.version_path(artifact, version_id), content)
        atomic_write(self.current_path(artifact), content)
        refresh_freshness(state)
        version["freshness_at_creation"] = artifact["freshness"]
        return version

    def recover(self, state: dict):
        """Materialize committed versions after an interrupted write, never recalculate."""
        for artifact in state["artifacts"].values():
            version = artifact["versions"][artifact["current_version"]]
            path = self.current_path(artifact)
            if not path.exists() or digest(path.read_bytes()) != version["sha256"]:
                data = self.version_path(artifact, artifact["current_version"]).read_bytes()
                if digest(data) != version["sha256"]:
                    raise ValueError("Corrupt immutable artifact version")
                atomic_write(path, data)
