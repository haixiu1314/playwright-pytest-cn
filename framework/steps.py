"""每个用例维护独立步骤上下文。"""
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter
from framework.security import redact

current_case = ContextVar("current_case", default=None)


@contextmanager
def step(title):
    record = {"title": str(title), "status": "passed", "duration_ms": 0, "error": ""}
    case = current_case.get()
    if case is not None:
        case["steps"].append(record)
    start = perf_counter()
    try:
        yield record
    except BaseException as exc:
        record["status"] = "failed"
        record["error"] = redact(str(exc))
        raise
    finally:
        record["duration_ms"] = round((perf_counter() - start) * 1000, 2)
