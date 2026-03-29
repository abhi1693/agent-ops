from contextvars import ContextVar, Token


_current_request: ContextVar = ContextVar("agent_ops_current_request", default=None)


def get_current_request():
    return _current_request.get()


def set_current_request(request) -> Token:
    return _current_request.set(request)


def reset_current_request(token: Token) -> None:
    _current_request.reset(token)
