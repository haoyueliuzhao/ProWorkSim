"""Read-only, task- and repository-aware analysis of the frozen v053 inventory."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random

VERSION = "software-panel-report-v053-v1"
BOOTSTRAP_SEED = 202610200531
BOOTSTRAP_DRAWS = 20_000
Z95 = 1.959963984540054


def wilson95(successes, total):
    """Working independent-Bernoulli interval, not a repository-cluster claim."""
    if not 0 <= successes <= total or total <= 0:
        raise ValueError("Wilson interval requires a nonempty valid binomial count")
    p = successes / total
    denominator = 1 + Z95**2 / total
    center = (p + Z95**2 / (2 * total)) / denominator
    half = Z95 * math.sqrt(p * (1 - p) / total + Z95**2 / (4 * total**2)) / denominator
    return [0.0 if successes == 0 else max(0.0, center - half),
            1.0 if successes == total else min(1.0, center + half)]


def completion_summary(values):
    counts = Counter(values)
    total, success, failed, unknown = len(values), counts[1], counts[0], counts[None]
    if not total or success + failed + unknown != total:
        raise ValueError("Outcomes must be integer zero/one or null")
    return {
        "denominator": total, "successes": success, "failures": failed, "unknown": unknown,
        "completion_rate": success / total if not unknown else None,
        "identification_bounds": [success / total, (success + unknown) / total],
        "wilson95_working_independence": wilson95(success, total) if not unknown else None,
        "known_subset_rate": None,
    }


def _quantile(sorted_values, fraction):
    index = (len(sorted_values) - 1) * fraction
    low, high = math.floor(index), math.ceil(index)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (index - low)


def cluster_bootstrap(repository_values):
    """Resample whole equal-size repository clusters; keep their ten tasks together."""
    if len(repository_values) != 20 or any(len(values) != 10 for values in repository_values):
        raise ValueError("Repository bootstrap requires the declared 20 x 10 panel")
    metadata = {
        "method": "percentile_bootstrap_resampling_whole_repositories_with_replacement",
        "seed": BOOTSTRAP_SEED, "draws": BOOTSTRAP_DRAWS, "clusters": 20,
        "interval95": None,
        "limitations": (
            "Only 20 selected repository clusters; percentile coverage can be poor. "
            "The interval describes this balanced panel design and is not an "
            "unconditional SWE-smith population or SWE-bench Verified interval."
        ),
    }
    if any(value is None for values in repository_values for value in values):
        return {**metadata, "unavailable_reason": "at_least_one_main_outcome_unknown"}
    means = [sum(values) / 10 for values in repository_values]
    rng = random.Random(BOOTSTRAP_SEED)
    draws = sorted(sum(means[rng.randrange(20)] for _ in range(20)) / 20
                   for _ in range(BOOTSTRAP_DRAWS))
    return {**metadata, "interval95": [_quantile(draws, 0.025), _quantile(draws, 0.975)],
            "unavailable_reason": None}


def _validate_panel(panel):
    slots, tasks = panel["slots"], panel["tasks"]
    by_id = {row["slot_id"]: row for row in slots}
    task_map = {row["task_id"]: row for row in tasks}
    main = [row for row in slots if row["repeat_index"] == 1]
    repeat_ids = set(panel["repeat_task_ids"])
    repetitions = defaultdict(list)
    for row in slots:
        repetitions[row["task_id"]].append(row["repeat_index"])
    repo_counts = Counter(row["repository"] for row in tasks)
    if (len(by_id) != len(slots) or len(slots) != 280 or len(main) != 200
            or len(task_map) != len(tasks) or len(tasks) != 200
            or len({row["seed"] for row in slots}) != 280
            or {row["task_id"] for row in main} != set(task_map)
            or set(panel["main_task_ids"]) != set(task_map)
            or len(panel["main_task_ids"]) != 200 or len(repeat_ids) != 40
            or len(panel["repeat_task_ids"]) != 40 or not repeat_ids <= set(task_map)
            or len(repo_counts) != 20 or set(repo_counts.values()) != {10}
            or any(sorted(indices) != ([1, 2, 3] if task_id in repeat_ids else [1])
                   for task_id, indices in repetitions.items())):
        raise ValueError("Require exactly 200 distinct tasks, 20 x 10 repositories, and 40 x 3 repeats")
    return by_id, task_map


def _nonnegative_int(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _accounting(observation):
    account = observation.get("accounting")
    if not isinstance(account, dict) or account.get("known_actual_tokens") is None:
        return {
            "known_actual_tokens": None, "complete_actual_tokens": None,
            "uncertain_reservation_tokens": None, "accounting_present": False,
            "prompt_tokens": None, "completion_tokens": None,
            "started_generations": None, "complete_generations": None,
        }
    known = _nonnegative_int(account["known_actual_tokens"], "known_actual_tokens")
    reserve = account["uncertain_reservation_tokens"]
    if reserve is not None:
        _nonnegative_int(reserve, "uncertain_reservation_tokens")
    total = account.get("complete_actual_tokens")
    if total is not None and (type(total) is not int or total != known or reserve != 0):
        raise ValueError("Complete actual accounting conflicts with known usage/reservation")
    calls = account.get("actual_calls")
    prompt = completion = None
    if calls is not None:
        if len({call["attempt_id"] for call in calls}) != len(calls):
            raise ValueError("A native generation receipt cannot be counted twice")
        prompt = sum(_nonnegative_int(call["usage"]["prompt_tokens"], "prompt_tokens")
                     for call in calls)
        completion = sum(_nonnegative_int(call["usage"]["completion_tokens"], "completion_tokens")
                         for call in calls)
        if prompt + completion != known:
            raise ValueError("Actual generation receipts do not match the known token subtotal")
    return {
        "known_actual_tokens": known, "complete_actual_tokens": total,
        "uncertain_reservation_tokens": reserve, "accounting_present": True,
        "prompt_tokens": prompt, "completion_tokens": completion,
        "started_generations": account.get("started_generations"),
        "complete_generations": account.get("complete_generations"),
    }


def _empty_cost(*, known_zero):
    return {
        "known_actual_tokens": 0 if known_zero else None,
        "complete_actual_tokens": 0 if known_zero else None,
        "uncertain_reservation_tokens": 0 if known_zero else None,
        "accounting_present": known_zero,
        "prompt_tokens": 0 if known_zero else None,
        "completion_tokens": 0 if known_zero else None,
        "started_generations": 0 if known_zero else None,
        "complete_generations": 0 if known_zero else None,
    }


def _token_summary(episodes):
    known = sum(row["tokens"]["known_actual_tokens"] or 0 for row in episodes)
    settled = all(row["tokens"]["complete_actual_tokens"] is not None for row in episodes)
    unknown_reserve = [row["slot_id"] for row in episodes
                       if row["tokens"]["uncertain_reservation_tokens"] is None]
    all_closed = all(row["status"] in ("complete", "technical_unknown") for row in episodes)
    full_values = (sorted(row["tokens"]["complete_actual_tokens"] for row in episodes)
                   if settled and all_closed else None)
    return {
        "known_actual_tokens": known,
        "complete_observed_actual_tokens": known if settled else None,
        "full_planned_inventory_actual_tokens": known if settled and all_closed else None,
        "known_uncertain_reservation_tokens": sum(
            row["tokens"]["uncertain_reservation_tokens"] or 0 for row in episodes),
        "reservation_unknown_slot_ids": unknown_reserve,
        "accounting_unknown_slot_ids": [row["slot_id"] for row in episodes
                                       if not row["tokens"]["accounting_present"]],
        "unsettled_slot_ids": [row["slot_id"] for row in episodes
                              if row["tokens"]["complete_actual_tokens"] is None],
        "prompt_tokens": (sum(row["tokens"]["prompt_tokens"] for row in episodes)
                          if all(row["tokens"]["prompt_tokens"] is not None for row in episodes)
                          else None),
        "completion_tokens": (sum(row["tokens"]["completion_tokens"] for row in episodes)
                              if all(row["tokens"]["completion_tokens"] is not None
                                     for row in episodes) else None),
        "reservation_is_actual_usage": False,
        "environment_cpu_and_gpu_residency_included": False,
        "per_episode_final_actual_distribution": {
            "planned_episode_count": len(episodes),
            "complete_episode_cost_count": sum(
                row["status"] in ("complete", "technical_unknown")
                and row["tokens"]["complete_actual_tokens"] is not None for row in episodes),
            "minimum": full_values[0] if full_values else None,
            "q25": _quantile(full_values, 0.25) if full_values else None,
            "median": _quantile(full_values, 0.5) if full_values else None,
            "q75": _quantile(full_values, 0.75) if full_values else None,
            "q95": _quantile(full_values, 0.95) if full_values else None,
            "maximum": full_values[-1] if full_values else None,
            "mean": sum(full_values) / len(full_values) if full_values else None,
            "scope": "all specified episodes; null until every final episode cost is known",
        },
    }


def recover_native_accounting(attempt_path, *, slot_id):
    """Read only the original provider receipts for an unclosed host attempt.

    No provider/runtime import is needed. Missing receipt inventories stay null;
    prepared-only zero usage requires a bound explicit generation_started=false.
    """
    calls = Path(attempt_path) / "resident/calls"
    records, references, errors = {}, [], []
    for suffix in ("prepared", "started", "complete"):
        values = {}
        for path in sorted(calls.glob(f"*-{suffix}.json")):
            content = path.read_bytes()
            references.append({"path": str(path), "sha256": hashlib.sha256(content).hexdigest(),
                               "bytes": len(content)})
            key = path.name.removesuffix(f"-{suffix}.json")
            try:
                decoded = json.loads(content)
                if not isinstance(decoded, dict):
                    raise ValueError("Provider receipt must be an object")
                values[key] = decoded
            except (ValueError, TypeError):
                errors.append(key + ":unreadable_" + suffix)
        records[suffix] = values
    prepared, started, complete = (records[key] for key in ("prepared", "started", "complete"))
    recovery = {"method": "read_only_original_native_receipts", "references": references,
                "slot_id": slot_id, "integrity_errors": errors}
    if not references:
        return None, {**recovery, "reason": "provider_receipts_missing_not_zero_usage"}
    expected_window = "software-panel-v053:" + slot_id
    valid_started, valid_prepared = {}, {}
    for key, value in prepared.items():
        if (value.get("attempt_id") == key and value.get("online_window_id") == expected_window
                and value.get("generation_started") is False
                and type(value.get("reserved_maximum_tokens")) is int
                and value["reserved_maximum_tokens"] > 0):
            valid_prepared[key] = value
        else:
            errors.append(key + ":invalid_preparation_binding")
    for key, value in started.items():
        preparation = valid_prepared.get(key)
        if (preparation is not None and value.get("attempt_id") == key
                and value.get("generation_started") is True
                and all(value.get(field) == preparation.get(field) for field in (
                    "native_input", "actor_identity", "online_window_id", "reserved_maximum_tokens"))):
            valid_started[key] = value
        else:
            errors.append(key + ":invalid_generation_start_binding")
    actual_calls, actual, uncertain = [], 0, 0
    for key, value in complete.items():
        before = valid_started.get(key)
        usage = value.get("usage", {})
        input_value = value.get("input", {})
        if (before is None or value.get("attempt_id") != key
                or input_value != before.get("native_input")
                or value.get("actor_identity") != before.get("actor_identity")
                or any(type(usage.get(field)) is not int for field in
                       ("prompt_tokens", "completion_tokens", "total_tokens"))
                or usage["prompt_tokens"] != len(input_value.get("input_ids", []))
                or usage["completion_tokens"] != len(value.get("output_ids", []))
                or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]
                or not 0 < usage["total_tokens"] <= before["reserved_maximum_tokens"]):
            errors.append(key + ":invalid_completion_binding_or_usage")
            continue
        actual += usage["total_tokens"]
        actual_calls.append({"attempt_id": key, "usage": usage})
    settled_ids = {row["attempt_id"] for row in actual_calls}
    for key, before in valid_started.items():
        if key not in settled_ids:
            uncertain += before["reserved_maximum_tokens"]
    if errors and not actual_calls:
        return None, {**recovery, "reason": "no_valid_actual_usage_or_explicit_zero_proof"}
    account = {
        "known_actual_tokens": actual, "uncertain_reservation_tokens": uncertain,
        "complete_actual_tokens": actual if not uncertain and not errors else None,
        "started_generations": len(started), "complete_generations": len(actual_calls),
        "actual_calls": actual_calls, "all_started_settled": not uncertain and not errors,
        "integrity_errors": errors,
    }
    if errors:
        account["uncertain_reservation_tokens"] = None
        recovery["known_valid_unsettled_reservation_tokens"] = uncertain
    return account, recovery


def build_report(panel, observations, *, panel_sha256, started_slot_ids=(), active_slot_ids=()):
    """Use each formal slot at most once; never select a completed-only denominator.

    Observations are verified worker report/interruption dictionaries with an
    added ``panel_sha256`` identity. Resource-wait attempts are zero-model events,
    recorded separately; they cannot replace or duplicate entered model episodes.
    """
    rows, task_map = _validate_panel(panel)
    observations = list(observations)
    started, active = set(started_slot_ids), set(active_slot_ids)
    if not active <= started or not started <= set(rows):
        raise ValueError("Active/entered slots must belong to the frozen inventory")
    formal, waits = {}, Counter()
    run_plan_digests = {row["_run_plan_sha256"] for row in observations
                        if row.get("_run_plan_sha256")}
    if len(run_plan_digests) > 1:
        raise ValueError("Different frozen run configurations must be reported separately")
    for observation in observations:
        row = observation["row"]
        slot_id = row["slot_id"]
        if (slot_id not in rows or row != rows[slot_id]
                or observation.get("panel_sha256") != panel_sha256):
            raise ValueError("Observation must match the full frozen slot and panel identity")
        if observation.get("status") == "resource_wait":
            if (observation.get("loader_not_entered") is not True
                    or observation.get("model_loader_entered") is not False
                    or observation.get("model_calls") != 0
                    or observation.get("known_actual_tokens") != 0
                    or observation.get("resident_exists") is not False):
                raise ValueError("Resource retries must prove zero model entry and zero usage")
            waits[slot_id] += 1
            continue
        if slot_id in formal:
            raise ValueError("Duplicate formal observation; do not replay or select an outcome")
        formal[slot_id] = observation
    episodes = []
    for slot_id, row in rows.items():
        observation = formal.get(slot_id)
        value, failure, reasons = None, None, []
        if observation is None:
            if slot_id in active:
                status = "running"
            elif slot_id in started:
                status, reasons = "technical_unknown", ["entered_without_closed_report"]
            else:
                status = "resource_wait" if waits[slot_id] else "not_started"
            tokens = _empty_cost(known_zero=slot_id not in started)
        else:
            status = observation["status"]
            if status not in ("complete", "technical_unknown"):
                raise ValueError("A closed worker must be complete or technical_unknown")
            value = observation.get("R_code")
            verdict = observation.get("verdict", {})
            tokens = _accounting(observation)
            if status == "complete":
                if type(value) is not int or value not in (0, 1):
                    raise ValueError("Completed outcomes require exact zero/one")
                if tokens["complete_actual_tokens"] is None:
                    raise ValueError("A complete worker cannot conceal unsettled actual usage")
                if value == 0:
                    failure = verdict.get("failure_type") or "model_incomplete_unspecified"
            else:
                if value is not None:
                    raise ValueError("Technical unknown cannot be recoded as model success/failure")
                reasons = verdict.get("reasons") or [
                    (observation.get("error") or {}).get("type", "technical_unknown_unspecified")]
        episodes.append({
            **row, "repository": task_map[row["task_id"]]["repository"],
            "status": status, "R_code": value, "model_failure_type": failure,
            "technical_reasons": reasons, "tokens": tokens,
            "resource_wait_attempt_count": waits[slot_id],
            "source_ref": observation.get("_source_ref") if observation else None,
            "accounting_recovery": observation.get("accounting_recovery") if observation else None,
        })
    episode_map = {(row["task_id"], row["repeat_index"]): row for row in episodes}
    main = [row for row in episodes if row["repeat_index"] == 1]
    repeat_ids = panel["repeat_task_ids"]
    task_records, repository_records = [], []
    for task_id in panel["main_task_ids"]:
        replications = [episode_map[(task_id, index)] for index in
                        ((1, 2, 3) if task_id in set(repeat_ids) else (1,))]
        task_records.append({
            "task_id": task_id, "repository": task_map[task_id]["repository"],
            "mutation_family": task_map[task_id].get("mutation_family"),
            "in_repeat_subset": task_id in set(repeat_ids),
            "main_R_code": replications[0]["R_code"],
            "outcomes_in_preregistered_order": [row["R_code"] for row in replications],
            "slot_ids": [row["slot_id"] for row in replications],
            "tokens": _token_summary(replications),
        })
    repo_values = []
    for repository in sorted({row["repository"] for row in main}):
        main_rows = [row for row in main if row["repository"] == repository]
        repo_rows = [row for row in episodes if row["repository"] == repository]
        values = [row["R_code"] for row in main_rows]
        repo_values.append(values)
        repository_records.append({
            "repository": repository, "main": completion_summary(values),
            "main_slot_ids": [row["slot_id"] for row in main_rows],
            "all_episode_state_counts": dict(sorted(Counter(
                row["status"] for row in repo_rows).items())),
            "tokens": _token_summary(repo_rows),
        })
    rounds = []
    for index in (1, 2, 3):
        sample = [episode_map[(task_id, index)] for task_id in repeat_ids]
        rounds.append({"repeat_index": index, **completion_summary(
            [row["R_code"] for row in sample])})
    histogram = {f"{count}/3": 0 for count in range(4)}
    unknown_tasks, confirmed_mixed = [], 0
    pair_disagreements = 0
    for task_id in repeat_ids:
        outcomes = [episode_map[(task_id, index)]["R_code"] for index in (1, 2, 3)]
        observed = {value for value in outcomes if value is not None}
        confirmed_mixed += observed == {0, 1}
        if None in outcomes:
            unknown_tasks.append(task_id)
        else:
            histogram[f"{sum(outcomes)}/3"] += 1
            pair_disagreements += sum(outcomes[left] != outcomes[right]
                                      for left, right in ((0, 1), (0, 2), (1, 2)))
    potentially_mixed = confirmed_mixed + sum(
        len({episode_map[(task_id, index)]["R_code"] for index in (1, 2, 3)} - {None}) < 2
        for task_id in unknown_tasks)
    main_summary = completion_summary([row["R_code"] for row in main])
    return {
        "version": VERSION, "panel_sha256": panel_sha256,
        "run_plan_sha256": next(iter(run_plan_digests), None),
        "estimand": "single_run_completion_on_the_fixed_repository_stratified_panel",
        "main": {**main_summary, "preregistered_run": 1,
                 "repository_cluster_bootstrap": cluster_bootstrap(repo_values)},
        "repeat_diagnostic": {
            "task_count": 40, "rounds": rounds, "success_count_histogram": histogram,
            "unknown_three_run_task_count": len(unknown_tasks),
            "unknown_three_run_task_ids": unknown_tasks,
            "confirmed_mixed_outcome_task_count": confirmed_mixed,
            "mixed_outcome_task_fraction": confirmed_mixed / 40 if not unknown_tasks else None,
            "mixed_outcome_task_fraction_bounds": [confirmed_mixed / 40, potentially_mixed / 40],
            "pairwise_disagreement_rate": pair_disagreements / 120 if not unknown_tasks else None,
            "pairwise_denominator_when_complete": 120,
            "stability_certified": False, "pass_at_three_used_as_main": False,
        },
        "inventory": {
            "distinct_tasks": 200, "repositories": 20, "planned_episodes": 280,
            "state_counts": dict(sorted(Counter(row["status"] for row in episodes).items())),
            "main_state_counts": dict(sorted(Counter(row["status"] for row in main).items())),
            "resource_wait_attempts": sum(waits.values()),
            "all_episodes_closed": all(row["status"] in ("complete", "technical_unknown")
                                       for row in episodes),
        },
        "tokens": {
            "all_280_slots": _token_summary(episodes),
            "main_200_slots": _token_summary(main),
            "extra_80_repeat_slots": _token_summary(
                [row for row in episodes if row["repeat_index"] != 1]),
            "per_episode_cap": 500_000, "all_episode_cap": 140_000_000,
        },
        "failure_distribution": {
            "known_model_failures": dict(sorted(Counter(
                row["model_failure_type"] for row in episodes if row["R_code"] == 0).items())),
            "main_200_known_model_failures": dict(sorted(Counter(
                row["model_failure_type"] for row in main if row["R_code"] == 0).items())),
            "extra_80_known_model_failures": dict(sorted(Counter(
                row["model_failure_type"] for row in episodes
                if row["repeat_index"] != 1 and row["R_code"] == 0).items())),
            "technical_unknown_episodes": sum(row["status"] == "technical_unknown" for row in episodes),
            "technical_reason_counts_nonexclusive": dict(sorted(Counter(
                reason for row in episodes for reason in row["technical_reasons"]).items())),
            "successful_episodes": sum(row["R_code"] == 1 for row in episodes),
            "unstarted_or_waiting_episodes": sum(
                row["status"] in ("not_started", "resource_wait") for row in episodes),
            "running_episodes": sum(row["status"] == "running" for row in episodes),
        },
        "repositories": repository_records, "tasks": task_records, "episodes": episodes,
        "interpretation": {
            "all_280_pooled_completion_rate": None,
            "repeated_runs_are_independent_tasks": False,
            "wilson_scope": "Working independent-Bernoulli description; ignores repository clustering.",
            "unknown_bounds_are_confidence_intervals": False,
            "natural_swesmith_population_mean": False, "swebench_verified_score": False,
            "training_or_independent_confirmation_result": False,
        },
    }


def markdown(report):
    main, repeat, inventory = report["main"], report["repeat_diagnostic"], report["inventory"]

    def rate(value):
        return "null（尚有未知）" if value is None else f"{value:.4f}"

    lines = [
        "# v053：200 题主面板与 40 题重复诊断", "",
        f"Panel SHA-256：`{report['panel_sha256']}`。本报告只读取既有回执，不执行模型或测试。",
        "",
        f"主结果固定使用 200 题第一次预定运行：成功 {main['successes']}，失败 {main['failures']}，"
        f"未知 {main['unknown']}；完成率 **{rate(main['completion_rate'])}**。",
        f"未知结果识别界限为 {main['identification_bounds']}，该界限不是置信区间。",
        f"Wilson 95% 区间：{main['wilson95_working_independence']}；"
        f"仓库整簇 bootstrap 95% 区间：{main['repository_cluster_bootstrap']['interval95']}。",
        "Wilson 使用独立 Bernoulli 工作假设；整簇 bootstrap 保留任务归属，只有 20 个仓库簇，"
        "区间覆盖可能不理想。两者均不支持 SWE-smith 自然总体或 SWE-bench Verified 外推。",
        "", "## 预选 40 题的重复诊断", "",
        "| 预定轮次 | 成功 | 失败 | 未知 | 40 题完成率 |", "| --- | ---: | ---: | ---: | --- |",
    ]
    for row in repeat["rounds"]:
        lines.append(f"| {row['repeat_index']} | {row['successes']} | {row['failures']} | "
                     f"{row['unknown']} | {rate(row['completion_rate'])} |")
    lines.extend([
        "", f"三轮均已知任务的成功次数计数：{repeat['success_count_histogram']}；"
        f"三轮记录不完整任务 {repeat['unknown_three_run_task_count']}，单独保留。",
        f"已观察到成功／失败翻转的任务 {repeat['confirmed_mixed_outcome_task_count']}；"
        f"40 题翻转比例 {rate(repeat['mixed_outcome_task_fraction'])}，"
        f"识别界限 {repeat['mixed_outcome_task_fraction_bounds']}。",
        "三次重复只是有限波动诊断，不认证稳定性；不把 pass@3 或 280 回合混合平均当作主完成率。",
        "", "## 全部库存与实际费用", "",
        f"全部 280 回合状态：`{inventory['state_counts']}`。"
        f"零模型资源等待尝试 {inventory['resource_wait_attempts']} 次。",
        "| 范围 | 已知实际 token | 完整已观测实际 token | 不确定预约 token |",
        "| --- | ---: | --- | ---: |",
    ])
    for key, label in (("main_200_slots", "主面板 200"),
                       ("extra_80_repeat_slots", "额外重复 80"), ("all_280_slots", "全部 280")):
        token = report["tokens"][key]
        lines.append(f"| {label} | {token['known_actual_tokens']} | "
                     f"{token['complete_observed_actual_tokens']} | "
                     f"{token['known_uncertain_reservation_tokens']} |")
    lines.extend([
        "", "预算上限 140,000,000 输入＋输出 token；预约不冒称实际消耗，"
        "环境准备、CPU 测试、GPU 驻留另计。未闭合库存的最终总费用仍为 null。",
        f"已知模型失败类型：`{report['failure_distribution']['known_model_failures']}`。",
        f"技术未知回合：{report['failure_distribution']['technical_unknown_episodes']}；"
        f"原因（可多标签）：`{report['failure_distribution']['technical_reason_counts_nonexclusive']}`。",
        "", "## 仓库层级", "",
        "| 仓库 | 主题数 | 成功 | 失败 | 未知 | 完成率 |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ])
    for row in report["repositories"]:
        value = row["main"]
        lines.append(f"| {row['repository']} | {value['denominator']} | {value['successes']} | "
                     f"{value['failures']} | {value['unknown']} | {rate(value['completion_rate'])} |")
    lines.extend(["", "完整机器报告保留 200 个任务及 280 个回合的状态、费用和所属仓库。"
                  "未知不补零，不只对已闭合子集计算主完成率。", ""])
    return "\n".join(lines)
