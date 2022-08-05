class UnknownCommandError(Exception):
    """Command is not known (used when parsing devices reply)."""


class InvalidReplyError(Exception):
    """Reply can not be parsed, e.g. wrong datatype (used when parsing devices reply)."""


class ChannelError(Exception):
    """Channel has a problem (used when parsing devices reply)."""


class ParameterError(Exception):
    """Parameter not accepted (used when parsing devices reply)."""
