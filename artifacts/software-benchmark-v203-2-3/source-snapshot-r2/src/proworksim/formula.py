"""Token-based restricted Excel AST. Percent is a postfix node, never text replacement."""

import math
import operator
from dataclasses import dataclass

from openpyxl.formula.tokenizer import Tokenizer, TokenizerError

ENGINE_VERSION = "restricted-excel-v0.1.2"


class FormulaError(ValueError):
    pass


@dataclass(frozen=True)
class Node:
    kind: str
    value: object = None
    children: tuple = ()


class FormulaParser:
    # Microsoft: negation, percent, exponent, multiply/divide, add/subtract.
    # Equal-precedence binary operators are evaluated from left to right.
    precedence = {"+": 10, "-": 10, "*": 20, "/": 20, "^": 30}

    def __init__(self, formula):
        if not isinstance(formula, str) or not formula.startswith("=") or len(formula) > 8000:
            raise FormulaError("Invalid formula or formula length")
        try:
            self.tokens = [t for t in Tokenizer(formula).items if t.type != "WHITE-SPACE"]
        except TokenizerError as exc:
            raise FormulaError(str(exc)) from exc
        if len(self.tokens) > 500:
            raise FormulaError("Formula exceeds 500 tokens")
        self.index = 0

    def peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def pop(self):
        token = self.peek()
        if token is None:
            raise FormulaError("Unexpected end of formula")
        self.index += 1
        return token

    def expression(self, minimum=0):
        token = self.pop()
        if token.type == "OPERATOR-PREFIX" and token.value in ("+", "-"):
            left = Node("unary", token.value, (self.expression(50),))
        elif token.type == "OPERAND" and token.subtype == "NUMBER":
            left = Node("number", float(token.value))
        elif token.type == "OPERAND" and token.subtype == "RANGE":
            left = Node("reference", token.value)
        elif token.type == "PAREN" and token.subtype == "OPEN":
            left = self.expression()
            close = self.pop()
            if close.type != "PAREN" or close.subtype != "CLOSE":
                raise FormulaError("Expected closing parenthesis")
        elif token.type == "FUNC" and token.subtype == "OPEN":
            name = token.value[:-1].upper()
            args = []
            if self.peek() and self.peek().type == "FUNC" and self.peek().subtype == "CLOSE":
                self.pop()
            else:
                while True:
                    args.append(self.expression())
                    sep = self.pop()
                    if sep.type == "FUNC" and sep.subtype == "CLOSE":
                        break
                    if sep.type != "SEP" or sep.subtype != "ARG":
                        raise FormulaError("Invalid function argument separator")
            left = Node("function", name, tuple(args))
        else:
            raise FormulaError(f"Unsupported operand: {token.value}")
        while self.peek():
            token = self.peek()
            if token.type == "OPERATOR-POSTFIX" and token.value == "%" and minimum <= 40:
                self.pop()
                left = Node("percent", None, (left,))
                continue
            precedence = (
                self.precedence.get(token.value) if token.type == "OPERATOR-INFIX" else None
            )
            if precedence is None or precedence < minimum:
                break
            self.pop()
            left = Node("binary", token.value, (left, self.expression(precedence + 1)))
        return left

    def parse(self):
        try:
            node = self.expression()
        except (RecursionError, ValueError) as exc:
            raise FormulaError(str(exc)) from exc
        if self.peek() is not None:
            raise FormulaError(f"Unsupported or trailing token: {self.peek().value}")
        return node


def evaluate_formula(formula, resolver, functions):
    tree = FormulaParser(formula).parse()

    def finite(value):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise FormulaError("Formula result must be a finite number")
        return value

    def visit(node):
        if node.kind == "number":
            return finite(node.value)
        if node.kind == "reference":
            return resolver(node.value)
        if node.kind == "unary":
            value = finite(visit(node.children[0]))
            return -value if node.value == "-" else value
        if node.kind == "percent":
            return finite(visit(node.children[0])) / 100
        if node.kind == "binary":
            a, b = [finite(visit(child)) for child in node.children]
            if node.value == "^" and abs(b) > 32:
                raise FormulaError("Exponent exceeds limit")
            operation = {
                "+": operator.add,
                "-": operator.sub,
                "*": operator.mul,
                "/": operator.truediv,
                "^": operator.pow,
            }[node.value]
            return finite(operation(a, b))
        if node.kind == "function":
            if node.value not in functions:
                raise FormulaError(f"Unsupported function: {node.value}")
            args = []
            for child in node.children:
                value = visit(child)
                args.extend(value if isinstance(value, list) else [value])
            if node.value == "ABS" and len(args) != 1:
                raise FormulaError("ABS expects one argument")
            for value in args:
                finite(value)
            return finite(functions[node.value](args))
        raise FormulaError("Unsupported AST node")

    try:
        return finite(visit(tree))
    except (ArithmeticError, TypeError, IndexError, RecursionError) as exc:
        raise FormulaError(str(exc)) from exc
