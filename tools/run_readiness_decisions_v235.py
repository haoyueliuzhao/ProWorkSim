"""Eight interleaved, matched decision replays on the same v234 SymPy state."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_sympy_osa_pair_v234 import PLAN as PREVIOUS_PLAN, RUN as PREVIOUS_RUN, CASE
from run_repaired_osa_pair_v233 import reserve
from proworksim.software_context_panel_v231 import ROOT, PairedLedger
from proworksim.software_project_relations_v217 import identity
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_deepseek_api_v105 import load_api_key
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.software_organization_api_v204 import Backend, DirectHTTPS
from proworksim.software_readiness_evidence_v235 import detailed_input
from proworksim.storage import atomic_write, json_bytes, read_json

PLAN = ROOT / "artifacts/software-benchmark-v235/readiness-decisions-r1"
RUN = ROOT / "runs/software-benchmark-v235/readiness-decisions-r1"
SOURCE = PREVIOUS_RUN / CASE / "OSA"
TOKENIZER = ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
PAIRS = 8
LIMIT = 4096
SEED = 235
BLOCK = "v235:sympy-readiness-decisions"


def save(path, value):
    atomic_write(path, json_bytes(value))


def prepare():
    old = read_json(PREVIOUS_PLAN / "protocol.json")
    (request,) = (SOURCE / "osa-api").glob("*/request.json")
    original = read_json(request)["payload"]
    wire = original["wire"]
    obs_file = ROOT / old["source_prefix"] / "observations.json"
    observations = read_json(obs_file)
    # The checkpoint manifest fixes the prefix. Later member events cannot enter either input.
    boundary = read_json(SOURCE / "decision.json")["original_ordinal"]
    enriched = detailed_input(wire, observations, original["member_id"], boundary)
    before = json.loads(wire["messages"][-1]["content"])
    after = json.loads(enriched["messages"][-1]["content"])
    extra = after.pop("readiness_by_evidence")
    if (
        before != after
        or {**enriched, "messages": wire["messages"]} != wire
        or enriched["messages"][:-1] != wire["messages"][:-1]
    ):
        raise ValueError("Unintended treatment difference")
    if (
        original["member_id"] != "member_002"
        or set(before["options"]) != {"K", "D1"}
        or len(extra) != 1
    ):
        raise ValueError("Wrong saved decision")
    order = ["standard"] * (PAIRS // 2) + ["detailed"] * (PAIRS // 2)
    random.Random(SEED).shuffle(order)
    slots = [
        [f"{i + 1:02d}-{a}" for a in (first, "detailed" if first == "standard" else "standard")]
        for i, first in enumerate(order)
    ]
    data = dict(
        case=CASE,
        checkpoint=old["checkpoint"],
        source=reference(request),
        observations=reference(obs_file),
        boundary=boundary,
        member=original["member_id"],
        added=extra,
        wire_sha256={"standard": identity(wire), "detailed": identity(enriched)},
        model=wire["model"],
        sampling={k: wire[k] for k in ("thinking", "temperature", "top_p", "max_tokens")},
        order=slots,
        ordering_seed=SEED,
        independent_provider_seed=False,
        arm_limit=LIMIT,
        worst_pair_nanoyuan=2 * PAIRS * LIMIT * 8000,
        account_cap_nanoyuan=old["account_cap_nanoyuan"],
        previous_balance_nanoyuan=read_json(PREVIOUS_PLAN / "results.json")["balance_nanoyuan"],
        primary="Count K, D1, invalid and technical unknown among all eight per condition. Compare within the same sampled task state. Each call starts fresh. No best-of or replacement.",
        followup="Advance to a new full-task paired validation if all decisions are valid, the modal action changes and each condition chooses its own mode in at least 6/8 calls. Existing v234 outcomes remain separate. No C/N update.",
        files=[
            reference(Path(__file__)),
            reference(ROOT / "src/proworksim/software_readiness_evidence_v235.py"),
            reference(TOKENIZER),
        ],
    )
    return data, {"standard": wire, "detailed": enriched}


def decision(body, view):
    calls = body["choices"][0]["message"].get("tool_calls") or []
    try:
        if len(calls) != 1 or calls[0]["function"]["name"] != "activate_organization":
            raise ValueError("expected one controller decision")
        value = json.loads(calls[0]["function"]["arguments"])
        if (
            set(value) != {"option", "evidence", "reason"}
            or value["option"] not in view["options"]
            or not isinstance(value["reason"], str)
            or not 0 < len(value["reason"].strip()) <= 1200
            or not isinstance(value["evidence"], list)
            or not value["evidence"]
            or any(e not in view["evidence"] for e in value["evidence"])
        ):
            raise ValueError("invalid option, reason or evidence")
        return {"status": "valid", **value}
    except (KeyError, ValueError, TypeError) as e:
        return {"status": "invalid", "error": str(e)}


def run(data, wires):
    old = read_json(PREVIOUS_RUN / "authority.json")
    old.update(
        scope="v235 fixed-state SymPy readiness evidence decisions only",
        available_on_approval_nanoyuan=data["previous_balance_nanoyuan"],
    )
    auth = RUN / "authority.json"
    if auth.exists() and read_json(auth) != old:
        raise ValueError("Cash identity changed")
    save(auth, old)
    ledger = PairedLedger.load(auth)
    labels = sorted(s for pair in data["order"] for s in pair)
    clone_function(reserve, {**reserve.__globals__, "ARMS": labels})(
        auth, data, namespace="v235", block=BLOCK
    )
    counter = OfficialDeepSeekCounter(TOKENIZER, manifest_sha256=reference(TOKENIZER)["sha256"])
    key = load_api_key(ROOT / ".env")

    def once(label):
        arm = label.split("-")[1]
        slot = f"v235:{CASE}:{label}"
        folder = RUN / label
        folder.mkdir(exist_ok=True)
        with ledger.db() as c:
            state = c.execute("select status from slots where id=?", (slot,)).fetchone()
        if not state:
            ledger.admit(slot, LIMIT)
        else:
            with ledger.db() as c:
                requests = c.execute(
                    "select status,provider_id from requests where slot=?", (slot,)
                ).fetchall()
            if requests or state != ("active",):
                if state == ("active",):
                    ledger.close(slot)
                return
        wire = wires[arm]
        try:
            backend = Backend(
                folder / "api",
                ledger,
                slot,
                counter,
                DirectHTTPS(key, timeout_seconds=120),
                {"activate_organization"},
            )
            backend.post(
                "/chat/completions",
                dict(
                    team_slot_id=slot,
                    request_id=slot,
                    member_id=data["member"],
                    usage_id="agent",
                    wire=wire,
                ),
            )
        except Exception as e:
            save(folder / "error.json", {"type": type(e).__name__, "message": str(e)[:350]})
        finally:
            ledger.close(slot)

    def pair(labels):
        for label in labels:
            once(label)

    with ThreadPoolExecutor(2) as pool:
        list(pool.map(pair, data["order"]))

    outcomes = []
    with ledger.db() as c:
        for label in labels:
            arm = label.split("-")[1]
            slot = f"v235:{CASE}:{label}"
            folder = RUN / label
            seen = c.execute(
                "select id,status,tokens,cost,provider_id from requests where slot=?", (slot,)
            ).fetchall()
            settled = [s for s in seen if s[1] == "settled"]
            row = dict(
                label=label,
                arm=arm,
                status="technical_unknown",
                attempts=len(seen),
                tokens=sum(s[2] for s in settled),
                nanoyuan=sum(s[3] for s in settled),
                unsettled=sum(s[1] not in ("settled", "http_error") for s in seen),
            )
            if len(settled) == 1:
                rid = settled[0][0]
                archive = folder / "api" / rid.rsplit(":", 1)[-1]
                actual = read_json(archive / "request.json")["payload"]["wire"]
                body = read_json(archive / "response.json")
                usage = read_json(archive / "usage.json")
                if (
                    actual != wires[arm]
                    or body["id"] != settled[0][4]
                    or usage["total_tokens"] != row["tokens"]
                    or usage["peak_cost_nanoyuan"] != row["nanoyuan"]
                ):
                    raise ValueError("Wire/settlement mismatch")
                row.update(
                    decision(body, json.loads(actual["messages"][-1]["content"])),
                    provider_id=body["id"],
                    model=body["model"],
                    fingerprint=body.get("system_fingerprint"),
                    input=usage["input_tokens"],
                    output=usage["output_tokens"],
                )
            outcomes.append(row)
        cap = ledger.cap
        paid = c.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
        open_holds = c.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
    summary = {}
    for arm in wires:
        batch = [r for r in outcomes if r["arm"] == arm]
        summary[arm] = {
            k: sum(r.get("option", r["status"]) == k for r in batch)
            for k in ("K", "D1", "invalid", "technical_unknown")
        }
        summary[arm].update(
            {k: sum(r.get(k, 0) for r in batch) for k in ("input", "output", "tokens", "nanoyuan")}
        )
    s, d = summary["standard"], summary["detailed"]
    valid = all(x["K"] + x["D1"] == PAIRS for x in (s, d))
    followup = valid and ((s["K"] >= 6 and d["D1"] >= 6) or (s["D1"] >= 6 and d["K"] >= 6))
    save(
        PLAN / "results.json",
        dict(
            rows=outcomes,
            summary=summary,
            full_task_gate=followup,
            new_worker_calls=0,
            CN_updates=0,
            cash_cap_nanoyuan=cap,
            cumulative_nanoyuan=paid,
            unreleased_slot_holds_nanoyuan=open_holds,
            balance_after_settlement_nanoyuan=cap - paid,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    args = p.parse_args()
    PLAN.mkdir(parents=True, exist_ok=True)
    data, wires = prepare()
    spec = PLAN / "protocol.json"
    if args.freeze:
        if spec.exists() and read_json(spec) != data:
            raise ValueError("Frozen protocol differs")
        save(spec, data)
    else:
        if read_json(spec) != data:
            raise ValueError("Source or predeclared design differs")
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(data, wires)
