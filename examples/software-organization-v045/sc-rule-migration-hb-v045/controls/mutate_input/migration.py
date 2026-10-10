"""Convert the bounded v1 rule grammar to canonical v2 without mutation."""
import copy
from rule_v1 import validate_rule

def migrate_v1_to_v2(rule):
    validate_rule(rule)
    def convert(node):
        op = node.pop("op")
        if op in ("all", "any"):
            return {"kind": op, "children": [convert(child) for child in node["rules"]]}
        if op == "not":
            return {"kind": "not", "child": convert(node["rule"])}
        result = {"kind": "predicate", "path": node["path"].split("."), "test": op}
        if op == "eq":
            result["value"] = copy.deepcopy(node["value"])
        elif op == "between":
            result["bounds"] = [node["low"], node["high"]]
        return result
    return convert(rule)
