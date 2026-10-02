import io
import textfsm

TEMPLATE = 'Value Required KEY (\\w+)\nValue List ITEM (\\S+)\n\nStart\n ^key: ${KEY}\n ^item: ${ITEM}\n ^end -> Record\n'


def record_items(text):
    records = textfsm.TextFSM(io.StringIO(TEMPLATE)).ParseText(text)
    return [{"key": key, "items": list(items)} for key, items in records]
