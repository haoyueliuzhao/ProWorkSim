"""Bounded v1 rule evaluator; missing fields differ from explicit null."""
import re

_MISSING = object()

def _error(path, code):
    raise ValueError(path + ":" + code)

def _path(value, path):
    if type(value) is not str or not 1 <= len(value.split(".")) <= 4 or any(
            not re.fullmatch(r"[a-z][a-z0-9_]{0,15}", part) for part in value.split(".")):
        _error(path, "invalid_path")

def validate_rule(rule):
    count = [0]
    def visit(node, path, depth):
        count[0] += 1
        if count[0] > 16:
            _error(path, "node_limit")
        if depth > 4:
            _error(path, "depth_limit")
        if type(node) is not dict:
            _error(path, "object_required")
        if "op" not in node:
            _error(path + ".op", "missing")
        op = node["op"]
        if type(op) is not str or op not in ("eq", "exists", "between", "all", "any", "not"):
            _error(path + ".op", "unknown")
        fields = {"eq": ("path", "value"), "exists": ("path",), "between": ("path", "low", "high"),
                  "all": ("rules",), "any": ("rules",), "not": ("rule",)}[op]
        for field in fields:
            if field not in node:
                _error(path + "." + field, "missing")
        extra = sorted(set(node) - {"op", *fields})
        if extra:
            _error(path + "." + str(extra[0]), "unknown_field")
        if op in ("eq", "exists", "between"):
            _path(node["path"], path + ".path")
        if op == "eq":
            value = node["value"]
            if value is not None and not (type(value) is bool or type(value) is int and -1000 <= value <= 1000
                    or type(value) is str and len(value) <= 32):
                _error(path + ".value", "scalar_required")
        elif op == "between":
            for field in ("low", "high"):
                if type(node[field]) is not int or not -1000 <= node[field] <= 1000:
                    _error(path + "." + field, "integer_required")
            if node["low"] > node["high"]:
                _error(path + ".high", "invalid_range")
        elif op in ("all", "any"):
            if type(node["rules"]) is not list or not 1 <= len(node["rules"]) <= 4:
                _error(path + ".rules", "rule_list_required")
            for index, child in enumerate(node["rules"]):
                visit(child, path + ".rules[" + str(index) + "]", depth + 1)
        elif op == "not":
            visit(node["rule"], path + ".rule", depth + 1)
    visit(rule, "$", 1)

def _value(document, path):
    value = document
    for part in path.split("."):
        if type(value) is not dict or part not in value:
            return _MISSING
        value = value[part]
    return value

def _evaluate(rule, document):
    op = rule["op"]
    if op == "all":
        return all(_evaluate(child, document) for child in rule["rules"])
    if op == "any":
        return any(_evaluate(child, document) for child in rule["rules"])
    if op == "not":
        return not _evaluate(rule["rule"], document)
    value = _value(document, rule["path"])
    if op == "exists":
        return value is not _MISSING
    if op == "eq":
        return type(value) is type(rule["value"]) and value == rule["value"]
    return type(value) is int and rule["low"] <= value <= rule["high"]

def evaluate(rule, document):
    validate_rule(rule)
    if type(document) is not dict:
        raise ValueError("document:object_required")
    return _evaluate(rule, document)
