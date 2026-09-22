"""Command-line lifecycle for synthesis, execution, validation and export."""

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from .baseline import run_baseline
from .compiler import compile_world
from .curriculum import propose_quotas, synthesize_from_quotas
from .designer import DELIVERIES, INFORMATION_MODES, design
from .experiments import run_matrix
from .kernel import World
from .learning import export_bundle
from .runtime import DeepSeekBackend, load_env, run_model
from .storage import Store, atomic_write, json_bytes, read_json
from .validation import evaluate


def parser():
    root = argparse.ArgumentParser(prog="proworksim", description="ProWorkSim v0.5.0 工作世界模拟器")
    commands = root.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="合成并编译一个独立世界")
    build.add_argument("destination")
    build.add_argument("--workflow-spec", help="JSON WorkflowSpec，替换预设节点和事件规则")
    build.add_argument("--seed", type=int, default=1)
    build.add_argument("--delivery", choices=DELIVERIES, default="continuous")
    build.add_argument("--information", choices=INFORMATION_MODES, default="mail")
    build.add_argument(
        "--topology", choices=("chain", "fork", "selective", "coordination"), default="chain"
    )
    build.add_argument("--layout", choices=("standard", "shifted"), default="standard")
    build.add_argument(
        "--scenario",
        choices=(
            "standard",
            "basis_only",
            "during_update",
            "waiting_reply",
            "during_review",
            "unavailable",
        ),
        default="standard",
    )
    run = commands.add_parser("run", help="运行或恢复目标工作人员")
    run.add_argument("world")
    run.add_argument("--provider", choices=("baseline", "deepseek"), default="baseline")
    run.add_argument("--max-turns", type=int, default=80)
    run.add_argument("--model")
    run.add_argument("--env-file", default=".env")
    run.add_argument("--thinking", action="store_true")
    run.add_argument(
        "--inject-stale-memo", action="store_true", help="基线试验中故意漏改一次备忘录"
    )
    inspect = commands.add_parser("inspect", help="查看指定角色的过滤观察")
    inspect.add_argument("world")
    inspect.add_argument("--role", default="analyst")
    act = commands.add_parser("act", help="操作者直接调用一次世界工具")
    act.add_argument("world")
    act.add_argument("action")
    act.add_argument("--arguments", default="{}", help="JSON 工具参数")
    act.add_argument("--role", default="analyst")
    grading = commands.add_parser("evaluate", help="独立验证实际提交版本")
    grading.add_argument("world")
    grading.add_argument("--work-item")
    for name, help_text in (
        ("snapshot", "保存包含后台状态的快照"),
        ("export", "导出世界、完整经历和训练适配包"),
    ):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("world")
        sub.add_argument("destination")
    restore = commands.add_parser("restore", help="从快照恢复到新路径，默认创建分支")
    restore.add_argument("snapshot")
    restore.add_argument("destination")
    restore.add_argument("--same-branch", action="store_true")
    replay = commands.add_parser("replay", help="读取记录的原始调用和工具结果，不重新采样模型")
    replay.add_argument("world")
    replay.add_argument("--output", required=True)
    experiment = commands.add_parser("experiment", help="并行运行离线机制实验矩阵")
    experiment.add_argument("destination")
    experiment.add_argument("--seeds", type=int, nargs="+", default=[11, 29])
    experiment.add_argument("--workers", type=int, default=4)
    curriculum = commands.add_parser("curriculum", help="根据开发集诊断生成可解释配额建议")
    curriculum.add_argument("worlds", nargs="+")
    curriculum.add_argument("--total", type=int, default=24)
    curriculum.add_argument("--output", required=True)
    curriculum.add_argument("--generate", help="可选：按建议并行生成新的训练集世界")
    curriculum.add_argument("--seed-start", type=int, default=1000)
    curriculum.add_argument("--workers", type=int, default=4)
    return root


def execute(args):
    if args.command == "build":
        spec = design(
            args.seed,
            args.delivery,
            args.information,
            topology=args.topology,
            layout=args.layout,
            scenario=args.scenario,
        )
        if args.workflow_spec:
            spec = replace(spec, workflow=read_json(Path(args.workflow_spec)))
        path = compile_world(spec, args.destination)
        return {"world": str(path), "observation": World(path).observe()}
    if args.command == "run":
        world = World(args.world)
        if args.provider == "baseline":
            return run_baseline(world.session(), inject_stale_memo=args.inject_stale_memo)
        load_env(args.env_file)
        return run_model(
            world,
            DeepSeekBackend(model=args.model, thinking=args.thinking),
            max_turns=args.max_turns,
            progress=lambda event: print(json.dumps(event), file=sys.stderr, flush=True),
        )
    if args.command == "inspect":
        return World(args.world).observe(args.role)
    if args.command == "act":
        return World(args.world).act(args.role, args.action, json.loads(args.arguments))
    if args.command == "evaluate":
        records = evaluate(args.world, args.work_item)
        return {"evaluations": records, "all_submissions_passed": all(r["passed"] for r in records)}
    if args.command == "snapshot":
        return {"snapshot": str(World(args.world).snapshot(args.destination))}
    if args.command == "restore":
        return World.restore(args.snapshot, args.destination, branch=not args.same_branch).observe()
    if args.command == "export":
        return export_bundle(args.world, args.destination)
    if args.command == "replay":
        state = Store(args.world).load()
        output = Path(args.output).resolve()
        world_root = Path(args.world).resolve()
        if output == world_root or world_root in output.parents or output.exists():
            raise ValueError("Replay output requires a new file outside the world")
        atomic_write(
            output,
            json_bytes(
                {
                    "mode": "recorded_observations_and_outputs",
                    "branch_id": state["branch_id"],
                    "calls": state["calls"],
                    "interactions": state["interactions"],
                }
            ),
        )
        return {"output": str(output), "calls": len(state["calls"]), "resampled": False}
    if args.command == "experiment":
        return run_matrix(args.destination, tuple(args.seeds), args.workers)
    if args.command == "curriculum":
        rows = []
        for path in args.worlds:
            state = Store(path).load()
            latest = {}
            for row in state["evaluations"]:
                latest[row["work_item_id"]] = row
            rows += [
                {**row, "split": state["project"]["split"], "episode_id": state["branch_id"]}
                for row in latest.values()
            ]
        proposal = propose_quotas(rows, args.total)
        output = Path(args.output)
        if output.exists():
            raise ValueError("Curriculum output already exists")
        atomic_write(output, json_bytes(proposal))
        if args.generate:
            return synthesize_from_quotas(proposal, args.generate, args.seed_start, args.workers)
        return proposal
    raise ValueError("Unknown command")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args)
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print(f"proworksim: {exc}", file=sys.stderr)
        return_code = 2
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return_code = 0
        if (
            args.command == "run"
            and not result.get("complete")
            and result.get("reason") != "blocked_unavailable"
        ):
            return_code = 1
        if args.command == "act" and not result.get("ok"):
            return_code = 1
        if args.command == "experiment" and result["final_passed"] != result["worlds"]:
            return_code = 1
        if args.command == "evaluate":
            latest = {}
            for row in result["evaluations"]:
                if row.get("currently_applicable", True):
                    latest[row["work_item_id"]] = row
            if not all(row["passed"] for row in latest.values()):
                return_code = 1
    if return_code:
        raise SystemExit(return_code)
    return return_code
