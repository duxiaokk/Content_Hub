"""检查 FetchRun 执行结果"""
import httpx
import json

c = httpx.Client(base_url="http://127.0.0.1:8000", follow_redirects=True)
r = c.post("/api/v1/auth/login", json={"username": "testuser2", "password": "test123456", "remember": True})
c.headers.update({"Authorization": "Bearer " + r.json()["data"]["access_token"]})

r = c.get("/api/v1/console/fetch-runs")
runs = r.json()["data"]["items"]
run = runs[0]
print(f"status: {run['status']}")
print(f"fetched: {run['fetched_count']}")
print(f"inserted: {run['inserted_count']}")
print(f"deduped: {run['deduped_count']}")
err = run.get("error_message", "") or ""
if err:
    print(f"error_message: {err[:200]}")
else:
    print("error_message: (none)")
print(f"finished_at: {run.get('finished_at', 'null')}")

r2 = c.get("/api/v1/console/content-items")
items = r2.json().get("data", {}).get("items", [])
print(f"\nContentItems stored: {len(items)}")
if items:
    for item in items[:3]:
        print(f"  - [{item['source_type']}] {item['title'][:60]}")
