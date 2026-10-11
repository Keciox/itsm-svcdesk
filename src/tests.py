# ai-generated: 20% - I drafted the smoke-test script and then adjusted it to the repository's expected JSON contract.
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get("SVCDESK_URL", "http://localhost:8080")

passed = 0
failed = 0


def request(method, path, payload=None, headers=None):
    url = BASE_URL.rstrip("/") + path
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body) if body else None


for _ in range(15):
    status, body = request("GET", "/health")
    if status == 200 and body.get("status") == "ok":
        passed += 1
        break
    time.sleep(0.5)
else:
    failed += 1
    print("health check failed")

status, created = request(
    "POST",
    "/tickets",
    {
        "title": "Test ticket",
        "description": "probe",
        "reporter": {"name": "Tester", "email": "tester@example.com", "vip": False},
        "impact": 1,
        "urgency": 2,
    },
    {"X-Test-Clock": "2026-10-14T10:00:00Z"},
)
if status == 201 and created["priority"] == "P2":
    passed += 1
else:
    failed += 1
    print("create ticket check failed", status, created)

status, created2 = request(
    "POST",
    "/tickets",
    {
        "title": "VIP test",
        "reporter": {"name": "VIP User", "vip": True},
        "impact": 3,
        "urgency": 3,
    },
    {"X-Test-Clock": "2026-10-14T10:00:00Z"},
)
if status == 201 and created2["priority"] == "P2":
    passed += 1
else:
    failed += 1
    print("vip priority check failed", status, created2)

status, body = request("GET", "/tickets")
if status == 200 and isinstance(body, list):
    passed += 1
else:
    failed += 1
    print("list check failed", status, body)

print(f"ITSMLAB-TESTS: passed={passed} failed={failed}")
if failed:
    raise SystemExit(1)
