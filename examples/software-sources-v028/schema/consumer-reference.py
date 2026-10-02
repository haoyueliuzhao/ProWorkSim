from schema import Schema


def schema_catalog(specs):
    kinds = {"str": str, "int": int, "bool": bool}
    return [{"name": spec["name"], "schema": Schema(
        {spec["field"]: kinds[spec["kind"]]}, name=spec["name"],
        description=spec["description"]).json_schema("urn:" + spec["name"])}
        for spec in specs]
