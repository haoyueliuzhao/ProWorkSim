import pytest
from proworksim.software_context_fields_v231_1 import transform
from proworksim.software_context_builder_v230 import compact


def test_nested_roundtrip_privacy_keys_null_and_versions():
    a = {
        "actor_id": "member_001",
        "organization_protocol": {"stable": "long " * 100, "a/b": {"~n": True, "gone": 7}},
        "messages": ["observed"],
    }
    b = {"stable": "long " * 100, "a/b": {"~n": 1, "more": None}}
    msgs = [
        {"role": "user", "content": compact({"observation": a})},
        {
            "role": "user",
            "content": compact(
                {
                    "observation_delta": {
                        "inherits_observation_at_message": 0,
                        "changed": {"organization_protocol": b},
                        "removed": ["messages"],
                    }
                }
            ),
        },
    ]
    w = {"messages": msgs, "tools": []}
    t, items = transform(w, "member_001")
    assert items and t != w and transform(t, "member_001", restore=True)[0] == w
    assert w["messages"][0] == t["messages"][0]
    with pytest.raises(ValueError, match="Foreign snapshot"):
        transform(w, "member_002")
    with pytest.raises(ValueError, match="base"):
        transform({"messages": msgs[1:]}, "member_001")
