"""Pure local function binding; no host runtime, resources or dispatch imports."""
from types import FunctionType


def clone_function(function, namespace):
    value = FunctionType(function.__code__, namespace, function.__name__,
                         function.__defaults__, function.__closure__)
    value.__kwdefaults__ = function.__kwdefaults__
    value.__annotations__ = dict(function.__annotations__)
    return value


def clone_namespace(module, **overrides):
    namespace = {**vars(module), **overrides}
    for name, value in vars(module).items():
        if isinstance(value, FunctionType) and value.__module__ == module.__name__:
            namespace[name] = clone_function(value, namespace)
    return namespace
