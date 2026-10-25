"""API smoke test. Run with the server already running.

    python scripts/smoke_test.py [base_url]

Works in mock mode and live mode. In live mode, if data is not initialized,
the script exits with code 2 and prints the ingestion hint.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")


def call(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def main() -> int:
    status, health = call("GET", "/api/health")
    assert status == 200 and health.get("status") == "ok", health
    print("health:", health)

    status, data_status = call("GET", "/api/status")
    assert status == 200, data_status
    print("status:", data_status.get("mode"), "ready=", data_status.get("ready"))

    status, parsed = call(
        "POST",
        "/api/parse",
        {"query": "经营改善、估值合理、走势相对稳定", "universe": "all_a_share"},
    )
    assert status == 200, parsed
    groups = [group["label"] for group in parsed["dsl"]["groups"]]
    assert groups == ["经营改善", "估值合理", "走势相对稳定"], groups
    print("parse:", parsed["parser"], groups)

    status, preview = call("POST", "/api/preview", {"dsl": parsed["dsl"]})
    if status != 200:
        print("preview failed:", preview)
        hint = preview.get("error", {}).get("hint")
        if hint:
            print("hint:", hint)
            return 2
        return 1
    print("preview:", preview["summary"])

    job_status, job = call("POST", "/api/screen/jobs", {"dsl": parsed["dsl"]})
    assert job_status == 200, job
    job_id = job["job_id"]
    result = None
    for _ in range(120):
        status, job = call("GET", f"/api/screen/jobs/{job_id}")
        assert status == 200, job
        if job["status"] == "done":
            result = job["result"]
            break
        if job["status"] == "failed":
            print("job failed:", job.get("error"))
            return 1
        time.sleep(0.5)
    assert result is not None, "job timed out"
    summary = result["summary"]
    print("screen:", summary)
    assert summary["included"] + summary["near_miss"] + summary["excluded"] + summary["unknown"] == summary["returned"]
    assert summary["included"] > 0

    status, diagnosis = call("POST", "/api/diagnose", {"query": "600036", "dsl": parsed["dsl"]})
    if status == 200:
        print("diagnose:", diagnosis["stock"]["name"], diagnosis["stock"]["status"])
    else:
        print("diagnose skipped:", diagnosis)

    status, explanation = call("POST", "/api/explain", {"query": "600036", "dsl": parsed["dsl"]})
    if status == 200:
        print("explain:", explanation["explanation"]["mode"], explanation["explanation"]["text"][:60])

    status, strategies = call("GET", "/api/strategies")
    assert status == 200, strategies
    print("strategies:", len(strategies.get("items", [])))

    print("OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print("FAIL:", exc)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print("ERROR:", type(exc).__name__, exc)
        sys.exit(1)
