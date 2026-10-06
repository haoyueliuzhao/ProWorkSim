import io
from pathlib import Path
import textfsm


def batch_values(text):
    parser = textfsm.TextFSM(io.StringIO(Path("batches.template").read_text()))
    return [{"batch": name, "value": int(value)} for name, value in parser.ParseText(text)]
