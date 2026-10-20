"""Freeze a completed domestic pip report and install REF from its local cache.

No downloader or index fallback exists here. HTTP cache bodies are hard-linked
into a named wheelhouse; pip verifies the report's hashes during offline install.
The existing resident/SDK environment is never an installation target.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

VLLM_VERSION = "0.32.0"
VLLM_SHA256 = "5e2ecdc5b0baf72921c288486417ca82778456a448e4fe60b62ee43c0dfc8611"
ALLOWED_HOST = "pypi.tuna.tsinghua.edu.cn"


def frozen_write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(body)
    except FileExistsError:
        if path.read_bytes() != body:
            raise ValueError(f"Refusing to replace a different frozen file: {path}")


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def identity(path):
    info = path.stat()
    return {"device": info.st_dev, "inode": info.st_ino, "bytes": info.st_size,
            "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns}


def prepare(report_path, cache_root, wheelhouse, output_root):
    report_body = report_path.read_bytes()
    report = json.loads(report_body)
    if report.get("version") != "1" or not report.get("install"):
        raise ValueError("A complete pip install report v1 is required")
    if report.get("environment", {}).get("python_version") != "3.12":
        raise ValueError("The report must target the prepared Python 3.12 environment")
    items = []
    names = set()
    for entry in report["install"]:
        metadata = entry["metadata"]
        name = re.sub(r"[-_.]+", "-", metadata["name"]).lower()
        version = metadata["version"]
        if name in names or re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) is None:
            raise ValueError("Duplicate or invalid package name")
        names.add(name)
        if re.fullmatch(r"[A-Za-z0-9.!+_-]+", version) is None:
            raise ValueError("Unsafe package version")
        download = entry["download_info"]
        url = download["url"]
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST
                or parsed.port not in (None, 443)
                or parsed.username or parsed.password or parsed.fragment):
            raise ValueError("Report contains a non-domestic or non-HTTPS wheel source")
        filename = unquote(parsed.path.rsplit("/", 1)[-1])
        if not filename.endswith(".whl") or "/" in filename or "\\" in filename:
            raise ValueError("Only named wheel files are accepted")
        expected = download["archive_info"]["hashes"].get("sha256")
        if not expected or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise ValueError("Every wheel requires an explicit SHA256")
        if name == "vllm" and (version != VLLM_VERSION or expected != VLLM_SHA256):
            raise ValueError("vLLM differs from the independently pinned official wheel")
        key = hashlib.sha224(url.encode()).hexdigest()
        cached = cache_root.joinpath(*key[:5], key + ".body")
        if cached.is_symlink() or not cached.is_file():
            raise FileNotFoundError(f"Wheel absent from completed HTTP cache: {filename}")
        destination = wheelhouse / filename
        items.append({
            "name": name, "version": version, "sha256": expected, "url": url,
            "filename": filename, "cached_body": str(cached),
            "wheel_path": str(destination), "bytes": cached.stat().st_size,
        })
    if "vllm" not in names:
        raise ValueError("The report does not contain the pinned REF service")
    wheelhouse.mkdir(parents=True, exist_ok=True)
    for item in items:
        cached, destination = Path(item["cached_body"]), Path(item["wheel_path"])
        if destination.exists():
            if not os.path.samefile(cached, destination):
                raise ValueError("A different wheelhouse entry already exists")
            continue
        try:
            os.link(cached, destination)
        except OSError as error:
            if error.errno == errno.EXDEV:
                raise ValueError("Use a wheelhouse on the same filesystem as the cache") from error
            raise
    items.sort(key=lambda item: item["name"])
    requirements = "".join(
        f'{item["name"]}=={item["version"]} --hash=sha256:{item["sha256"]}\n'
        for item in items
    ).encode()
    requirements_path = output_root / "ref-requirements.lock"
    frozen_write(requirements_path, requirements)
    frozen_write(output_root / "ref-install-plan.json", report_body)
    manifest = {
        "version": "software-benchmark-v054-ref-local-wheelhouse-v1",
        "report_sha256": hashlib.sha256(report_body).hexdigest(),
        "requirements_sha256": hashlib.sha256(requirements).hexdigest(),
        "package_count": len(items),
        "total_wheel_bytes": sum(item["bytes"] for item in items),
        "source_host": ALLOWED_HOST,
        "new_network_payload_bytes": 0,
        "cache_reuse": "hardlink_no_payload_copy",
        "wheel_integrity": "required_hashes_verified_by_subsequent_offline_pip_install",
        "formal_execution_authorized": False,
        "packages": items,
    }
    frozen_write(output_root / "ref-wheelhouse.json", json_bytes(manifest))
    return requirements_path, manifest


def install(*, pip_python, target_python, wheelhouse, output_root, requirements, manifest):
    target_root = target_python.parent.parent
    if target_root.name != "ref-venv" or "software-benchmark-v054" not in str(target_root):
        raise ValueError("Installation is restricted to the independent v054 ref-venv")
    pyvenv = target_root / "pyvenv.cfg"
    if not pyvenv.is_file() or "include-system-site-packages = false" not in pyvenv.read_text():
        raise ValueError("REF must be a private venv without system site packages")
    receipt_path = output_root / "ref-install-receipt.json"
    if receipt_path.exists():
        raise ValueError("An install receipt exists; inspect it before another installation")
    command = [
        str(pip_python), "-m", "pip", "--python", str(target_python),
        "--isolated", "--disable-pip-version-check", "install",
        "--no-index", "--find-links", str(wheelhouse),
        "--only-binary=:all:", "--no-deps", "--require-hashes", "--no-compile",
        "-r", str(requirements),
    ]
    environment = dict(os.environ)
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                "http_proxy", "https_proxy", "all_proxy"):
        environment.pop(key, None)
    environment.update({
        "PIP_CONFIG_FILE": "/dev/null", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "NO_PROXY": "*", "no_proxy": "*",
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
    })
    before = {item["filename"]: identity(Path(item["wheel_path"]))
              for item in manifest["packages"]}
    receipt = {
        "version": "software-benchmark-v054-ref-offline-install-v1",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "requirements_sha256": manifest["requirements_sha256"],
        "package_count": manifest["package_count"],
        "total_wheel_bytes": manifest["total_wheel_bytes"],
        "new_network_payload_bytes": 0,
        "formal_execution_authorized": False,
    }
    with (output_root / "ref-install.log").open("xb") as log:
        completed = subprocess.run(command, env=environment, stdout=log,
                                   stderr=subprocess.STDOUT, check=False)
    after = {item["filename"]: identity(Path(item["wheel_path"]))
             for item in manifest["packages"]}
    receipt.update({
        "ended_at_utc": datetime.now(timezone.utc).isoformat(),
        "exit_code": completed.returncode,
        "cache_files_unchanged_during_install": before == after,
        "wheel_hashes_verified_by_pip": completed.returncode == 0,
        "installed": completed.returncode == 0 and before == after,
    })
    frozen_write(receipt_path, json_bytes(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--http-cache", type=Path)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--install-only", action="store_true",
                        help="Use an already frozen host wheelhouse inside the CPU namespace")
    parser.add_argument("--pip-python", type=Path, default=Path(sys.executable))
    parser.add_argument("--target-python", type=Path)
    args = parser.parse_args()
    if args.install_only:
        requirements = args.output_root.absolute() / "ref-requirements.lock"
        manifest = json.loads(
            (args.output_root / "ref-wheelhouse.json").read_bytes())
        if hashlib.sha256(requirements.read_bytes()).hexdigest() != manifest["requirements_sha256"]:
            raise ValueError("Frozen requirements identity changed")
    else:
        if args.report is None or args.http_cache is None:
            parser.error("Preparation requires --report and --http-cache")
        requirements, manifest = prepare(
            args.report.absolute(), args.http_cache.absolute(),
            args.wheelhouse.absolute(), args.output_root.absolute())
    if args.install or args.install_only:
        if args.target_python is None:
            parser.error("--install requires --target-python")
        result = install(
            pip_python=args.pip_python.absolute(), target_python=args.target_python.absolute(),
            wheelhouse=args.wheelhouse.absolute(), output_root=args.output_root.absolute(),
            requirements=requirements, manifest=manifest)
    else:
        result = {key: value for key, value in manifest.items() if key != "packages"}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not (args.install or args.install_only) or result["installed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
