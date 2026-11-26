"""One new P2.1 and P2.2 call at each of the fourteen archived decision inputs."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_prompt_panel_v248_9 as panel
from proworksim import software_organization_intent_v248_6 as compiler
from proworksim import software_organization_intent_v248_7 as baseline
from proworksim.storage import read_json

first = panel.first
PLAN = panel.PLAN.parent.parent / "p21-p22-pairs-r1/protocol.json"
RUN = panel.RUN.parent / "p21-p22-pairs-r1"
MODELS = {"P2.1": baseline, "P2.2": panel.policy}
ALLOWANCE = 20_000


def register():
    sites = []
    for n, r in enumerate(read_json(PLAN.parent.parent / "intent-replay-r1/results.json")["cases"]):
        original = (panel.ROOT / r["source"]).with_name("request.json")
        sites.append(
            dict(
                index=n,
                instance=r["instance"],
                condition=r["arm"],
                opportunity=r["opportunity"],
                source=first.old.reference(original),
            )
        )
    first.freeze(
        PLAN,
        dict(
            sites=sites,
            order="Both prompts once per exact archived input, alternating within-site call order by index, no later score or history. All 14 P1 decision sites drawn from two tasks; no independence assumption.",
            limit_per_call=ALLOWANCE,
            endpoints="distinguish invalid call from executable intent; A1 assessment grounded if distinct executed receipts, targets and code versions are supported by the public incident; record costs and paired disagreements. Decisions only; no retroactive effects on tasks.",
            sources=[
                first.old.reference(p)
                for p in (
                    Path(__file__),
                    Path(baseline.__file__),
                    Path(panel.policy.__file__),
                    Path(compiler.__file__),
                )
            ],
        ),
    )


def names(site):
    return {key: f"v248.9-probe:{site['index']}:{key}" for key in MODELS}


def call_site(site):
    state = json.loads(
        read_json(first.old.checked(site["source"]))["payload"]["wire"]["messages"][1]["content"]
    )
    manifest = panel.ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
    counter = first.M.OfficialDeepSeekCounter(
        manifest, manifest_sha256=first.old.digest(manifest.read_bytes())
    )
    meter = first.PairedLedger.load(first.AUTH)
    for key in list(MODELS) if site["index"] % 2 == 0 else list(reversed(MODELS)):
        slot = names(site)[key]
        out = RUN / str(site["index"]) / key
        if out.exists():
            continue
        out.mkdir(parents=True)
        wire = MODELS[key].wire(state)
        if counter.measure(wire)["prompt_tokens"] + wire["max_tokens"] > ALLOWANCE:
            raise ValueError("Call allowance insufficient")
        meter.admit(slot, ALLOWANCE)
        try:
            transport = first.M.DirectHTTPS(
                first.M.load_api_key(panel.ROOT / ".env"), timeout_seconds=1800
            )
            backend = first.M.Backend(
                out / "api", meter, slot, counter, transport, {"activate_organization"}
            )
            body = backend.post(
                "/chat/completions",
                dict(
                    team_slot_id=slot,
                    request_id=slot,
                    member_id="member_001",
                    usage_id="agent",
                    wire=wire,
                ),
            )
            (call,) = body["choices"][0]["message"].get("tool_calls") or []
            if call["function"]["name"] != "activate_organization":
                raise ValueError("Wrong tool")
            intent = compiler.unpack(call["function"]["arguments"])
            first.save(out / "intent.json", intent)
            p = compiler.compile_intent(state, intent)
            rec = dict(
                status="accepted",
                assessment=p["assessment"],
                decision=p["decision"],
                membership=p["membership_decision"]["action"],
                ops=p["organization_patch"]["operations"],
            )
        except Exception as e:
            rec = dict(status="error", reason=str(e).splitlines()[0][:240] or type(e).__name__)
        finally:
            meter.close(slot)
        first.save(out / "record.json", rec)


def run():
    spec = read_json(PLAN)
    for src in spec["sources"]:
        first.old.checked(src)
    meter = first.PairedLedger.load(first.AUTH)
    with meter.db() as db:
        if db.execute("select value from meta where key='cap'").fetchone() != (str(meter.cap),):
            raise ValueError("Ledger cap")
        expected = [
            (s, "v248.9-probe", ALLOWANCE) for site in spec["sites"] for s in names(site).values()
        ]
        existing = db.execute(
            "select slot,block_id,token_limit from block_slots where block_id='v248.9-probe'"
        ).fetchall()
        if not existing:
            paid = db.execute(
                "select coalesce(sum(cost),0) from requests where slot in (select id from slots where status='closed')"
            ).fetchone()[0]
            active = db.execute(
                "select coalesce(sum(hold),0) from slots where status!='closed'"
            ).fetchone()[0]
            pending = db.execute(
                "select coalesce(sum(token_limit),0) from block_slots where status='pending'"
            ).fetchone()[0]
            if paid + active + (pending + ALLOWANCE * len(expected)) * 8000 > meter.cap:
                raise ValueError("Not enough funds for the whole diagnostic")
            db.executemany("insert into block_slots values(?,?,?,'pending')", expected)
        elif sorted(existing) != sorted(expected):
            raise ValueError("Frozen probe mismatch")
    with ThreadPoolExecutor(4) as pool:
        for _ in pool.map(call_site, spec["sites"]):
            pass


if __name__ == "__main__":
    if sys.argv[1:] == ["--freeze"]:
        register()
    else:
        run()
