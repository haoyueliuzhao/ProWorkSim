import hashlib
import json
from pathlib import Path
import threading

import pytest

from tools import verified_image_metadata_v054 as metadata
from tools import verified_image_prepare_v054 as preparation


INVENTORY = Path(__file__).parents[1] / "config/v054-verified-image-inventory.json"


@pytest.mark.parametrize("tamper", [False, True])
def test_manifest_identity_and_no_blob_access(tmp_path, monkeypatch, tamper):
    rows, _ = metadata.load_inventory(INVENTORY)
    body = json.dumps({
        "schemaVersion": 2,
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:" + "1" * 64, "size": 17},
        "layers": [{"digest": "sha256:" + "2" * 64, "size": 99}],
    }).encode()

    class Client:
        def __init__(self, source):
            self.bytes, self.requests = 0, 0

        def token(self, name):
            return "synthetic-token"

        def manifest(self, name, ref, token):
            self.bytes += len(body)
            self.requests += 1
            return body, {"docker_content_digest": "sha256:" + (
                "0" * 64 if tamper else hashlib.sha256(body).hexdigest())}

    monkeypatch.setattr(metadata, "Metadata", Client)
    result = metadata.audit_one(rows[0], tmp_path, "mirror")
    assert result["requests"] == 1
    assert result["status"] == ("unknown" if tamper else "manifest_verified")
    assert "synthetic-token" not in json.dumps(result)
    if tamper:
        assert result["error"] == "manifest_header_digest_mismatch"
    else:
        assert result["config_digest"] == "sha256:" + "1" * 64


@pytest.mark.parametrize("condition", ["mismatch", "rate_limited"])
def test_plan_preserves_official_identity_before_download(tmp_path, monkeypatch, condition):
    rows, sha = metadata.load_inventory(INVENTORY)
    fixed = {}
    for row in rows:
        fixed[row["instance_id"]] = {
            **row, "status": "manifest_verified", "top_manifest_digest": "sha256:" + "a" * 64,
            "manifest_digest": "sha256:" + "a" * 64,
            "config_digest": "sha256:" + "b" * 64,
            "config": {"digest": "sha256:" + "b" * 64, "size": 12},
            "layers": [{"digest": "sha256:" + "c" * 64, "size": 20}],
        }
    monkeypatch.setattr(preparation, "merged_official", lambda *args: (fixed, []))
    monkeypatch.setattr(preparation, "verified_prior_layers", lambda: {})
    mirror = json.loads(json.dumps(list(fixed.values())))
    if condition == "mismatch":
        mirror[0]["manifest_digest"] = "sha256:" + "d" * 64
    else:
        mirror[0] = {**rows[0], "status": "unknown", "error": "http_429"}
    path = tmp_path / "mirror.json"
    path.write_text(json.dumps({
        "source": "mirror", "inventory_sha256": sha, "images": mirror,
    }))
    if condition == "mismatch":
        with pytest.raises(ValueError, match="mirror differs"):
            preparation.make_plan(INVENTORY, tmp_path, path, tmp_path / "blobs")
    else:
        plan = preparation.make_plan(INVENTORY, tmp_path, path, tmp_path / "blobs")
        assert len(plan["images"]) == 500
        assert plan["images"][0]["mirror_matches_official"] is None
        assert plan["images"][0]["config_digest"] == "sha256:" + "b" * 64
        assert plan["images"][0]["status"] == "pinned_not_loaded"


def test_ready_image_loads_before_remaining_downloads_finish(tmp_path, monkeypatch):
    loaded_first = threading.Event()
    blobs, images = {}, []
    for index in range(2):
        digest = "sha256:" + str(index + 1) * 64
        blobs[digest] = {
            "digest": digest, "bytes": 1, "image_name": "swebench/example",
            "path": str(tmp_path / f"{index}.blob"),
        }
        images.append({
            "instance_id": f"synthetic-{index}", "config_digest": digest,
            "config": {"digest": digest, "size": 1}, "layers": [],
            "status": "pinned_not_loaded", "environment_ready": False,
        })

    def download(image, digest, output, *, expected_bytes):
        if digest == images[1]["config_digest"]:
            assert loaded_first.wait(5), "loader waited for every remaining blob"
        Path(output).write_bytes(b"x")
        return {"status": "synthetic"}

    def load(image, *args):
        if image["instance_id"] == "synthetic-0":
            loaded_first.set()
        return {"image_id": image["config_digest"]}

    monkeypatch.setattr(preparation, "daemon_identity", lambda: {"synthetic": True})
    monkeypatch.setattr(preparation, "disk_gate", lambda *args: 999999)
    monkeypatch.setattr(preparation, "download_blob", download)
    monkeypatch.setattr(preparation, "stream_load", load)
    monkeypatch.setattr(preparation, "preflight",
                        lambda *args: {"status": "bounded_preflight_passed"})
    plan = {"blobs": blobs, "images": images, "reused_blob_proofs": {},
            "required_network_payload_bytes_upper_bound": 2}
    preparation.execute(plan, tmp_path, workers=2, minimum_free=0)
    assert plan["loaded_count"] == 2
    assert plan["bounded_preflight_passed_count"] == 2
