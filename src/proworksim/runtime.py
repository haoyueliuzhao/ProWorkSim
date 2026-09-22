"""Resumable target-worker loop and direct DeepSeek HTTP provider."""

import copy
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .audit import begin_run, finish_run
from .kernel import World
from .storage import json_bytes
from .tools import TOOLS

SYSTEM_PROMPT = """你是 ProWorkSim 中的执行分析师，承担当前可见工作义务。
通过工具发现材料、读取邮件、计算、修改实际文件并提交。只有工具成功执行才改变世界。
先阅读工作要求与 guide；使用 artifact_id。版本依赖必须反映实际使用的输入。
输入口径未确认时可询问负责人；提交后等待实际审阅。处理新产生的义务直到项目完成。
遵守当前任务交付范围：短回复不必写文件；文件任务不必写报告；连续项目需同步依赖成果。
你没有隐藏评分器或未来材料的访问权。工具错误是可恢复的观察。遇到不可解决的缺口可 block_work。
不要把专业假设写成已发生事实。解释应说明来源、期间、单位与不确定性。
"""


def load_env(path=".env"):
    """Read simple KEY=value dotenv assignments without executing shell code."""
    file = Path(path)
    if not file.is_file():
        return
    for line in file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key.startswith("DEEPSEEK_"):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


class DeepSeekBackend:
    provider = "deepseek"

    def __init__(
        self, model=None, base_url=None, api_key=None, thinking=False, timeout=120, max_tokens=4096
    ):
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
        self.base_url = (
            base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        ).rstrip("/")
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY is missing; configure .env or use --provider baseline"
            )
        self.thinking, self.timeout, self.max_tokens = thinking, timeout, max_tokens

    def payload(self, messages):
        return {
            "model": self.model,
            "messages": messages,
            "tools": TOOLS,
            "thinking": {"type": "enabled" if self.thinking else "disabled"},
            "max_tokens": self.max_tokens,
            "stream": False,
        }

    def complete(self, request):
        for index in range(3):
            attempt = {
                "attempt_id": uuid.uuid4().hex,
                "attempt_index": index,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "status": "started",
                "usage": None,
                "http_status": None,
            }
            start = time.monotonic()
            sink = getattr(self, "attempt_sink", lambda record: None)
            sink(copy.deepcopy(attempt))
            http_request = urllib.request.Request(
                self.base_url + "/chat/completions",
                data=json_bytes(request),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            retry = False
            try:
                with urllib.request.urlopen(http_request, timeout=self.timeout) as response:
                    attempt["http_status"] = response.status
                    result = json.load(response)
                if not result.get("choices"):
                    raise ValueError("Provider returned no choices")
                attempt.update(status="success", usage=result.get("usage"))
                return result
            except urllib.error.HTTPError as exc:
                attempt.update(status="http_error", http_status=exc.code)
                retry = exc.code in (429, 500, 502, 503, 504) and index < 2
                if not retry:
                    raise RuntimeError(
                        f"DeepSeek HTTP {exc.code}; no credentials are recorded"
                    ) from None
            except (urllib.error.URLError, TimeoutError) as exc:
                attempt.update(
                    status="timeout" if isinstance(exc, TimeoutError) else "connection_error"
                )
                retry = index < 2
                if not retry:
                    raise RuntimeError(
                        f"DeepSeek connection failed ({type(exc).__name__})"
                    ) from None
            except Exception:
                attempt["status"] = "invalid_response"
                raise
            finally:
                attempt["wall_seconds"] = time.monotonic() - start
                sink(copy.deepcopy(attempt))
            if retry:
                time.sleep(2**index)
        raise RuntimeError("Provider retry budget exhausted")


def _save_runtime(world, actor, messages, call=None):
    with world.store.lock():
        state = world.store.load()
        state.setdefault("runtime", {})[actor] = {"messages": messages}
        if call is not None:
            index = next(
                (i for i, old in enumerate(state["calls"]) if old["call_id"] == call["call_id"]),
                None,
            )
            if index is None:
                state["calls"].append(call)
            else:
                state["calls"][index] = call
        world.store.save(state)


def _finish_tools(world, actor, messages, call):
    assistant = call["response"]["choices"][0]["message"]
    replied = set(call.get("completed_tool_call_ids", []))
    for candidate in assistant.get("tool_calls", []):
        candidate_id = candidate["id"]
        if candidate_id in replied:
            continue
        try:
            arguments = json.loads(candidate["function"]["arguments"])
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be an object")
        except (ValueError, KeyError, TypeError) as exc:
            result = {"ok": False, "error": {"type": "MalformedToolCall", "message": str(exc)}}
        else:
            result = world.act(
                actor,
                candidate["function"]["name"],
                arguments,
                request_key=f"{call['call_id']}:{candidate_id}",
            )
        if "action_id" in result:
            call["action_ids"].append(result["action_id"])
        call["tool_results"].append(result)
        call.setdefault("completed_tool_call_ids", []).append(candidate_id)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": candidate_id,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )
        _save_runtime(world, actor, messages, call)
    call["tools_complete"] = True
    _save_runtime(world, actor, messages, call)


def run_model(world: World, backend, max_turns=80, actor="analyst", progress=None, stop_when=None):
    if max_turns < 1:
        raise ValueError("max_turns must be positive")
    manifest = begin_run(world, backend, {"max_turns": max_turns})
    try:
        result = _run_loop(
            world, backend, max_turns, actor, progress, stop_when, manifest["run_id"]
        )
    except BaseException:
        finish_run(world, manifest, "exception")
        raise
    finish_run(world, manifest, result.get("reason", "complete"))
    return {**result, "run_id": manifest["run_id"]}


def _run_loop(world, backend, max_turns, actor, progress, stop_when, run_id):
    state = world.store.load()
    saved = state.get("runtime", {}).get(actor)
    messages = (
        copy.deepcopy(saved["messages"])
        if saved
        else [{"role": "system", "content": SYSTEM_PROMPT}]
    )
    pending = next(
        (
            c
            for c in reversed(state["calls"])
            if c["actor_id"] == actor and c.get("response") and not c.get("tools_complete")
        ),
        None,
    )
    if pending:
        _finish_tools(world, actor, messages, pending)
    for turn in range(max_turns):
        observation = world.observe(actor)
        if observation["complete"] or (stop_when and stop_when(observation)):
            return {
                "provider": backend.provider,
                "model": backend.model,
                "complete": observation["complete"],
                "turns_this_run": turn,
                "reason": "complete" if observation["complete"] else "experiment_boundary",
            }
        messages.append({"role": "user", "content": json.dumps(observation, ensure_ascii=False)})
        request = backend.payload(copy.deepcopy(messages))
        call = {
            "call_id": uuid.uuid4().hex,
            "run_id": run_id,
            "actor_id": actor,
            "provider": backend.provider,
            "model_requested": backend.model,
            "model_returned": None,
            "policy_version": getattr(backend, "policy_version", backend.model),
            "instance_id": state["instance_id"],
            "branch_id": world.store.load()["branch_id"],
            "request": request,
            "response": None,
            "status": "requested",
            "attempts": [],
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "usage": None,
            "system_fingerprint": None,
            "token_ids": None,
            "token_logprobs": None,
            "action_ids": [],
            "tool_results": [],
            "completed_tool_call_ids": [],
            "tools_complete": False,
        }
        _save_runtime(world, actor, messages, call)

        def persist_attempt(attempt):
            old = next(
                (a for a in call["attempts"] if a["attempt_id"] == attempt["attempt_id"]), None
            )
            if old is None:
                call["attempts"].append(attempt)
            else:
                old.update(attempt)
            _save_runtime(world, actor, messages, call)

        backend.attempt_sink = persist_attempt
        started = time.monotonic()
        try:
            response = backend.complete(request)
            assistant = response["choices"][0]["message"]
            if assistant.get("role") != "assistant":
                raise ValueError("Provider response must contain an assistant message")
        except Exception as exc:
            call.update(
                status="failed",
                tools_complete=True,
                error_type=type(exc).__name__,
                wall_seconds=time.monotonic() - started,
            )
            _save_runtime(world, actor, messages, call)
            raise
        call.update(
            response=response,
            status="completed",
            model_returned=response.get("model"),
            wall_seconds=time.monotonic() - started,
            usage=response.get("usage"),
            system_fingerprint=response.get("system_fingerprint"),
            token_ids=response.get("output_token_ids"),
            token_logprobs=response["choices"][0].get("logprobs"),
        )
        messages.append(copy.deepcopy(assistant))
        _save_runtime(world, actor, messages, call)
        _finish_tools(world, actor, messages, call)
        if progress:
            progress(
                {
                    "turn": turn + 1,
                    "usage": call["usage"],
                    "actions": len(call["action_ids"]),
                    "logical_time": world.store.load()["clock"],
                }
            )
        if not assistant.get("tool_calls"):
            messages.append(
                {
                    "role": "user",
                    "content": "请通过 submit 提交实际成果；若已提交，请 wait 等待反馈。",
                }
            )
            _save_runtime(world, actor, messages)
    return {
        "provider": backend.provider,
        "model": backend.model,
        "complete": world.observe(actor)["complete"],
        "turns_this_run": max_turns,
        "reason": "turn_budget",
    }
