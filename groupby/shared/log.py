"""로그. 한 줄에 JSON 하나를 표준 출력으로 낸다 (11_log/log.md)."""
import json
import re
import secrets
import sys
from datetime import datetime

TRACE_ID = re.compile(r"[0-9a-f]{8}")


def new_trace_id() -> str:
    return secrets.token_hex(4)


def trace_id_or_new(value: str | None) -> str:
    return value if value and TRACE_ID.fullmatch(value) else new_trace_id()


def log(service: str, trace_id: str, event: str, level: str = "INFO", **fields) -> None:
    record = {
        "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "level": level,
        "service": service,
        "trace_id": trace_id,
        "event": event,
        **{k: v for k, v in fields.items() if v is not None},
    }
    print(json.dumps(record, ensure_ascii=False), file=sys.stdout, flush=True)
