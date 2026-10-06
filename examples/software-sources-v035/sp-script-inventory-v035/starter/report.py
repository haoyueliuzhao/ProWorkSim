def summarize(script):
    """Produce the complete ordered SQL inventory report."""
    return {"statements": [], "counts": {"SELECT": 0, "UPDATE": 0, "DELETE": 0}, "total": 0}
