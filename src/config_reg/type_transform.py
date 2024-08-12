import typing


def is_type(t):
    return isinstance(t, type) or typing.get_origin(t) is not None
