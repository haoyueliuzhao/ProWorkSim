"""Command-line lifecycle for synthesis, execution, validation and export."""

import argparse
import json
import sys
import tempfile
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
    root = argparse.ArgumentParser(
        prog="proworksim", description="ProWorkSim v0.9.0 工作世界模拟器"
    )
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
    create = commands.add_parser("world-create", help="从主体和世界服务配置创建零项目世界")
    create.add_argument("destination")
    create.add_argument("--spec", required=True)
    load = commands.add_parser("project-load", help="向已有世界原子装载项目包")
    load.add_argument("world")
    load.add_argument("package")
    load.add_argument("--actor", required=True)
    for name in ("world-act", "world-inspect", "world-tools", "world-worker"):
        cmd = commands.add_parser(name, help="在可信身份与项目范围内操作或观察 World Core")
        cmd.add_argument("world")
        cmd.add_argument("--actor", required=True)
        cmd.add_argument("--project")
        if name == "world-act":
            cmd.add_argument("action")
            cmd.add_argument("--arguments", default="{}")
            cmd.add_argument("--request-key")
        if name == "world-worker":
            cmd.add_argument("--max-actions", type=int, default=24)
            cmd.add_argument(
                "--output", required=True, help="保存真实工具定义、观察和往返的新文件，须位于世界外"
            )
    continuous = commands.add_parser(
        "world-continue", help="通过同一世界的多个公开会话持续执行有限工作"
    )
    continuous.add_argument("world")
    continuous.add_argument(
        "--ports", required=True, help='JSON 文件：label → {"actor": "主体", "project": "项目"}'
    )
    continuous.add_argument(
        "--checkpoint", help="先前 world-continue 输出或公共策略快照；仅恢复已完成 step 的显式保存边界，不提供任意进程崩溃恢复"
    )
    continuous.add_argument("--max-actions", type=int, default=40, help="本次新增工具调用的正整数预算")
    continuous.add_argument(
        "--output", required=True, help="世界目录外的新 JSON 文件；父目录须已存在，保存 result 与 checkpoint"
    )
    check = commands.add_parser("world-evaluate", help="独立检查固定提交的有限内容合同")
    check.add_argument("world")
    check.add_argument("--project", required=True)
    check.add_argument("--work", required=True)
    check.add_argument("--submission", required=True)
    recover = commands.add_parser("world-recover", help="恢复已提交文件并继续到期环境事件")
    recover.add_argument("world")
    return root


def _continue_world(args):
    """Validate configuration/checkpoint/output before opening the mutable runner."""
    from .continuous_worker import ContinuousWorker
    from .world_core import WorldCore

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result

    def load(path):
        return json.loads(Path(path).read_text(), object_pairs_hook=unique_pairs)

    if type(args.max_actions) is not int or args.max_actions < 1:
        raise ValueError("Continuous worker budget must be a positive integer")
    world_path = Path(args.world).resolve()
    requested_output = Path(args.output)
    output = requested_output.resolve()
    if (requested_output.is_symlink() or output.exists() or output == world_path
            or world_path in output.parents):
        raise ValueError("Continuous worker output needs a new path outside the world")
    if not output.parent.is_dir():
        raise ValueError("Continuous worker output parent must already exist")
    bindings = load(args.ports)
    if not isinstance(bindings, dict) or not bindings:
        raise ValueError("Ports must be a nonempty label-to-actor/project mapping")
    identities = set()
    for label, binding in bindings.items():
        if (not isinstance(label, str) or not label.strip() or not isinstance(binding, dict)
                or set(binding) != {"actor", "project"}
                or any(not isinstance(binding[field], str) or not binding[field].strip()
                       for field in ("actor", "project"))):
            raise ValueError("Every port needs a nonempty label, actor and project")
        identity = (binding["actor"], binding["project"])
        if identity in identities:
            raise ValueError("Ports must not duplicate an actor/project binding")
        identities.add(identity)

    # Store.load is read-only: a failed configuration must not trigger runner
    # recovery or rewrite mirrors before any bound session is accepted.
    state = Store(world_path).load()
    if state.get("schema_version") != WorldCore.runtime_schema:
        raise ValueError("Continuous worker requires the current WorldCore schema")
    actors = {role["role_id"] for role in state["roles"]}
    for binding in bindings.values():
        project = state["projects"].get(binding["project"])
        if binding["actor"] not in actors or project is None or binding["actor"] not in project["participants"]:
            raise ValueError("Port actor/project binding is not available in this world")
    checkpoint = None
    if args.checkpoint:
        saved = load(args.checkpoint)
        if not isinstance(saved, dict):
            raise ValueError("Checkpoint must be a JSON object")
        if "checkpoint" in saved:
            if (saved.get("world") != str(world_path) or saved.get("world_id") != state["world_id"]
                    or saved.get("ports") != bindings):
                raise ValueError("CLI checkpoint belongs to different world or port bindings")
            checkpoint = saved["checkpoint"]
        else:
            checkpoint = saved
        required = {"checkpoint_version", "port_labels", "run_id", "actions", "port_cursor",
                    "work_cursors", "tasks", "transcript", "port_counts", "steps"}
        if (not isinstance(checkpoint, dict) or set(checkpoint) != required
                or checkpoint["checkpoint_version"] != "public-continuous-worker-v0.8"
                or checkpoint["port_labels"] != list(bindings)
                or not isinstance(checkpoint["run_id"], str) or not checkpoint["run_id"]
                or not isinstance(checkpoint["transcript"], list)):
            raise ValueError("Unsupported or malformed public worker checkpoint")
        for field in ("actions", "port_cursor", "steps"):
            if type(checkpoint[field]) is not int or checkpoint[field] < 0:
                raise ValueError("Checkpoint counters must be nonnegative integers")
        for field in ("work_cursors", "port_counts"):
            values = checkpoint[field]
            if (not isinstance(values, dict) or set(values) - set(bindings)
                    or any(type(v) is not int or v < 0 for v in values.values())):
                raise ValueError("Checkpoint scheduler values are malformed")
        if not isinstance(checkpoint["tasks"], dict):
            raise ValueError("Checkpoint tasks must be a mapping")
        for key, task in checkpoint["tasks"].items():
            if (not isinstance(task, dict) or task.get("port") not in bindings
                    or not isinstance(task.get("work_id"), str)
                    or key != task["port"] + ":" + task["work_id"]
                    or type(task.get("requirement_version")) is not int
                    or not isinstance(task.get("status"), str)
                    or not isinstance(task.get("sources"), dict)
                    or not isinstance(task.get("requests"), dict)):
                raise ValueError("Checkpoint task context is malformed")
            item = state["work_items"].get(task["work_id"])
            binding = bindings[task["port"]]
            if (item is None or item["project_id"] != binding["project"]
                    or item["owner_role"] != binding["actor"]
                    or item["requirement_version"] != task["requirement_version"]):
                raise ValueError("Checkpoint task belongs to another work context")
            for source in task["sources"].values():
                if (not isinstance(source, dict) or set(source) != {"reference", "value"}
                        or not isinstance(source["reference"], dict)
                        or set(source["reference"]) != {"object_id", "version_id"}):
                    raise ValueError("Checkpoint source progress is malformed")
            for request in task["requests"].values():
                if not isinstance(request, dict) or not isinstance(request.get("route_token"), list):
                    raise ValueError("Checkpoint request progress is malformed")
            if "output" in task and (not isinstance(task["output"], dict)
                    or not {"alias", "data", "reference"} <= set(task["output"])
                    or not isinstance(task["output"]["alias"], str)
                    or not isinstance(task["output"]["data"], dict)):
                raise ValueError("Checkpoint output progress is malformed")
            if "source_error" in task and not isinstance(task["source_error"], dict):
                raise ValueError("Checkpoint source error progress is malformed")
        for index, entry in enumerate(checkpoint["transcript"]):
            if (not isinstance(entry, dict) or entry.get("port") not in bindings
                    or entry.get("sequence") != index or "value" not in entry):
                raise ValueError("Checkpoint transcript sequence or port is malformed")
            if entry.get("kind") == "observation":
                observation = entry["value"]
                if (not isinstance(observation, dict) or observation.get("world_id") != state["world_id"]
                        or observation.get("actor_id") != bindings[entry["port"]]["actor"]
                        or bindings[entry["port"]]["project"] not in observation.get("projects", {})):
                    raise ValueError("Checkpoint observation belongs to another public context")
        json_bytes(checkpoint)  # Reject nonfinite/unserializable data before any action.
        ContinuousWorker(dict.fromkeys(bindings), checkpoint=checkpoint)

    # Probe output writeability before runner recovery/actions, without leaving
    # a file or touching world persistence. This is not an arbitrary-crash claim.
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".continue-output-probe-"):
        pass
    world = WorldCore(world_path)
    sessions = {label: world.session(binding["actor"], binding["project"])
                for label, binding in bindings.items()}
    worker = ContinuousWorker(sessions, checkpoint=checkpoint)
    result = worker.run(max_actions=args.max_actions)
    payload = {"world": str(world_path), "world_id": state["world_id"], "ports": bindings,
               "result": result, "checkpoint": worker.snapshot()}
    atomic_write(output, json_bytes(payload))
    return {"status": result["status"], "actions": result["actions"], "run_id": result["run_id"],
            "output": str(output), "task_statuses": {key: task["status"] for key, task in result["tasks"].items()}}


def execute(args):
    if args.command == "world-continue":
        return _continue_world(args)
    if args.command in {
        "world-create",
        "project-load",
        "world-act",
        "world-inspect",
        "world-evaluate",
        "world-recover",
        "world-tools",
        "world-worker",
    }:
        from .world_core import WorldCore
        from .core.world import WorldSpec

        if args.command == "world-create":
            world = WorldCore.create(args.destination, WorldSpec(**read_json(Path(args.spec))))
            return {
                "world": str(world.store.root),
                "world_id": world.state["world_id"],
                "projects": [],
            }
        world = WorldCore(args.world)
        if args.command == "project-load":
            return world.session(args.actor).call(
                "install_project", package=read_json(Path(args.package))
            )
        if args.command == "world-act":
            return world.session(args.actor, args.project).call(
                args.action, request_key=args.request_key, **json.loads(args.arguments)
            )
        if args.command == "world-tools":
            return {"tools": world.session(args.actor, args.project).tools()}
        if args.command == "world-worker":
            from .public_worker import run_public_worker

            output = Path(args.output).resolve()
            if output.exists() or output == world.store.root or world.store.root in output.parents:
                raise ValueError("Worker transcript needs a new path outside the world")
            if args.max_actions < 1:
                raise ValueError("Worker budget must be positive")
            result = run_public_worker(world.session(args.actor, args.project), args.max_actions)
            atomic_write(output, json_bytes(result))
            return {key: value for key, value in result.items() if key != "transcript"} | {
                "transcript": str(output)
            }
        if args.command == "world-inspect":
            return world.session(args.actor, args.project).observe()
        if args.command == "world-recover":
            return world.recover()
        return world.evaluate_submission(args.project, args.work, args.submission)
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
        from .world_core import WorldCore

        runtime = (
            WorldCore if Store(args.world).load().get("runtime_kind") == "world_core" else World
        )
        return {"snapshot": str(runtime(args.world).snapshot(args.destination))}
    if args.command == "restore":
        from .world_core import WorldCore

        if Store(args.snapshot).load().get("runtime_kind") == "world_core":
            world = WorldCore.restore(args.snapshot, args.destination, branch=not args.same_branch)
            return {
                "world_id": world.state["world_id"],
                "branch_id": world.state["branch_id"],
                "world": str(world.store.root),
            }
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
