import io
from pathlib import Path
import textfsm


def port_records(text):
    parser = textfsm.TextFSM(io.StringIO(Path("ports.template").read_text()))
    return [{"name": name, "state": state} for name, state in parser.ParseText(text)]
