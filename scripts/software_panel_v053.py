"""Build an outcome-blind source inventory, then freeze an admitted 200/40 panel."""
from __future__ import annotations

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import urllib.request

from proworksim.software_panel_v053 import (
    CODE_REVISION, DATASET, DATASET_REVISION, build_inventory,
    canonical_bytes, freeze_panel, sha256, write_new,
)


def fetch(source_root):
    """Retrieve only fixed raw task assets; resume interrupted public downloads."""
    root = Path(source_root)
    root.mkdir(parents=True, exist_ok=True)
    tree_path = root / "hf-tree.json"
    if tree_path.exists():
        tree = json.loads(tree_path.read_bytes())
    else:
        url = (f"https://huggingface.co/api/datasets/{DATASET}/tree/"
               f"{DATASET_REVISION}/data?recursive=true&expand=false")
        with urllib.request.urlopen(url, timeout=60) as response:
            tree = json.load(response)
        write_new(tree_path, tree)

    def get_shard(row):
        path = root / Path(row["path"]).name
        url = (f"https://huggingface.co/datasets/{DATASET}/resolve/"
               f"{DATASET_REVISION}/{row['path']}?download=true")
        for attempt in range(7):
            size = path.stat().st_size if path.exists() else 0
            if size == row["size"]:
                if sha256(path.read_bytes()) != row["lfs"]["oid"]:
                    raise ValueError(f"Published task shard digest mismatch: {path}")
                return {"path": str(path), "bytes": size, "sha256": row["lfs"]["oid"],
                        "upstream_path": row["path"], "url": url}
            if size > row["size"]:
                raise ValueError(f"Existing task shard exceeds published size: {path}")
            if attempt == 6:
                break
            request = urllib.request.Request(url, headers={
                "Range": f"bytes={size}-", "Accept-Encoding": "identity"})
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    if size and (response.status != 206 or not response.headers.get(
                            "Content-Range", "").startswith(f"bytes {size}-")):
                        raise ValueError("Download server did not honor the resume offset")
                    with path.open("ab" if size else "wb") as stream:
                        shutil.copyfileobj(response, stream)
            except (OSError, TimeoutError):
                if attempt == 5:
                    raise
        raise RuntimeError(f"Public task download remained incomplete: {path}")

    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(get_shard, tree))
    extras = (
        (f"SWE-smith-{CODE_REVISION}.tar.gz",
         f"https://codeload.github.com/SWE-bench/SWE-smith/tar.gz/{CODE_REVISION}"),
        ("dataset-card.md",
         f"https://huggingface.co/datasets/{DATASET}/resolve/{DATASET_REVISION}/README.md"),
    )
    for name, url in extras:
        path = root / name
        if not path.exists():
            with urllib.request.urlopen(url, timeout=120) as response, path.open("xb") as stream:
                shutil.copyfileobj(response, stream)
        records.append({"path": str(path), "bytes": path.stat().st_size,
                        "sha256": sha256(path.read_bytes()), "url": url})
    manifest = {"dataset": DATASET, "dataset_revision": DATASET_REVISION,
                "official_code_revision": CODE_REVISION, "records": records}
    write_new(root / "download-manifest.json", manifest)
    return {"manifest": str(root / "download-manifest.json"),
            "bytes": sum(row["bytes"] for row in records), "shards": len(tree)}


def profile_slugs(code_root):
    profiles = Path(code_root) / "swesmith/profiles"
    result = {}
    for path in profiles.rglob("*.py"):
        for node in ast.parse(path.read_bytes()).body:
            if not isinstance(node, ast.ClassDef):
                continue
            fields = {}
            for statement in node.body:
                if (isinstance(statement, ast.AnnAssign)
                        and isinstance(statement.target, ast.Name)
                        and isinstance(statement.value, ast.Constant)):
                    fields[statement.target.id] = statement.value.value
            if not all(key in fields for key in ("owner", "repo", "commit")):
                continue
            slug = f"{fields['owner']}__{fields['repo']}.{fields['commit'][:8]}"
            result[slug] = {
                "owner": fields["owner"], "repo": fields["repo"],
                "commit": fields["commit"], "profile_class": node.name,
                "profile_file": str(path.relative_to(code_root)),
                "profile_file_sha256": sha256(path.read_bytes()),
            }
    return result


def inventory(source_root, code_root, output, tasks_root):
    import duckdb

    source_root = Path(source_root)
    downloads = json.loads((source_root / "download-manifest.json").read_bytes())
    if (downloads["dataset"] != DATASET or downloads["dataset_revision"] != DATASET_REVISION
            or downloads["official_code_revision"] != CODE_REVISION):
        raise ValueError("Use the fixed official dataset and profile revisions")
    shards = [row for row in downloads["records"] if row["path"].endswith(".parquet")]
    if len(shards) != 11:
        raise ValueError("Require every one of the 11 official shards")
    paths = []
    for row in shards:
        path = Path(row["path"])
        if path.stat().st_size != row["bytes"] or sha256(path.read_bytes()) != row["sha256"]:
            raise ValueError("Downloaded shard differs from its source manifest")
        paths.append(str(path))
    connection = duckdb.connect()
    cursor = connection.execute("SELECT * FROM read_parquet(?)", [paths])
    columns = [item[0] for item in cursor.description]
    rows = (dict(zip(columns, row, strict=True)) for row in cursor.fetchall())
    source = {
        "dataset": DATASET, "dataset_revision": DATASET_REVISION,
        "official_code_revision": CODE_REVISION,
        "download_manifest_sha256": sha256((source_root / "download-manifest.json").read_bytes()),
        "dataset_url": f"https://huggingface.co/datasets/{DATASET}/tree/{DATASET_REVISION}",
        "code_url": f"https://github.com/SWE-bench/SWE-smith/tree/{CODE_REVISION}",
        "expert_trajectories_downloaded": False,
    }
    value, raw_rows = build_inventory(rows, source_manifest=source,
                                       official_profile_slugs=profile_slugs(code_root))
    candidate_ids = {task for repo in value["repositories"]
                     for task in repo["candidate_task_ids"]}
    for task_id in sorted(candidate_ids):
        write_new(Path(tasks_root) / (task_id + ".json"), raw_rows[task_id])
    write_new(output, value)
    return {"output": str(output), "inventory_sha256": sha256(canonical_bytes(value)),
            "raw_row_count": value["raw_row_count"],
            "repository_count": value["repository_count"],
            "eligible_repository_count": value["eligible_repository_count"],
            "candidate_task_files": len(candidate_ids)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    download = subparsers.add_parser("fetch")
    download.add_argument("--source-root", required=True)
    prepare = subparsers.add_parser("inventory")
    prepare.add_argument("--source-root", required=True)
    prepare.add_argument("--code-root", required=True)
    prepare.add_argument("--tasks-root", required=True)
    prepare.add_argument("--output", required=True)
    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("--inventory", required=True)
    freeze.add_argument("--admission", required=True)
    freeze.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.action == "fetch":
        value = fetch(args.source_root)
    elif args.action == "inventory":
        value = inventory(args.source_root, args.code_root, args.output, args.tasks_root)
    else:
        panel = freeze_panel(json.loads(Path(args.inventory).read_bytes()),
                             json.loads(Path(args.admission).read_bytes()))
        write_new(args.output, panel)
        value = {"output": args.output, "panel_sha256": sha256(canonical_bytes(panel)),
                 "main_tasks": 200, "repeat_tasks": 40, "episodes": 280}
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
