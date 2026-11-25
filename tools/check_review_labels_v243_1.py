"""Four frozen archive states, eight live calls; no grading information enters the controller."""

from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_review_handoff_v243_1 as exp
from proworksim import software_anomaly_evidence_v243_1 as revised
from proworksim.software_benchmark_candidates_v054 import reference, checked
from proworksim.software_context_panel_v231 import PairedLedger
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.software_benchmark_deepseek_api_v105 import load_api_key
from proworksim.software_organization_api_v204 import Backend, DirectHTTPS
from proworksim.storage import digest, read_json
from jsonschema import Draft202012Validator
import json, fcntl

PLAN, RUN = exp.PLAN / "classification", exp.RUN / "classification"
ROOT = exp.ROOT
NS = "v243.1-label"


def main():
    expected = {"q04": "A2", "q10": "A4", "q11": "A4", "q14": "A2"}
    bank = {r["id"]: r for r in exp.event.previous.prior.sources()}
    probes = read_json(exp.event.previous.prior.PREFLIGHT / "references.json")
    rows = {k: {**bank[k], "probe_id": probes[k]["probe_id"]} for k in expected}
    spec = dict(
        expected=expected,
        design="Four known development states; both prompts get same three graphs, routes, tool and output cap. One new decision per condition per state. Adopt only if more correct labels, with no reduction in valid scoped decisions. This measures classification only.",
        files=[reference(Path(__file__)), reference(Path(revised.__file__))],
        cap_per_call=8192,
    )
    exp.event.previous.freeze(PLAN / "protocol.json", spec)
    RUN.mkdir(parents=True, exist_ok=True)
    auth = exp.RUN / "authority.json"
    db = PairedLedger.load(auth)
    tok = ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
    counter = OfficialDeepSeekCounter(tok, manifest_sha256=digest(tok.read_bytes()))

    def pair(k):
        rowslot = dict(
            case=k,
            account_cap_nanoyuan=230000000000,
            arm_limit=8192,
            worst_pair_nanoyuan=2 * 8192 * 8000,
        )
        exp.event.previous.prior.paired.reserve(auth, rowslot, namespace=NS, block=NS + ":" + k)
        for arm in ("KEEP", "OSA") if k in ("q04", "q11") else ("OSA", "KEEP"):
            resfile = PLAN / k / (arm + ".json")
            if resfile.exists():
                continue
            row = rows[k]
            slot = NS + ":" + k + ":" + arm
            folder = RUN / k / arm
            if folder.exists():
                raise ValueError("Prior attempt requires reconciliation")
            db.admit(slot, 8192)
            res = dict(site=k, arm=arm, expected=expected[k], label=None, valid=False)
            try:
                options = exp.event.orders.orders(row)
                w = (exp.event.orders.wire if arm == "KEEP" else revised.wire)(row, options)
                backend = Backend(
                    folder,
                    db,
                    slot,
                    counter,
                    DirectHTTPS(load_api_key(ROOT / ".env"), timeout_seconds=150),
                    {"activate_organization"},
                )
                payload = dict(
                    team_slot_id=slot,
                    request_id=slot,
                    member_id=row["observer"],
                    usage_id="agent",
                    wire=w,
                )
                if backend.post("/tokenize", payload)["prompt_tokens"] + w["max_tokens"] > 8192:
                    raise ValueError("Reserve exceeded")
                b = backend.post("/chat/completions", payload)
                calls = b["choices"][0]["message"].get("tool_calls") or []
                if len(calls) != 1 or calls[0]["function"]["name"] != "activate_organization":
                    raise ValueError("Missing decision")
                d = json.loads(calls[0]["function"]["arguments"])
                Draft202012Validator(w["tools"][0]["function"]["parameters"]).validate(d)
                c = exp.event.orders.contract.compile_decision(row, d)
                res.update(
                    label=d["anomaly"], order=d["work_order"], route=d["route"], reason=d["reason"]
                )
                key = d["work_order"]
                if key in options:
                    o = options[key]
                    if (
                        c["patch"]["option"] != "K"
                        or c["execution"]["package"] != o["task"]
                        or o["evidence"] not in d["basis"]
                    ):
                        raise ValueError("Incompatible execution order")
                if key == "abstain" and c["patch"]["option"] != "K":
                    raise ValueError("Invalid abstention")
                res["valid"] = True
            except Exception as e:
                res["error"] = str(e)[:400]
            finally:
                db.close(slot)
            with db.db() as conn:
                res["settlement"] = conn.execute(
                    "select status,count(*),sum(tokens),sum(cost) from requests where slot=? group by status",
                    (slot,),
                ).fetchall()
            res["receipts"] = [reference(p) for p in sorted(folder.glob("*/response.json"))]
            exp.event.save(resfile, res)

    with (RUN / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(pair, expected))
        out = {}
        for arm in ("KEEP", "OSA"):
            rr = [read_json(PLAN / k / (arm + ".json")) for k in expected]
            out[arm] = dict(
                correct=sum(r["label"] == r["expected"] for r in rr),
                valid=sum(r["valid"] for r in rr),
                n=len(rr),
                rows=rr,
            )
        out["admitted"] = (
            out["OSA"]["correct"] > out["KEEP"]["correct"]
            and out["OSA"]["valid"] >= out["KEEP"]["valid"]
            and all(len(r["receipts"]) == 1 for arm in ("KEEP", "OSA") for r in out[arm]["rows"])
        )
        exp.event.save(PLAN / "results.json", out)


if __name__ == "__main__":
    main()
