"""One narrow identity-metadata repair, never a general numerical-source waiver."""

import ast
import hashlib
from pathlib import Path
import subprocess

from proworksim.storage import digest


TARGET = "src/proworksim/candidate_runtime_v019.py"


def tree_identity(root):
    root = Path(root).resolve()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(
        subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()
    )
    source_hash = hashlib.sha256()
    for p in sorted((root / "src").rglob("*.py")):
        source_hash.update(str(p.relative_to(root)).encode())
        source_hash.update(p.read_bytes())
    return {
        "code_commit": commit,
        "code_dirty": dirty,
        "source_tree_sha256": source_hash.hexdigest(),
    }


def canonical_candidate(text, *, allow_metadata_fix):
    module = ast.parse(text)
    removed = {"import": 0, "keyword": 0}
    if allow_metadata_fix:
        for node in ast.walk(module):
            if isinstance(node, ast.ImportFrom) and node.module == "candidate_runtime_v017":
                before = len(node.names)
                node.names = [
                    a for a in node.names if not (a.name == "PARSER_CONTRACT" and a.asname is None)
                ]
                removed["import"] += before - len(node.names)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "profile"
                and node.func.attr == "update"
            ):
                keep = []
                for keyword in node.keywords:
                    if keyword.arg == "parser_contract":
                        expected = ast.parse("copy.deepcopy(PARSER_CONTRACT)", mode="eval").body
                        if ast.dump(keyword.value) != ast.dump(expected):
                            raise ValueError(
                                "Only the unchanged v0.17 parser contract metadata may be added"
                            )
                        removed["keyword"] += 1
                    else:
                        keep.append(keyword)
                node.keywords = keep
        module.body = [
            n for n in module.body if not (isinstance(n, ast.ImportFrom) and not n.names)
        ]
        if removed != {"import": 1, "keyword": 1}:
            raise ValueError("Expected exactly one missing parser-contract metadata repair")
    return ast.dump(module, include_attributes=False)


def verify_metadata_only_transition(old_root, new_root):
    old_root, new_root = Path(old_root).resolve(), Path(new_root).resolve()
    old, new = tree_identity(old_root), tree_identity(new_root)
    if old["code_dirty"] or new["code_dirty"]:
        raise ValueError("Both original numeric source and repaired execution source must be clean")
    old_paths = {str(p.relative_to(old_root)) for p in (old_root / "src").rglob("*.py")}
    new_paths = {str(p.relative_to(new_root)) for p in (new_root / "src").rglob("*.py")}
    if old_paths != new_paths:
        raise ValueError("Numerical/source file inventory changed")
    changed = [
        p for p in sorted(old_paths) if (old_root / p).read_bytes() != (new_root / p).read_bytes()
    ]
    if changed != [TARGET]:
        raise ValueError("Source review permits only the named constructor metadata repair")
    original = (old_root / TARGET).read_text()
    current = (new_root / TARGET).read_text()
    if canonical_candidate(original, allow_metadata_fix=False) != canonical_candidate(
        current, allow_metadata_fix=True
    ):
        raise ValueError("Candidate execution changed beyond the exact parser metadata addition")
    return {
        "version": "parser-metadata-only-source-review-v0.19",
        "passed": True,
        "numerical_source": old,
        "execution_source": new,
        "changed_src_paths": changed,
        "old_file_sha256": digest(original.encode()),
        "new_file_sha256": digest(current.encode()),
        "scope": "All src bytes match except exactly importing the existing PARSER_CONTRACT and copying it into actual profile metadata. Generation, parser functions, model loading, precision, attention, prefix, probability replay, backward and replica code are unchanged. New-source actual two-process identity/probability control is still required for parallel deployment.",
    }
