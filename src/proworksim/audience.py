"""Public, finite audience requirements shared by guides, staff and evaluators.

These contracts validate only explicit fields, types and nonempty content. They
do not judge writing quality, factual accuracy or fitness for a real client, and
must not prevent a worker from saving an incomplete or incorrect note.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AudienceRequirement:
    audience: str
    text_fields: tuple[str, ...]
    list_fields: tuple[str, ...]

    def public(self) -> dict:
        """Return a JSON-serializable declaration, with no reference answer."""
        return {
            "audience": self.audience,
            "content_field": "audience_content",
            "required_fields": {
                **{
                    name: {"type": "string", "min_non_whitespace_chars": 1}
                    for name in self.text_fields
                },
                **{
                    name: {
                        "type": "array",
                        "min_items": 1,
                        "items": {"type": "string", "min_non_whitespace_chars": 1},
                    }
                    for name in self.list_fields
                },
            },
            "additional_fields_allowed": True,
            "validation_scope": "required fields, types and nonempty content only",
        }

    def render_guidance(self) -> str:
        fields = [f"{name}: 非空字符串" for name in self.text_fields]
        fields.extend(f"{name}: 至少一项非空字符串的数组" for name in self.list_fields)
        return (
            f"受众 {self.audience}：在 note.audience_content 对象中提供 "
            + "；".join(fields)
            + "。保留 audience、share_price、sensitivity、source_versions 等基础字段。"
            "这些要求只核验字段、类型及非空内容，不代表主观写作质量或事实准确性评分。"
        )

    def defects(self, content) -> list[str]:
        """Describe missing or malformed content without mutating the artifact."""
        if not isinstance(content, dict):
            return ["note.audience_content 必须是对象。"]
        defects = []
        for name in self.text_fields:
            value = content.get(name)
            if not isinstance(value, str) or not value.strip():
                defects.append(f"note.audience_content.{name} 必须是非空字符串。")
        for name in self.list_fields:
            value = content.get(name)
            if (
                not isinstance(value, list)
                or not value
                or any(not isinstance(entry, str) or not entry.strip() for entry in value)
            ):
                defects.append(f"note.audience_content.{name} 必须是至少包含一项非空字符串的数组。")
        return defects


_REQUIREMENTS = {
    "internal_management": AudienceRequirement(
        "internal_management", ("executive_summary",), ("action_items",)
    ),
    "external_client": AudienceRequirement(
        "external_client",
        ("plain_language_summary",),
        ("assumption_disclosure", "limitations"),
    ),
    "investment_committee": AudienceRequirement(
        "investment_committee", ("decision_context",), ("scenario_risks",)
    ),
}


def audience_requirement(audience: str) -> AudienceRequirement:
    if not isinstance(audience, str) or audience not in _REQUIREMENTS:
        raise ValueError(f"Unsupported audience requirement: {audience!r}")
    return _REQUIREMENTS[audience]


def public_audience_requirements() -> dict:
    return {name: requirement.public() for name, requirement in _REQUIREMENTS.items()}


def audience_content_defects(content, audience: str) -> list[str]:
    """Report unknown audiences explicitly instead of silently accepting them."""
    try:
        requirement = audience_requirement(audience)
    except ValueError as exc:
        return [str(exc)]
    return requirement.defects(content)


def witness_audience_content(audience: str) -> dict:
    """Deterministic mechanism witness; never a grading reference or gold prose."""
    audience_requirement(audience)
    content = {
        "internal_management": {
            "executive_summary": "本说明汇总本次模型估值及敏感性结果，数值见股价和情景表。",
            "action_items": ["结合情景表检查增长及利润率变化对估值的影响，再决定后续行动。"],
        },
        "external_client": {
            "plain_language_summary": "股价估计表示在所列假设下模型得到的结果，情景表展示假设改变时的差异。",
            "assumption_disclosure": [
                "估值使用本次确认的增长率、利润率调整、税率及估值倍数；假设变化时需要重新计算。"
            ],
            "limitations": ["这是有限经营模型的情景结果，不能保证实际经营表现或未来交易价格。"],
        },
        "investment_committee": {
            "decision_context": "本次估值与情景表供委员会结合其他资料讨论，不构成独立投资决定。",
            "scenario_risks": [
                "增长及利润率假设变化会影响股价估计，模型未覆盖全部经营和市场风险。"
            ],
        },
    }
    return content[audience]
