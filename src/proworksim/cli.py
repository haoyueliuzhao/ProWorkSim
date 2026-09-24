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
from .storage import Store, atomic_write, json_bytes, read_json, digest
from .validation import evaluate


def parser():
    root = argparse.ArgumentParser(
        prog="proworksim", description="ProWorkSim v0.11.0 工作世界模拟器"
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
    scenario = commands.add_parser("scenario-build", help="按声明部署已有模板、角色和外部事件")
    scenario.add_argument("destination")
    scenario.add_argument("--spec", required=True)
    staff = commands.add_parser("staff-run", help="给独立角色行动机会并保存真实经历")
    staff.add_argument("world")
    staff.add_argument("--output", required=True, help="世界目录外的新运行文件，包含已完成动作边界checkpoint")
    staff.add_argument("--checkpoint", help="上次staff-run输出；保持同世界、场景和策略身份")
    staff.add_argument("--max-opportunities", type=int, help="本次主episode软上限，不超过场景声明；真实前缀使用独立预算")
    staff.add_argument("--env-file", default=".env", help="模型密钥来源；不进入策略上下文或检查点")
    assessment = commands.add_parser("episode-assess", help="只读评价保存的episode结束快照")
    assessment.add_argument("world")
    assessment.add_argument("--experience", required=True, help="staff-run保存的完整运行文件")
    assessment.add_argument("--spec", help="可选JSON：work_ids、independent_targets、process_requirements")
    assessment.add_argument("--output", required=True, help="世界目录外的新评价文件")
    assessment.add_argument("--reward-spec", help="可选显式RewardSpec；原分项评价仍完整保留")
    current = commands.add_parser("world-assess", help="只读查询当前世界进度，与历史episode评价分开")
    current.add_argument("world")
    current.add_argument("--experience", required=True)
    current.add_argument("--spec")
    current.add_argument("--output", required=True)
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


def _new_episode_output(world_root, filename):
    root, requested = Path(world_root).resolve(), Path(filename)
    output = requested.resolve()
    if requested.is_symlink() or output.exists() or output == root or root in output.parents:
        raise ValueError("Episode output needs a new file outside the world")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".episode-output-probe-"):
        pass
    return output


def _episode_identity(world_root, state, manifest):
    return {"world": str(Path(world_root).resolve()), "world_id": state["world_id"],
            "instance_id": state["instance_id"], "branch_id": state["branch_id"],
            "scenario_sha256": manifest["scenario_sha256"]}


def _staff_run(args):
    from .scenarios import load_deployment, bind_runtime, ScenarioController, run_scenario

    from .episode import begin_episode, finish_episode

    load_env(args.env_file)
    root = Path(args.world).resolve()
    output = _new_episode_output(root, args.output)
    episode_root = output.with_suffix(output.suffix + ".episode")
    if episode_root.exists() or episode_root.is_symlink():
        raise ValueError("Episode boundary archive requires a new destination")
    manifest = read_json(root / "control" / "scenario.json")
    state = Store(root).load()
    identity = _episode_identity(root, state, manifest)
    maximum = manifest["spec"]["boundary"]["max_opportunities"]
    if args.max_opportunities is not None and not 0 <= args.max_opportunities <= maximum:
        raise ValueError("Soft opportunity limit must be between zero and the declared scenario limit")
    marker_path = root / "control" / "last-staff-run.json"
    saved = read_json(Path(args.checkpoint)) if args.checkpoint else None
    if saved is not None:
        if (saved.get("version") != "staff-run-v0.11"
                or any(saved.get(key) != value for key, value in identity.items())):
            raise ValueError("Staff checkpoint belongs to a different world instance or scenario")
        if marker_path.exists() and read_json(marker_path)["checkpoint_sha256"] != digest(
            json_bytes(saved["worker_checkpoint"])
        ):
            raise ValueError("Use the latest completed staff-run checkpoint for this world")
    elif marker_path.exists():
        raise ValueError("This scenario has run before; pass its latest --checkpoint to continue")
    deployment = load_deployment(root)
    if deployment.status != "ready":
        payload = {"version": "staff-run-v0.11", **identity, "status": "unbuildable",
                   "diagnostics": deployment.diagnostics}
        atomic_write(output, json_bytes(payload))
        return {"status": "unbuildable", "output": str(output), "diagnostics": deployment.diagnostics}
    runtime = bind_runtime(deployment, checkpoint=saved["worker_checkpoint"] if saved else None)
    controller = ScenarioController(
        deployment, checkpoint=saved["controller_checkpoint"] if saved else None,
        recorder=runtime.recorder,
    )
    if saved is None:
        for record in deployment.deployment_log:
            runtime.recorder.record("deployment_action", record)
    if deployment.spec["start"]["kind"] == "executed_prefix" and not deployment.prefix["prefix_executed"]:
        deployment.prepare_start(runtime, controller)
        if deployment.status != "ready":
            payload = {"version": "staff-run-v0.11", **identity, "status": "unbuildable",
                       "diagnostics": deployment.diagnostics, "prefix": deployment.prefix,
                       "worker_checkpoint": runtime.snapshot(), "controller_checkpoint": controller.snapshot()}
            atomic_write(output, json_bytes(payload))
            return {"status": "unbuildable", "output": str(output), "diagnostics": deployment.diagnostics}
    model_bindings = [(role["actor"], role["project"]) for role in deployment.spec["roles"]
                      if role["policy"] == "model"]
    selected = [wid for wid, item in deployment.world.state["work_items"].items()
                if not model_bindings or (item["owner_role"], item["project_id"]) in model_bindings]
    nodes = sorted({deployment.world.state["work_items"][wid]["node_id"] for wid in selected})
    begin_episode(deployment.world, episode_root, experience=runtime.recorder.snapshot(),
                  work_ids=[], work_nodes=nodes,
                  scenario={"spec": deployment.spec, "sha256": manifest["scenario_sha256"]},
                  policies=runtime.policy_identities,
                  parent_episode_id=saved.get("episode_id") if saved else None)
    result = run_scenario(deployment, runtime, controller, max_opportunities=args.max_opportunities)
    end = finish_episode(deployment.world, episode_root, experience=runtime.recorder.snapshot(),
                         termination={key: value for key, value in result.items()
                                      if key not in {"worker_checkpoint", "experience", "controller", "outcomes", "prefix"}})
    summary = {key: value for key, value in result.items()
               if key not in {"worker_checkpoint", "experience", "controller", "outcomes", "prefix"}}
    prefix = {key: value for key, value in deployment.prefix.items()
              if key not in {"worker_checkpoint", "opportunities"}}
    payload = {"version": "staff-run-v0.11", **identity, "result": summary,
               "episode_id": end["episode_id"], "episode_manifest": end["manifest_path"],
               "episode_manifest_sha256": digest(Path(end["manifest_path"]).read_bytes()),
               "prefix": prefix, "worker_checkpoint": runtime.snapshot(),
               "controller_checkpoint": controller.snapshot(),
               "scope": "Actual public experience is retained once in worker_checkpoint.experience; prefix full facts remain in scenario manifest. Completed-action continuation only."}
    atomic_write(output, json_bytes(payload))
    atomic_write(marker_path, json_bytes({**identity, "output": str(output),
                                        "checkpoint_sha256": digest(json_bytes(payload["worker_checkpoint"]))}))
    return {**summary, "run_id": runtime.run_id, "output": str(output),
            "episode_id": end["episode_id"], "episode_manifest": end["manifest_path"],
            "experience": runtime.recorder.summary(), "prefix": prefix}


def _current_world_assess(args):
    from .evaluation import assess_episode

    root = Path(args.world).resolve()
    output = _new_episode_output(root, args.output)
    saved = read_json(Path(args.experience))
    store = Store(root)
    state = store.load()
    manifest = read_json(root / "control" / "scenario.json")
    identity = _episode_identity(root, state, manifest)
    if saved.get("version") != "staff-run-v0.11" or any(
        saved.get(key) != value for key, value in identity.items()
    ):
        raise ValueError("Assessment experience belongs to another world or scenario")
    spec = read_json(Path(args.spec)) if args.spec else {}
    if not isinstance(spec, dict) or set(spec) - {"work_ids", "independent_targets", "process_requirements"}:
        raise ValueError("Unsupported independent assessment specification")
    result = assess_episode(store, state, saved["worker_checkpoint"]["experience"], **spec)
    atomic_write(output, json_bytes({**identity, "assessment": result}))
    return {"status": result["assessment_execution"]["status"], "output": str(output),
            "note": "Institutional progress, content, independent targets, process and incompleteness are separate; no combined success score."}


def _episode_assess(args):
    from .episode import assess_historical_episode

    root = Path(args.world).resolve()
    output = _new_episode_output(root, args.output)
    saved = read_json(Path(args.experience))
    # The live world need not still exist. Its path is only the saved identity;
    # all evaluation inputs come from the readable, closed boundary archive.
    if saved.get("version") != "staff-run-v0.11" or saved.get("world") != str(root):
        raise ValueError("Historical experience belongs to a different world path/version")
    path = Path(saved["episode_manifest"])
    if digest(path.read_bytes()) != saved["episode_manifest_sha256"]:
        raise ValueError("Episode manifest differs from the completed run")
    boundary = read_json(path)
    if (boundary.get("episode_id") != saved["episode_id"]
            or any(boundary["identity"].get(key) != saved.get(key)
                   for key in ("world_id", "instance_id", "branch_id"))
            or boundary["scenario"].get("sha256") != saved["scenario_sha256"]):
        raise ValueError("Episode identity differs from its completed staff run")
    spec = read_json(Path(args.spec)) if args.spec else {}
    if not isinstance(spec, dict) or set(spec) - {"independent_targets", "process_requirements"}:
        raise ValueError("Historical assessment cannot change its frozen responsibility")
    result = assess_historical_episode(path, **spec)
    payload = {"episode_id": saved["episode_id"], "episode_manifest": str(path), "assessment": result}
    if args.reward_spec:
        from .rewards import episode_reward

        reward_spec = read_json(Path(args.reward_spec))
        payload["reward_spec"] = reward_spec
        payload["reward"] = episode_reward(result, reward_spec)
    atomic_write(output, json_bytes(payload))
    return {"status": result["assessment_execution"]["status"], "output": str(output),
            "note": "Historical end snapshot only; current progress uses world-assess."}


def execute(args):
    if args.command == "scenario-build":
        from .scenarios import build_scenario, save_deployment

        if Path(args.destination).exists():
            raise ValueError("Scenario construction requires a new destination")
        deployment = build_scenario(read_json(Path(args.spec)), args.destination)
        manifest = save_deployment(deployment) if deployment.world is not None else None
        return {"status": deployment.status, "diagnostics": deployment.diagnostics,
                "world": str(Path(args.destination).resolve()),
                "manifest": str(manifest) if manifest is not None else None,
                "start": deployment.prefix}
    if args.command == "staff-run":
        return _staff_run(args)
    if args.command == "episode-assess":
        return _episode_assess(args)
    if args.command == "world-assess":
        return _current_world_assess(args)
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
        if args.command in {"scenario-build", "staff-run", "episode-assess", "world-assess"} and result.get("status") in {
            "unbuildable", "controller_rejected", "environment_error", "policy_error", "evaluator_error",
            "model_service_error", "model_format_error", "model_budget_exhausted", "model_usage_missing",
            "source_unavailable"
        }:
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
