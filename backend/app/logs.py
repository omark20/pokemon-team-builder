"""Log lines: one line per event, `event key=value ...`, and never a secret.

Every field value is an integer, one of the app's own constants, or a string from
outside wrapped by `outside()`, which escapes it so it cannot start a new line or fake
a field. Exceptions are logged by class and traceback frames only, never by message,
because a message can quote a connection string or the input that was rejected.
"""

import logging
import sys
import time
import traceback

from starlette.requests import Request
from starlette.routing import Route

LINE_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure() -> None:
    """Send INFO and above to standard output, each line stamped in UTC."""
    formatter = logging.Formatter(LINE_FORMAT, datefmt="%Y-%m-%dT%H:%M:%SZ")
    formatter.converter = time.gmtime
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def outside(value: str) -> str:
    """Quote a string that came from outside the app, cut to 100 characters."""
    return repr(value[:100])


def log_event(logger: logging.Logger, level: int, event: str, **fields: int | str) -> None:
    """Write one event line. Callers pass named fields chosen one by one."""
    parts = [event, *(f"{name}={value}" for name, value in fields.items())]
    logger.log(level, "%s", " ".join(parts))


def log_exception(
    logger: logging.Logger, event: str, exc: BaseException, **fields: int | str
) -> None:
    """Log an exception by class and frames (file:line:function), without its message.

    This is the only place exceptions are logged; nothing else uses exc_info.
    """
    frames = ",".join(
        f"{frame.filename}:{frame.lineno}:{frame.name}"
        for frame in traceback.extract_tb(exc.__traceback__)
    )
    log_event(logger, logging.ERROR, event, **fields, error_class=type(exc).__name__, frames=frames)


def route_template(request: Request) -> str:
    """The matched route's template, such as /api/teams/{team_id}, never the raw path.

    A raw path is decoded visitor text and could hold a line break; a template cannot.
    """
    route = request.scope.get("route")
    return route.path if isinstance(route, Route) else "unmatched"
