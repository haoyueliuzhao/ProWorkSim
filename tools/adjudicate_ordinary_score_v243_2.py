"""Attribute an official startup failure only when the locked prediction itself reproduces it."""

from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_ordinary_successor_v243_2 import RUN, PLAN, save, read_json
from proworksim.software_benchmark_candidates_v054 import checked, reference


def adjudicate(root, kind="code"):
    receipt_file = root / kind / "receipt.json"
    receipt = read_json(receipt_file)
    iid = receipt["instance_id"]
    _, report = receipt["official_result"]
    assert (
        receipt["status"] == "technical_unknown"
        and report[iid]["resolved"] is False
        and report[iid]["infra_failure"] is False
    )
    (folder,) = list((root / kind / "logs").glob("run_evaluation/*/*/" + iid))
    log = (folder / "run_instance.log").read_text()
    output = (folder / "test_output.txt").read_text()
    body = read_json(folder / "report.json")
    assert (
        iid in body
        and body[iid] == report[iid]
        and re.search(r"^>>>>> Test Exit Code: 1\s*$", output, re.M)
    )
    lock = read_json(checked(receipt["endpoint_lock"]))
    assert lock["tree_sha256"] == receipt["candidate_tree_sha256"]
    # The original file must compile, and the candidate must fail at the same file and line as the official traceback.
    candidate = read_json(checked(lock["candidate"]))["files"]
    baseline = read_json(root / "ordinary/actor/initial-tree.json")["files"]
    path, line = re.findall(
        r'File "/testbed/([^"\n]+)", line (\d+)\n[^\n]*\n(?:[^\n]*\^\s*\n)?IndentationError:',
        output,
    )[-1]
    assert re.search(rf"^Applied patch {re.escape(path)} cleanly\.$", log, re.M)
    patch = checked(receipt["patch"]).read_bytes()
    assert patch == (folder / "patch.diff").read_bytes() and ("+++ b/" + path).encode() in patch
    compile(baseline[path], path, "exec")
    try:
        compile(candidate[path], path, "exec")
    except IndentationError as exc:
        assert exc.lineno == int(line)
        detail = str(exc)
    else:
        raise ValueError("Locked candidate compiled")
    return dict(
        instance=iid,
        raw_status=receipt["status"],
        raw_applied_flag=report[iid]["patch_successfully_applied"],
        raw_resolved=report[iid]["resolved"],
        adjudicated_status="candidate_execution_failed",
        resolved=False,
        path=path,
        line=int(line),
        compile_error=detail,
        official_exit=1,
        provider_calls=0,
        new_score_calls=0,
        raw=reference(receipt_file),
        lock=receipt["endpoint_lock"],
        source=[
            reference(folder / n) for n in ("run_instance.log", "test_output.txt", "report.json")
        ],
    )


def main():
    save(PLAN / "first-score-adjudication.json", adjudicate(RUN))


if __name__ == "__main__":
    main()
