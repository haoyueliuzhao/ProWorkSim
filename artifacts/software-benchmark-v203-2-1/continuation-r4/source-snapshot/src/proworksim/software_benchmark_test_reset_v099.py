"""Narrow, opt-in repair of official test-path reset; original test patch retained."""
from __future__ import annotations

import copy
import hashlib
from pathlib import PurePosixPath
import re
import shlex
from types import SimpleNamespace

VERSION = "v099-official-test-preimage-reset-r1"
TASKS = frozenset({"sphinx-doc__sphinx-11510", "astropy__astropy-7336"})
_PATH = r"[A-Za-z0-9_./-]+"


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_paths(patch):
    """Both sides are necessary for renames; accept only reviewed plain paths."""
    paths = set()
    headers = []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            match = re.fullmatch(r"diff --git a/(" + _PATH + r") b/(" + _PATH + r")", line)
            if not match:
                raise ValueError("Unsupported official test patch path encoding")
            headers.append(match.groups())
            paths.update(match.groups())
        elif line.startswith(("--- ", "+++ ")):
            value = line[4:]
            if value == "/dev/null":
                continue
            if not headers or value not in ("a/" + headers[-1][0], "b/" + headers[-1][1]):
                raise ValueError("Official patch preimage/postimage path differs from its header")
        elif line.startswith(("GIT binary patch", "Binary files ")):
            raise ValueError("This repair does not support binary official test patches")
    if not paths:
        raise ValueError("Official test patch has no reviewed paths")
    for path in paths:
        parts = PurePosixPath(path).parts
        if (path != str(PurePosixPath(path)) or path.startswith("/")
                or any(part in {"..", ".", ".git"} for part in parts)):
            raise ValueError("Official test path is not an ordinary repository-relative file")
    if any(a != b and b.startswith(a + "/") for a in paths for b in paths):
        raise ValueError("Official file paths cannot overlap as parent and child")
    return sorted(paths)


def reset_command(base_commit, paths):
    """Only named test files may be restored/removed; never remove a directory."""
    if not re.fullmatch(r"[0-9a-f]{40}", base_commit):
        raise ValueError("Pinned full baseline commit required")
    if not paths or paths != sorted(set(paths)):
        raise ValueError("Exact sorted official test paths required")
    # Reuse the same path restrictions even for standalone CPU/control callers.
    for path in paths:
        if test_paths(f"diff --git a/{path} b/{path}\n") != [path]:
            raise ValueError("Unsafe reset path")
    lines = ["# " + VERSION, "(",
             "git cat-file -e " + shlex.quote(base_commit + "^{commit}") + " || exit $?", 
             "for pws_v099_path in " + " ".join(map(shlex.quote, paths)) + "; do",
             "  pws_v099_parent=${pws_v099_path%/*}",
             '  while [ "$pws_v099_parent" != "$pws_v099_path" ] && [ "$pws_v099_parent" != "." ]; do',
             '    if [ -L "$pws_v099_parent" ]; then echo "v099 refuses symlink test parent" >&2; exit 97; fi',
             '    case "$pws_v099_parent" in */*) pws_v099_parent=${pws_v099_parent%/*} ;; *) break ;; esac',
             "  done",
             '  if [ -e "$pws_v099_path" ] && [ ! -f "$pws_v099_path" ] && [ ! -L "$pws_v099_path" ]; then',
             '    echo "v099 refuses non-file test target" >&2; exit 97',
             "  fi",
             '  pws_v099_entry=$(git ls-tree ' + base_commit + ' -- "$pws_v099_path") || exit $?',
             '  if [ -n "$pws_v099_entry" ]; then',
             '    case "$pws_v099_entry" in "100644 blob "*|"100755 blob "*|"120000 blob "*) ;; *) echo "v099 refuses non-blob baseline" >&2; exit 97 ;; esac',
             '    rm -f -- "$pws_v099_path" || exit $?',
             '    git checkout ' + base_commit + ' -- "$pws_v099_path" || exit $?',
             "  else",
             '    rm -f -- "$pws_v099_path" || exit $?',
             "  fi",
             "done",
             ") || exit $?"]
    return "\n".join(lines)


def repair_eval_script(instance):
    """Replace two known reset commands; do not alter patch or test commands."""
    if instance["instance_id"] not in TASKS:
        raise ValueError("Instance outside the two reviewed reset failures")
    script, patch, base = instance["eval_script"], instance["test_patch"], instance["base_commit"]
    paths = test_paths(patch)
    lines = script.splitlines(keepends=True)
    resets = [i for i, line in enumerate(lines) if line.startswith("git checkout ")]
    starts = [i for i, line in enumerate(lines) if re.fullmatch(r"git apply -v - <<'(EOF_[0-9]+)'\n", line)]
    if len(resets) != 2 or len(starts) != 1:
        raise ValueError("The reviewed official reset/apply structure changed")
    start = starts[0]
    delimiter = re.fullmatch(r"git apply -v - <<'(EOF_[0-9]+)'\n", lines[start]).group(1)
    ends = [i for i, line in enumerate(lines) if line == delimiter + "\n"]
    if len(ends) != 1 or not resets[0] < start < ends[0] < resets[1]:
        raise ValueError("Unexpected official heredoc boundaries")
    payload = "".join(lines[start + 1:ends[0]])
    if payload not in {patch, patch + "\n"}:
        raise ValueError("Eval script does not contain the exact official test patch")
    for index in resets:
        args = shlex.split(lines[index])
        if (args[:3] != ["git", "checkout", base] or len(args) <= 3
                or not set(args[3:]).issubset(paths)):
            raise ValueError("Unexpected baseline or reset path in official script")
    replacement = reset_command(base, paths) + "\n"
    transformed = []
    for index, line in enumerate(lines):
        transformed.append(replacement if index in resets else line)
        if index == ends[0]:
            transformed.append("pws_v099_apply_status=$?\n"
                'if [ "$pws_v099_apply_status" -ne 0 ]; then\n'
                '  echo "v099 official test patch application failed" >&2\n'
                '  exit "$pws_v099_apply_status"\nfi\n')
    result = "".join(transformed)
    return result, {"version": VERSION, "instance_id": instance["instance_id"],
        "base_commit": base, "paths": paths, "old_reset_paths": shlex.split(lines[resets[0]])[3:],
        "original_eval_sha256": digest(script), "repaired_eval_sha256": digest(result),
        "official_test_patch_sha256": digest(patch), "unchanged_heredoc_payload_sha256": digest(payload),
        "replaced_reset_commands": 2, "patch_failure_is_technical_unknown": True,
        "candidate_patch_changed": False, "test_commands_changed": False,
        "official_test_patch_changed": False, "grading_rules_changed": False}


def diagnostics_adapter(original_diagnostics, instances):
    """Explicit new scorer hook: diagnostics.make_repaired_run_instance.

    The new scorer must separately freeze this adapter and a new manifest. This
    function does not authorize or run a container, nor edit the installed SDK.
    """
    instances = {row["instance_id"]: copy.deepcopy(row) for row in instances}
    if not instances or not set(instances).issubset(TASKS):
        raise ValueError("Only the reviewed two-task scoring set is supported")
    def make_repaired_run_instance(harness, directory):
        original, provenance = original_diagnostics.make_repaired_run_instance(harness, directory)
        # make_test_spec adds the official exit-code recording commands. Keep
        # those exact runtime bytes too, instead of comparing to raw dataset text.
        expected = {key: harness.make_test_spec(row).eval_script for key, row in instances.items()}
        scripts = {key: repair_eval_script({**row, "eval_script": expected[key]})
                   for key, row in instances.items()}

        def run_instance(spec, *args, **kwargs):
            if spec.instance_id not in instances or spec.eval_script != expected[spec.instance_id]:
                raise ValueError("Official test specification differs from the frozen two-task source")
            copied = copy.copy(spec)
            repaired = scripts[spec.instance_id][0]
            prefix = "#!/bin/bash\nset -uxo pipefail\n"
            if not repaired.startswith(prefix) or not repaired.endswith("\n"):
                raise ValueError("Official script header/trailing newline changed")
            # TestSpec.eval_script is a read-only property over eval_script_list.
            copied.eval_script_list = repaired[len(prefix):-1].split("\n")
            if copied.eval_script != repaired:
                raise ValueError("Copied official TestSpec does not preserve the repaired script bytes")
            return original(copied, *args, **kwargs)

        return run_instance, {**provenance, "test_reset_revision": VERSION,
            "test_reset_plans": {key: item[1] for key, item in scripts.items()}}

    return SimpleNamespace(**{**vars(original_diagnostics),
        "make_repaired_run_instance": make_repaired_run_instance})
