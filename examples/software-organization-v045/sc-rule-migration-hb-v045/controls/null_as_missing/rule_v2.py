"""Current v2 evaluator for the finite rule migration API."""
def evaluate_v2(rule, document):
    kind = rule["kind"]
    if kind == "all":
        return all(evaluate_v2(child, document) for child in rule["children"])
    if kind == "any":
        return any(evaluate_v2(child, document) for child in rule["children"])
    if kind == "not":
        return not evaluate_v2(rule["child"], document)
    value = document
    for key in rule["path"]:
        value = value.get(key) if isinstance(value, dict) else None
    if rule["test"] == "exists":
        return value is not None
    if rule["test"] == "eq":
        return value == rule.get("value")
    return isinstance(value, int) and rule["bounds"][0] <= value <= rule["bounds"][1]
