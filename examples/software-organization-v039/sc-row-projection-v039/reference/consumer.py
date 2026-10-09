from columns import validate_columns


def project_rows(rows, columns):
    selected = validate_columns(columns)
    if selected is None:
        return {"ok": False, "columns": [], "rows": []}
    return {"ok": True, "columns": selected,
            "rows": [[row.get(name) for name in selected] for row in rows]}
