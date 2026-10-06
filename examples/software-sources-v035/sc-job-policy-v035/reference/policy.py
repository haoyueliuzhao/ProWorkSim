from schema import Schema, And, SchemaError


def validate_job(job, queues, ceiling):
    validator = Schema({"queue": And(str, lambda name: name in queues),
                        "priority": And(int, lambda value: 0 <= value <= ceiling)})
    try:
        return validator.validate(job)
    except SchemaError:
        return None
