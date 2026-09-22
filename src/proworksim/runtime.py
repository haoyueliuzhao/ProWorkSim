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
        for attempt in range(3):
            http_request = urllib.request.Request(
                self.base_url + "/chat/completions",
                data=json_bytes(request),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(http_request, timeout=self.timeout) as response:
                    result = json.load(response)
                if not result.get("choices"):
                    raise ValueError("Provider returned no choices")
                return result
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(
                    f"DeepSeek HTTP {exc.code}; no credentials are recorded"
                ) from None
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(f"DeepSeek connection failed ({type(exc).__name__})") from None
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
    replied = {m.get("tool_call_id") for m in messages if m["role"] == "tool"}
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


def run_model(world: World, backend, max_turns=80, actor="analyst", progress=None):
    if max_turns < 1:
        raise ValueError("max_turns must be positive")
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
            if c["actor_id"] == actor and not c.get("tools_complete")
        ),
        None,
    )
    if pending:
        _finish_tools(world, actor, messages, pending)
    for turn in range(max_turns):
        observation = world.observe(actor)
        if observation["complete"]:
            return {
                "provider": backend.provider,
                "model": backend.model,
                "complete": True,
                "turns_this_run": turn,
            }
        messages.append({"role": "user", "content": json.dumps(observation, ensure_ascii=False)})
        request = backend.payload(copy.deepcopy(messages))
        start = time.monotonic()
        requested_at = datetime.now(timezone.utc).isoformat()
        try:
            response = backend.complete(request)
        except Exception:
            _save_runtime(world, actor, messages)
            raise
        assistant = response["choices"][0]["message"]
        if assistant.get("role") != "assistant":
            raise ValueError("Provider response must contain an assistant message")
        call = {
            "call_id": uuid.uuid4().hex,
            "actor_id": actor,
            "provider": backend.provider,
            "model_requested": backend.model,
            "model_returned": response.get("model"),
            "instance_id": state["instance_id"],
            "branch_id": world.store.load()["branch_id"],
            "request": request,
            "response": response,
            "requested_at": requested_at,
            "wall_seconds": time.monotonic() - start,
            "usage": response.get("usage"),
            "system_fingerprint": response.get("system_fingerprint"),
            "token_ids": None,
            "token_logprobs": response["choices"][0].get("logprobs"),
            "action_ids": [],
            "tool_results": [],
            "tools_complete": False,
        }
        # Preserve actual provider content, including reasoning_content if returned.
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
