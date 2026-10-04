from models import EnvelopeSchema


def unpack_envelope(payload, many=False):
    return EnvelopeSchema().load(payload, many=many)
