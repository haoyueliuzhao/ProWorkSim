"""Canonical v2 evaluator backed by the public preserved v1 semantics."""
import copy
import rule_v1

def _legacy(node, path="$", depth=1, count=None):
    count = [0] if count is None else count
    count[0] += 1
    if count[0] > 16:
        raise ValueError(path + ":node_limit")
    if depth > 4:
        raise ValueError(path + ":depth_limit")
    if type(node) is not dict:
        raise ValueError(path + ":object_required")
    kind = node.get("kind")
    if kind in ("all", "any"):
        if set(node) != {"kind", "children"} or type(node["children"]) is not list or not 1 <= len(node["children"]) <= 4:
            raise ValueError(path + ":invalid_v2")
        return {"op": kind, "rules": [_legacy(child, path + ".children[" + str(i) + "]", depth + 1, count)
            for i, child in enumerate(node["children"])]}
    if kind == "not":
        if set(node) != {"kind", "child"}:
            raise ValueError(path + ":invalid_v2")
        return {"op": "not", "rule": _legacy(node["child"], path + ".child", depth + 1, count)}
    if kind != "predicate" or node.get("test") not in ("eq", "exists", "between"):
        raise ValueError(path + ":invalid_v2")
    fields = {"kind", "path", "test"} | ({"value"} if node["test"] == "eq" else {"bounds"} if node["test"] == "between" else set())
    if set(node) != fields or type(node["path"]) is not list or not node["path"] or any(type(p) is not str or "." in p for p in node["path"]):
        raise ValueError(path + ":invalid_v2")
    result = {"op": node["test"], "path": ".".join(node["path"])}
    if node["test"] == "eq":
        result["value"] = copy.deepcopy(node["value"])
    elif node["test"] == "between":
        if type(node["bounds"]) is not list or len(node["bounds"]) != 2:
            raise ValueError(path + ":invalid_v2")
        result.update(low=node["bounds"][0], high=node["bounds"][1])
    return result

def evaluate_v2(rule, document):
    return rule_v1.evaluate(_legacy(rule), document)
