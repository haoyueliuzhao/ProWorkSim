import re


def _validated(jobs, max_parallel):
    if type(max_parallel) is not int or not 1 <= max_parallel <= 8:
        raise ValueError("plan:invalid")
    if type(jobs) is not list or not 1 <= len(jobs) <= 12:
        raise ValueError("plan:invalid")
    graph = {}
    for job in jobs:
        if type(job) is not dict or set(job) != {"id", "needs"}:
            raise ValueError("plan:invalid")
        name, needs = job["id"], job["needs"]
        if (type(name) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,15}", name) is None
                or name in graph or type(needs) is not list):
            raise ValueError("plan:invalid")
        if any(type(value) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,15}", value) is None
               for value in needs) or len(needs) != len(set(needs)):
            raise ValueError("plan:invalid")
        graph[name] = set(needs)
    if any(not needs <= graph.keys() for needs in graph.values()):
        raise ValueError("plan:invalid")
    done = set()
    while len(done) < len(graph):
        ready = {name for name, needs in graph.items() if name not in done and needs <= done}
        if not ready:
            raise ValueError("plan:invalid")
        done.update(ready)
    return graph


def plan_jobs(jobs, max_parallel):
    graph = _validated(jobs, max_parallel)
    done, batches = set(), []
    while len(done) < len(graph):
        ready = sorted(name for name, needs in graph.items() if name not in done and needs <= done)
        batch = ready[:max_parallel]
        batches.append(batch)
        done.update(batch)
    return batches
