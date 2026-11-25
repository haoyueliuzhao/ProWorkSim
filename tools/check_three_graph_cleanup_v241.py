"""Verify removal of only the container IDs in this pilot's own creation receipts."""

from contextlib import closing
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_three_graph_worker_v241 import PLAN, RUN, read_json, checked, save


def main():
    import docker

    specs = read_json(PLAN / "protocol.json")["roster"]
    sockets = {
        read_json(checked(s["configuration"]))["scorer_request_base"]["docker_socket"]
        for s in specs
    }
    if len(sockets) != 1:
        raise ValueError("Multiple daemon identities")
    paths = []
    for root in (RUN, RUN / "observer-compat-r1", RUN / "reason-compat-r1"):
        for s in specs:
            for arm in ("KEEP", "OSA"):
                candidates = [
                    root / s["case"] / arm / "actor/created.json",
                    *(
                        root / s["case"] / (arm + "-" + kind) / "created.json"
                        for kind in ("code", "delivery")
                    ),
                ]
                paths.extend(p for p in candidates if p.is_file())
    absence = []
    with closing(
        docker.DockerClient(base_url="unix://" + str(Path(sockets.pop()).resolve()), timeout=12)
    ) as client:
        for path in paths:
            cid = read_json(path)["id"]
            if not re.fullmatch("[0-9a-f]{64}", cid):
                raise ValueError("Invalid created identity")
            try:
                client.containers.get(cid)
                absent = False
            except docker.errors.NotFound:
                absent = True
            absence.append(
                dict(creation_receipt=str(path.relative_to(RUN)), container=cid, absent=absent)
            )
    save(
        PLAN / "resource-release.json",
        dict(containers=absence, all_absent=all(x["absent"] for x in absence), gpu_used=False),
    )


if __name__ == "__main__":
    main()
