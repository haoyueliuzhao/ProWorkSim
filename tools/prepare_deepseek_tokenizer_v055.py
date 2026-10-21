"""Install only the pinned official CPU recipe and tokenizer via domestic mirrors."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
from urllib.parse import urljoin, urlsplit
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from domestic_asset_download import download  # noqa: E402

WHEEL = "deepseek_recipe-0.2.0-cp310-abi3-manylinux_2_28_x86_64.whl"
WHEEL_SHA = "259812bf382bc82668b672707c5922095cc4f5f60a6c514ff89640bb62a746f7"
WHEEL_BYTES = 12846711
MS_REVISION = "9f9818127fdfbb60feba204799d617a874b32a86"
MODEL = "deepseek-ai/DeepSeek-V4.1-Flash-1017"


def ref(path):
    data = path.read_bytes()
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        raise SystemExit("Refuse another preparation after a manifest has been frozen")
    pypi = json.loads((root / "pypi-metadata.json").read_text())
    expected = [x for x in pypi["urls"] if x["filename"] == WHEEL]
    if (pypi["info"]["version"] != "0.2.0" or len(expected) != 1
            or expected[0]["digests"]["sha256"] != WHEEL_SHA
            or expected[0]["size"] != WHEEL_BYTES or expected[0]["yanked"]):
        raise ValueError("Official PyPI wheel identity differs")
    links = Links()
    links.feed((root / "tuna-index.html").read_text())
    urls = [urljoin("https://pypi.tuna.tsinghua.edu.cn/simple/deepseek-recipe/", link)
            for link in links.links if urlsplit(link).path.endswith("/" + WHEEL)]
    if len(urls) != 1 or urlsplit(urls[0]).hostname != "pypi.tuna.tsinghua.edu.cn":
        raise ValueError("One exact domestic wheel mirror is required")
    url = urls[0].split("#", 1)[0]
    wheel = root / WHEEL
    new_payload = 0
    if not wheel.exists():
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(url, timeout=120) as response:
            if response.status != 200 or response.geturl() != url:
                raise ValueError("Domestic wheel HTTP response is not exact")
            body = response.read(WHEEL_BYTES + 1)
        if len(body) != WHEEL_BYTES or hashlib.sha256(body).hexdigest() != WHEEL_SHA:
            raise ValueError("Domestic wheel bytes do not match official PyPI")
        with wheel.open("xb") as stream:
            stream.write(body)
        new_payload += len(body)
    if ref(wheel)["sha256"] != WHEEL_SHA or wheel.stat().st_size != WHEEL_BYTES:
        raise ValueError("Existing wheel is not the pinned version")
    files = json.loads((root / "modelscope-metadata.json").read_text())["Data"]["Files"]
    selected = [item for item in files if item["Name"] in {"tokenizer.json", "tokenizer_config.json", "LICENSE"}]
    if len(selected) != 3 or any(item["Revision"] != MS_REVISION for item in selected):
        raise ValueError("Official ModelScope tokenizer revision differs")
    assets = []
    for item in selected:
        name = item["Name"]
        source = f"https://modelscope.cn/api/v1/models/{MODEL}/repo?Revision={MS_REVISION}&FilePath={name}"
        result = download(source, root / "tokenizer" / name,
                          expected_sha256=item["Sha256"], expected_bytes=item["Size"])
        new_payload += result["payload_bytes_received"]
        assets.append({**ref(root / "tokenizer" / name), "modelscope_revision": MS_REVISION,
                       "source_url": source})
    overlay = root / "overlay"
    overlay.mkdir(exist_ok=False)
    with zipfile.ZipFile(wheel) as archive:
        for item in archive.infolist():
            target = (overlay / item.filename).resolve()
            if not target.is_relative_to(overlay) or item.external_attr >> 16 & 0o170000 == 0o120000:
                raise ValueError("Unsafe wheel path")
        archive.extractall(overlay)
    installed = [ref(path) for path in sorted(overlay.rglob("*")) if path.is_file()]
    manifest = {
        "version": "software-benchmark-v055-official-tokenizer-preparation-r1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "recipe_version": "0.2.0", "recipe_wheel": {**ref(wheel), "source_url": url},
        "tokenizer_model": MODEL, "modelscope_revision": MS_REVISION,
        "declared_hf_revision": "1bae0e1088993b9b82de08f59de5be5a34e42170",
        "hf_bytes_equivalence_independently_verified": False,
        "official_metadata": [ref(root / "pypi-metadata.json"), ref(root / "modelscope-metadata.json")],
        "tokenizer_files": assets, "overlay_path": str(overlay), "installed_files": installed,
        "new_asset_payload_bytes": new_payload, "environment_proxy_used": False,
        "origin_asset_downloads": 0, "model_weight_downloads": 0,
        "official_recipe_matches_provider_usage": "requires_live_neutral_control",
    }
    with manifest_path.open("x") as stream:
        json.dump(manifest, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({"manifest": ref(manifest_path), "new_asset_payload_bytes": new_payload,
                      "installed_file_count": len(installed), "model_weight_downloads": 0}))


if __name__ == "__main__":
    main()
