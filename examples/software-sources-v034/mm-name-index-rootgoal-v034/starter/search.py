def find_matches(names, query):
    """Search under the shared public name rule."""
    return [index for index, name in enumerate(names) if name == query]
