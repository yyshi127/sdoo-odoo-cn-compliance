"""Check that a China compliance preview URL is reachable for UAT handoff."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SCHEMA = "sdoo.cn.preview-health.v1"
BLOCKING_MARKERS = (
    "Internal Server Error",
    "Traceback",
    "Session expired",
    "invalid CSRF token",
    "Database not found",
)


def _check(url: str, timeout: int) -> dict[str, object]:
    result: dict[str, object] = {
        "schema": SCHEMA,
        "checked_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "url": url,
        "ok": False,
        "status_code": None,
        "blocking_marker": None,
        "error": None,
    }
    request = Request(url, headers={"User-Agent": "sdoo-cn-preview-health/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(512_000).decode("utf-8", errors="replace")
            result["status_code"] = response.getcode()
    except HTTPError as exc:
        result["status_code"] = exc.code
        try:
            body = exc.read(512_000).decode("utf-8", errors="replace")
        except Exception:
            body = ""
    except URLError as exc:
        result["error"] = str(exc.reason)
        return result
    except TimeoutError as exc:
        result["error"] = str(exc)
        return result

    for marker in BLOCKING_MARKERS:
        if marker in body:
            result["blocking_marker"] = marker
            return result

    status_code = result["status_code"]
    result["ok"] = isinstance(status_code, int) and 200 <= status_code < 500
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check a China compliance preview URL.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--json-output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = _check(args.url, args.timeout)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    if result["ok"]:
        print(f"preview health passed: {args.url}")
        return 0
    print(f"preview health failed: {args.url}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
