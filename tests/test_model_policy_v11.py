"""A0 interface checks use declared simulated HTTP responses, never a model run."""

import copy
import json

import pytest

from proworksim.core.world import WorldSpec
from proworksim.model_policy import ModelPolicy
from proworksim.model_transport import HTTPModelTransport, TransportFailure
from proworksim.staff_runtime import StaffRuntime
from proworksim.world_core import WorldCore


def response(
    *calls, content=None, reasoning="real returned reasoning", usage=True, status=200, error=None
):
    body = {
        "id": "simulated-completion",
        "model": "simulated-model-revision",
        "choices": [
            {
                "finish_reason": "tool_calls" if calls else "stop",
                "message": {
                    "role": "assistant",
                    "content": content,
                    "reasoning_content": reasoning,
                    "tool_calls": list(calls),
                },
            }
        ],
    }
    if usage:
        body["usage"] = {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "prompt_cache_hit_tokens": 25,
        }
    if error:
        body = {"error": error}
    return {
        "http_status": status,
        "raw_body": json.dumps(body),
        "body": body,
        "response_headers": {"x-request-id": "simulated-request"},
    }


def call(name="read_object", arguments=None, identity="tool-1"):
    return {
        "id": identity,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments if arguments is not None else {"alias": "input"}),
        },
    }


class SimulatedTransport:
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []

    def complete(self, request, *, timeout_seconds):
        self.requests.append(copy.deepcopy(request))
        assert self.responses, "Unexpected resampling exceeded the declared simulated sequence"
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)


def fixture(tmp_path, responses, config=None, audit_dir=None):
    world = WorldCore.create(
        tmp_path / "world",
        WorldSpec(
            "model-interface-A0",
            {"setup": {}, "worker": {}, "other": {}},
            bootstrap_grants=[{"actor_id": "setup", "scope": "world", "power": "install_project"}],
        ),
    )
    for project, actor, value in (("A", "worker", "private-A"), ("B", "other", "private-B")):
        package = {
            "project_id": project,
            "goal": "Read own material",
            "participants": [actor],
            "objects": [
                {
                    "alias": "input",
                    "kind": "json",
                    "filename": "input.json",
                    "owner": actor,
                    "readers": [actor],
                    "data": {"value": value},
                }
            ],
            "works": [],
        }
        assert world.session("setup").call("install_project", package=package)["ok"]
    transport = SimulatedTransport(responses)
    config = {
        "task": "Use only your own public input.",
        "retry": {"max_attempts": 2, "backoff_seconds": [0]},
        **(config or {}),
    }
    policy = ModelPolicy(
        config, transport=transport, audit_dir=audit_dir, sleep=lambda seconds: None
    )
    runtime = StaffRuntime(
        {"target": world.session("worker", "A")}, {"target": policy}, run_id="A0-run"
    )
    return world, transport, policy, runtime


def events(runtime, kind):
    return [e["payload"] for e in runtime.recorder.events if e["kind"] == kind]


def test_actual_action_history_checkpoint_and_role_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "A0-CREDENTIAL-MUST-NOT-ENTER-CHECKPOINT")
    world, transport, policy, runtime = fixture(
        tmp_path,
        [
            response(call()),
            response(call("staff_done", {"reason": "Read the actual value"}, "finish")),
        ],
        audit_dir=tmp_path / "model-calls",
    )
    first = runtime.step()
    assert first["action_performed"] and first["response"]["result"]["data"] == {
        "value": "private-A"
    }
    assert len(transport.requests) == 1
    assert "private-B" not in json.dumps(transport.requests)
    assert "A0-CREDENTIAL" not in json.dumps(runtime.snapshot())
    checkpoint = json.loads(json.dumps(runtime.snapshot()))
    resumed_policy = ModelPolicy(policy.config, transport=transport)
    resumed = StaffRuntime(
        {"target": world.session("worker", "A")}, {"target": resumed_policy}, checkpoint=checkpoint
    )
    outcome = resumed.step()
    assert outcome["status"] == "completed" and not outcome["action_performed"]
    history = transport.requests[1]["messages"]
    assert history[2]["reasoning_content"] == "real returned reasoning"
    assert history[2]["tool_calls"] == [call()]
    assert json.loads(history[3]["content"]) == first["response"]
    assert history[3]["tool_call_id"] == "tool-1"
    assert resumed.step()["status"] == "completed"
    assert len(transport.requests) == 2
    links = events(resumed, "model_action_link")
    assert len(links) == 1 and links[0]["world_response"] == first["response"]
    assert links[0]["model_call_id"] == events(resumed, "model_attempt")[0]["call_id"]
    assert links[0]["opportunity_id"].endswith("-1")
    assert len(list((tmp_path / "model-calls").glob("*.json"))) >= 4


def test_valid_wrong_action_is_executed_once_and_real_refusal_enters_next_request(tmp_path):
    _, transport, _, runtime = fixture(
        tmp_path,
        [
            response(call("not_a_registered_world_tool")),
            response(call("staff_done", {"reason": "Stop after the observed rejection"}, "finish")),
        ],
    )
    failed = runtime.step()
    assert failed["action_performed"] and failed["response"]["ok"] is False
    assert failed["status"] == "capability_gap" and len(transport.requests) == 1
    runtime.step()
    tool = next(
        message for message in transport.requests[1]["messages"] if message["role"] == "tool"
    )
    assert json.loads(tool["content"]) == failed["response"]
    assert runtime.actions == 1


@pytest.mark.parametrize(
    "bad",
    [
        response(call(identity="first"), call(identity="second")),
        response(
            {
                "id": "broken",
                "type": "function",
                "function": {"name": "read_object", "arguments": "{"},
            }
        ),
        response(content="I am finished; trust me."),
        response(call(arguments={"request_key": "override"})),
    ],
)
def test_format_failure_retains_whole_response_and_executes_nothing(tmp_path, bad):
    world, transport, _, runtime = fixture(tmp_path, [bad])
    before = copy.deepcopy(world.store.load()["artifacts"])
    outcome = runtime.step()
    assert outcome["status"] == "model_format_error" and not outcome["action_performed"]
    assert events(runtime, "model_response")[0]["response"] == bad["body"]
    assert runtime.actions == 0 and len(transport.requests) == 1
    assert runtime.step()["status"] == "model_format_error" and len(transport.requests) == 1
    assert world.store.load()["artifacts"] == before


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError("actual timeout fact"),
        TransportFailure("timeout", "offline declared timeout", retryable=True),
        response(status=429, error={"code": "rate_limit", "message": "Simulated throttle"}),
    ],
)
def test_fixed_service_retry_preserves_every_attempt_and_identical_request(tmp_path, failure):
    _, transport, _, runtime = fixture(tmp_path, [failure, response(call())])
    assert runtime.step()["action_performed"]
    assert len(transport.requests) == 2 and transport.requests[0] == transport.requests[1]
    attempts = events(runtime, "model_attempt")
    assert [a["stage"] for a in attempts] == ["started", "finished", "started", "finished"]
    assert attempts[1]["will_retry"] and not attempts[-1]["will_retry"]
    assert attempts[1]["accounting"]["usage_status"] == "missing_or_invalid"
    assert attempts[-1]["accounting"]["reported_usage"]["total_tokens"] == 120
    assert events(runtime, "model_retry")[0]["backoff_seconds"] == 0
    assert runtime.roles["target"]["memory"]["meter"]["decisions"] == 1


@pytest.mark.parametrize(
    "responses,status",
    [
        ([TimeoutError("t1"), TimeoutError("t2")], "model_service_error"),
        ([response(status=401, error={"code": "invalid_api_key"})], "model_service_error"),
        ([response(call(), usage=False)], "model_service_error"),
        (
            [response(status=400, error={"code": "context_length_exceeded"})],
            "model_budget_exhausted",
        ),
    ],
)
def test_service_context_or_missing_usage_is_not_policy_capability_error(
    tmp_path, responses, status
):
    _, transport, _, runtime = fixture(tmp_path, responses)
    outcome = runtime.step()
    assert outcome["status"] == status and not outcome["action_performed"]
    assert not events(runtime, "policy_error") and not events(runtime, "tool_call")
    attempts = len(transport.requests)
    assert runtime.step()["status"] == status and len(transport.requests) == attempts


@pytest.mark.parametrize(
    "budget",
    [
        {"max_decisions": 0},
        {"max_http_attempts": 0},
        {"max_total_tokens": 1},
        {"max_cost_usd": 0},
        {"max_context_bytes": 1},
    ],
)
def test_frozen_budget_prevents_http_without_trimming_or_fake_usage(tmp_path, budget):
    _, transport, _, runtime = fixture(tmp_path, [], {"budget": budget})
    assert runtime.step()["status"] == "model_budget_exhausted"
    assert transport.requests == [] and runtime.actions == 0
    meter = runtime.roles["target"]["memory"]["meter"]
    assert meter["reported_total_tokens"] == 0


def test_decision_budget_survives_checkpoint_and_consumes_pending_actual_result(tmp_path):
    world, transport, policy, runtime = fixture(
        tmp_path, [response(call())], {"budget": {"max_decisions": 1}}
    )
    first = runtime.step()
    resumed = StaffRuntime(
        {"target": world.session("worker", "A")},
        {"target": ModelPolicy(policy.config, transport=transport)},
        checkpoint=runtime.snapshot(),
    )
    assert resumed.step()["status"] == "model_budget_exhausted"
    assert len(transport.requests) == 1
    assert (
        json.loads(resumed.roles["target"]["memory"]["messages"][-1]["content"])
        == first["response"]
    )


def test_loopback_without_key_omits_thinking_and_retains_declared_weight_identity(tmp_path):
    _, transport, policy, runtime = fixture(
        tmp_path,
        [response(call("staff_wait", {"reason": "Wait for public information"}))],
        {
            "backend_id": "local-qwen",
            "model": "Qwen2.5-7B-Instruct",
            "model_revision": "a09a35458c702b33eeacc393d103063234e8bc28",
            "base_url": "http://127.0.0.1:9999/v1",
            "api_key_env": None,
            "thinking": None,
            "max_context_tokens": 32768,
            "pricing": {
                "input_miss_per_million": 0,
                "input_hit_per_million": 0,
                "output_per_million": 0,
            },
        },
    )
    assert runtime.step()["status"] == "worker_waiting"
    assert "thinking" not in transport.requests[0]
    assert policy.config["model_revision"].startswith("a09a")
    assert runtime.actions == 0
    with pytest.raises(ValueError, match="loopback"):
        HTTPModelTransport("https://example.org", api_key_env=None)


def test_http_attempt_preserves_body_and_never_records_authorization(tmp_path, monkeypatch):
    import urllib.request

    secret = "A0-HTTP-SECRET-CREDENTIAL"
    monkeypatch.setenv("A0_HTTP_KEY", secret)
    actual_request = []
    body = response(call())["body"]
    body["echoed_error_detail"] = secret

    class HTTPResponse:
        status = 200
        headers = {"x-request-id": "actual-A0-header"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps(body).encode()

    def fake_urlopen(request, timeout):
        actual_request.append(request)
        assert timeout == 2
        return HTTPResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    transport = HTTPModelTransport("https://api.deepseek.com", api_key_env="A0_HTTP_KEY")
    request = {
        "model": "declared-A0-model",
        "messages": [{"role": "user", "content": "public-only"}],
    }
    result = transport.complete(request, timeout_seconds=2)
    assert actual_request[0].headers["Authorization"] == "Bearer " + secret
    assert json.loads(actual_request[0].data) == request
    assert (
        result["http_status"] == 200
        and result["response_headers"]["x-request-id"] == "actual-A0-header"
    )
    assert result["body"]["choices"] == body["choices"]
    assert secret not in json.dumps(result) and result["response_redactions"]


@pytest.mark.parametrize(
    "config",
    [
        {"api_key_env": "sk-do-not-store-a-literal-key"},
        {"base_url": "https://credential@example.org"},
    ],
)
def test_even_offline_transports_do_not_accept_embedded_credential_config(config):
    with pytest.raises(ValueError):
        ModelPolicy(config, transport=SimulatedTransport([]))


def test_single_json_protocol_supplies_actual_tools_and_real_user_result_history(tmp_path):
    world, transport, policy, runtime = fixture(
        tmp_path,
        [
            response(
                content=json.dumps(
                    {"kind": "act", "action": "read_object", "arguments": {"alias": "input"}}
                )
            ),
            response(
                content=json.dumps({"kind": "done", "reason": "Read the actual returned source"})
            ),
        ],
        {"action_protocol": "single_decision_json"},
    )
    first = runtime.step()
    assert first["action_performed"] and first["response"]["ok"]
    request = transport.requests[0]
    assert "tools" not in request and "tool_choice" not in request
    assert request["response_format"] == {"type": "json_object"}
    public = json.loads(request["messages"][-1]["content"])
    assert public["public_tools"] == world.session("worker", "A").tools()
    assert public["observation"]["actor_id"] == "worker"
    original_message = copy.deepcopy(runtime.roles["target"]["memory"]["messages"][-1])
    resumed = StaffRuntime(
        {"target": world.session("worker", "A")},
        {"target": ModelPolicy(policy.config, transport=transport)},
        checkpoint=runtime.snapshot(),
    )
    assert resumed.step()["status"] == "completed"
    request = transport.requests[1]
    assert all(message["role"] != "tool" for message in request["messages"])
    assert request["messages"][2] == original_message
    actual = json.loads(request["messages"][3]["content"])
    assert actual["public_tool_result"] == first["response"]
    assert actual["executed_action"] == {"action": "read_object", "arguments": {"alias": "input"}}
    assert actual["model_call_id"] == events(resumed, "model_action_link")[0]["model_call_id"]
    assert resumed.step()["status"] == "completed" and len(transport.requests) == 2


@pytest.mark.parametrize(
    "bad",
    [
        response(content='[{"kind":"act","action":"read_object","arguments":{"alias":"input"}}]'),
        response(content='{"kind":"act","action":"read_object","arguments":{},"actions":[{}]}'),
        response(
            content='{"kind":"act","action":"read_object","arguments":{},"memory":{"fake":true}}'
        ),
        response(content='{"kind":"done","kind":"wait","reason":"ambiguous"}'),
        response(content='{"kind":"act","action":"read_object","arguments":{"x":1,"x":2}}'),
        response(call(), content='{"kind":"done","reason":"also try a native action"}'),
        response(call(identity="first"), call(identity="second")),
    ],
)
def test_json_protocol_never_selects_one_from_multiple_or_extra_decisions(tmp_path, bad):
    world, transport, _, runtime = fixture(
        tmp_path, [bad], {"action_protocol": "single_decision_json"}
    )
    before = copy.deepcopy(world.store.load()["artifacts"])
    result = runtime.step()
    assert result["status"] == "model_format_error" and not result["action_performed"]
    assert (
        len(transport.requests) == 1
        and events(runtime, "model_response")[0]["response"] == bad["body"]
    )
    assert world.store.load()["artifacts"] == before


def test_json_valid_wrong_action_is_not_resampled(tmp_path):
    _, transport, _, runtime = fixture(
        tmp_path,
        [response(content='{"kind":"act","action":"unregistered","arguments":{}}')],
        {"action_protocol": "single_decision_json"},
    )
    result = runtime.step()
    assert result["action_performed"] and result["status"] == "capability_gap"
    assert len(transport.requests) == 1 and runtime.actions == 1


def test_loopback_http_attempt_explicitly_bypasses_proxy(monkeypatch):
    import urllib.request

    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:9999")
    seen = []

    class Reply:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b'{"ok":"loopback"}'

    class Direct:
        def open(self, request, timeout):
            seen.append(request.full_url)
            assert "Authorization" not in request.headers
            return Reply()

    def no_proxy(*handlers):
        assert len(handlers) == 1 and isinstance(handlers[0], urllib.request.ProxyHandler)
        assert handlers[0].proxies == {}
        return Direct()

    monkeypatch.setattr(urllib.request, "build_opener", no_proxy)
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("loopback attempted the environment proxy path"),
    )
    result = HTTPModelTransport("http://127.0.0.1:18761/v1", api_key_env=None).complete(
        {"model": "offline"}, timeout_seconds=1
    )
    assert result["body"] == {"ok": "loopback"}
    assert seen == ["http://127.0.0.1:18761/v1/chat/completions"]
