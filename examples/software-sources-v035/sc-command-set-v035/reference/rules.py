from schema import Schema, Or, SchemaError


def validate_commands(commands):
    validator = Schema([{"op": Or("put", "drop"), "name": str}])
    try:
        return validator.validate(commands)
    except SchemaError:
        return None
