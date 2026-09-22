import json

import pytest

from proworksim.audience import (
    audience_content_defects,
    audience_requirement,
    public_audience_requirements,
    witness_audience_content,
)


@pytest.mark.parametrize(
    "audience,text_fields,list_fields",
    [
        ("internal_management", ["executive_summary"], ["action_items"]),
        (
            "external_client",
            ["plain_language_summary"],
            ["assumption_disclosure", "limitations"],
        ),
        ("investment_committee", ["decision_context"], ["scenario_risks"]),
    ],
)
def test_public_requirements_and_validation_use_the_same_finite_fields(
    audience, text_fields, list_fields
):
    requirement = audience_requirement(audience)
    public = json.loads(json.dumps(public_audience_requirements()))[audience]
    assert public == requirement.public()
    assert public["content_field"] == "audience_content"
    assert set(public["required_fields"]) == set(text_fields + list_fields)
    content = {name: "独立撰写的简短说明" for name in text_fields}
    content.update({name: ["一项已说明的内容"] for name in list_fields})
    content["optional_extra"] = {"ignored": True}
    before = json.dumps(content)
    assert audience_content_defects(content, audience) == []
    assert json.dumps(content) == before
    for name in text_fields + list_fields:
        assert name in requirement.render_guidance()
        incomplete = {key: value for key, value in content.items() if key != name}
        defects = audience_content_defects(incomplete, audience)
        assert len(defects) == 1
        assert f"audience_content.{name}" in defects[0]
    assert requirement.defects(witness_audience_content(audience)) == []


@pytest.mark.parametrize("content", [None, "summary", [], 42])
def test_content_requires_an_object(content):
    assert audience_content_defects(content, "internal_management")


@pytest.mark.parametrize(
    "field,value",
    [
        ("executive_summary", " \n\t"),
        ("executive_summary", ["summary"]),
        ("action_items", "an action"),
        ("action_items", []),
        ("action_items", ["valid", " \t"]),
        ("action_items", ["valid", 1]),
        ("action_items", {"action": "valid"}),
    ],
)
def test_blank_and_wrong_type_content_is_rejected(field, value):
    content = {"executive_summary": "A summary", "action_items": ["An action"]}
    content[field] = value
    defects = audience_content_defects(content, "internal_management")
    assert len(defects) == 1
    assert f"audience_content.{field}" in defects[0]


@pytest.mark.parametrize("audience", ["unknown_customer", None, ["internal_management"]])
def test_unknown_audience_is_explicitly_unsupported(audience):
    with pytest.raises(ValueError, match="Unsupported audience"):
        audience_requirement(audience)
    assert "Unsupported audience" in audience_content_defects({}, audience)[0]


def test_changing_only_the_audience_label_does_not_satisfy_new_content():
    old_content = {
        "executive_summary": "已有内部汇报。",
        "action_items": ["内部核查。"],
    }
    assert audience_content_defects(old_content, "internal_management") == []
    defects = audience_content_defects(old_content, "external_client")
    assert len(defects) == 3
