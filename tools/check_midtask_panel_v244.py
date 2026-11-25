"""Compile both groups' common decision view directly from the authenticated saved world."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_midtask_panel_v244 import PLAN, ROOT, RUN, decision, read_json, save
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.software_event_orders_v243 import orders, wire
from proworksim.software_organization_performance_v214 import BundleCache
from proworksim.software_review_handoff_v243_1 import ReviewWorld
from proworksim.storage import Store, digest, json_bytes


class ReadOnlyStore(Store):
    def lock(self):
        raise RuntimeError("Decision preparation must not write back into a checkpoint")

    def save(self, state):
        raise RuntimeError("Decision preparation must not mutate the saved world")


class Preview:
    def __init__(self, counter):
        self.counter = counter

    def decide(self, node, observer, frozen, arm):
        request = wire(self.record, orders(self.record))
        self.upper = self.counter.measure(request)["prompt_tokens"] + request["max_tokens"]
        self.options = list(frozen["options"])
        return {}, {}


def check(case, counter):
    source = ROOT / case["source"]
    proof = read_json(source / "checkpoint/manifest.json")
    world = ReviewWorld.__new__(ReviewWorld)
    world.store = ReadOnlyStore(source / "checkpoint/world")
    world.state = world.store.load()
    world.bundle_cache = BundleCache()
    if (
        proof["identity"] != case["checkpoint"]
        or proof["prefix_tokens"] != case["prefix"]
        or digest(json_bytes(world.state)) != proof["world_state_sha256"]
    ):
        raise ValueError("Saved world differs from frozen roster")
    rt = SimpleNamespace(
        prepared=SimpleNamespace(world=world),
        fixed_spec={"delivery_member": "member_001"},
        opportunities=read_json(source / "progress.json")["opportunities"],
        team_budget=SimpleNamespace(
            snapshot=lambda: dict(available_tokens=5_000_000 - case["prefix"])
        ),
    )
    with TemporaryDirectory(dir=RUN / "tmp") as directory:
        folder = Path(directory)
        preview = Preview(counter)
        decision(preview, rt, "KEEP", case, folder)
        inp = read_json(folder / "decision-input.json")
        if preview.upper > 8192:
            raise ValueError(
                f"Scheduled controller input exceeds its allocation: {case['instance']} {preview.upper}"
            )
        return dict(
            instance=case["instance"],
            checkpoint=case["checkpoint"],
            input_identity=digest((folder / "decision-input.json").read_bytes()),
            upper=preview.upper,
            routes=len(inp["routes"]),
            raw_options=preview.options,
        )


def main():
    tok = ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
    counter = OfficialDeepSeekCounter(tok, manifest_sha256=digest(tok.read_bytes()))
    (RUN / "tmp").mkdir(parents=True, exist_ok=True)
    rows = []
    for c in read_json(PLAN / "roster.json")["roster"]:
        rows.append(check(c, counter))
        print(c["index"], rows[-1]["upper"], flush=True)
    save(PLAN / "decision-preflight.json", dict(rows=rows, provider_calls=0, scoring_containers=0))


if __name__ == "__main__":
    main()
