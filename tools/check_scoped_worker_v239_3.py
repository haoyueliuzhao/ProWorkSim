"""Restore the first registered Worker pair locally, stopping before each provider request."""

from pathlib import Path
import sys
import subprocess
import argparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_scoped_obligations_v239_3 import PLAN, RUN, prior, first, repaired, read_json
from run_repaired_osa_pair_v233 import episode_module, EvidenceFollowupExecution, clone_function
from proworksim.software_benchmark_candidates_v054 import checked
from run_offline_scorer_v096 import launch_spec


def main(only_arm):
    result = read_json(PLAN / "results.json")
    if not result["compiled_gate"]:
        raise ValueError("Decision gate closed")
    site = "q07"
    row = next(s for s in read_json(prior.previous.PLAN / "panel.json") if s["id"] == site)
    record = next(
        r for r in result["records"] if r["id"] == site and r["arm"] == "FIX" and r["repeat"] == 1
    )
    proposal = repaired.parse(row, read_json(checked(record["response"])))
    compiled = repaired.compile_decision(row, proposal)
    summary = {}
    for arm in ("KEEP", "OSA"):
        if only_arm and arm != only_arm:
            continue

        class Replay(EvidenceFollowupExecution):
            def decide(self, node, observer, frozen, unused_arm):
                if (
                    frozen["graph"] != row["graph"]
                    or frozen["options"] != row["options"]
                    or row["available_tokens"]
                    != self.runtime.team_budget.snapshot()["available_tokens"]
                    or observer != row["observer"]
                ):
                    raise ValueError("Frozen graph, budget or observer differs")
                if arm == "KEEP":
                    return super().decide(node, observer, frozen, "KEEP")
                self.native_limit -= record["input"] + record["output"]
                self.runtime.team_budget.native_allocation = self.native_limit
                commands = dict(zip(row["evidence"], row["provenance"]["commands"]))
                authorized = {v["command_id"]: k for k, v in frozen["evidence"].items()}
                choice = dict(
                    option=compiled["option"],
                    evidence=[authorized[commands[k]] for k in proposal["basis"]],
                    reason=proposal["reason"],
                )
                activation = self.activate(node, observer, frozen, choice)
                binding = repaired.dispatch(row, compiled, activation["after"])
                self.runtime.policies[binding["actor"]].conversation.send_message(
                    "Immediate work under the active organization: "
                    + binding["action"]
                    + " for "
                    + binding["package"]
                    + ". Reassess on new evidence."
                )
                return activation, dict(source="v239.3 first registered response", binding=binding)

        out = (
            RUN
            / ("worker-rehearsal" if arm == "KEEP" else "worker-rehearsal-isolated")
            / "Sphinx-9591"
            / arm
        )
        if not (out / "result.json").exists() and not only_arm:
            command, env = launch_spec([str(Path(__file__).resolve()), "--arm", arm])
            subprocess.run(command, env=env, check=True)
        if not (out / "result.json").exists():
            fn = episode_module.episode
            clone_function(fn, {**fn.__globals__, "OrganizationExecution": Replay})(
                1, arm, out, True, slot_namespace="v239.3-rehearsal"
            )
        res = read_json(out / "result.json")
        summary[arm] = {
            k: res[k]
            for k in (
                "status",
                "first_member",
                "first_request",
                "option",
                "checkpoint",
                "available_at_start",
                "error",
                "provider_calls",
            )
            if k in res
        }
        if res.get("checkpoint") and res["checkpoint"] != row["provenance"]["checkpoint"]:
            raise ValueError("Different checkpoint")
    if only_arm:
        return
    first.save(
        PLAN / "worker-rehearsal.json",
        dict(
            site=site,
            expected_actor=compiled["execution"]["actor"],
            expected_action=compiled["execution"]["action"],
            branches=summary,
            matches_request=summary["OSA"].get("first_member") == compiled["execution"]["actor"],
            provider_calls=0,
            completed_worker_pairs=0,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=("KEEP", "OSA"))
    main(parser.parse_args().arm)
