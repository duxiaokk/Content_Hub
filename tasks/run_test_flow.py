"""Content Hub 运行测试脚本：执行一次完整业务流程并检测错误"""
import httpx
import json
import sys
import traceback
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"

results = []
errors = []

def log_step(step, status, detail=""):
    ts = datetime.now().strftime("%H:%M:%S")
    icon = "[OK]" if status == "OK" else "[FAIL]"
    msg = f"[{ts}] {icon} {step} -> {status}"
    if detail:
        msg += f" | {detail}"
    print(msg)
    results.append({"step": step, "status": status, "detail": detail, "time": ts})
    if status != "OK":
        errors.append({"step": step, "detail": detail})

def main():
    c = httpx.Client(base_url=BASE_URL, follow_redirects=True)

    # ===== Step 1: 健康检查 =====
    try:
        r = c.get("/")
        log_step("服务健康检查", "OK", f"status={r.status_code}")
    except Exception as e:
        log_step("服务健康检查", "FAIL", str(e))
        return

    # ===== Step 2: 注册用户 =====
    try:
        r = c.post("/api/v1/auth/register", json={
            "username": "testuser2", "email": "test2@test.com", "password": "test123456"
        })
        if r.status_code == 200:
            log_step("注册用户", "OK", "用户 testuser2 注册成功")
        else:
            data = r.json()
            log_step("注册用户", "WARN", f"可能已存在: {data.get('message','')}")
    except Exception as e:
        log_step("注册用户", "FAIL", str(e))
        return

    # ===== Step 3: 登录 =====
    try:
        r = c.post("/api/v1/auth/login", json={
            "username": "testuser2", "password": "test123456", "remember": True
        })
        data = r.json()
        token = data.get("data", {}).get("access_token", "")
        if token:
            c.headers.update({"Authorization": f"Bearer {token}"})
            log_step("登录获取Token", "OK", f"token前20: {token[:20]}...")
        else:
            log_step("登录获取Token", "FAIL", "未获取到token")
            return
    except Exception as e:
        log_step("登录获取Token", "FAIL", str(e))
        return

    # ===== Step 4: 创建 SourceConfig (RSS源) =====
    import time
    src_name = f"test-rss-{int(time.time())}"
    try:
        r = c.post("/api/v1/console/sources", json={
            "name": src_name,
            "source_type": "rss",
            "enabled": True,
            "channels": ["https://feeds.feedburner.com/TheHackersNews"],
            "keywords": ["security", "python"],
            "lookback_hours": 48,
            "item_limit": 10
        })
        if r.status_code == 200:
            data = r.json()
            log_step("创建SourceConfig", "OK", json.dumps(data.get("data",{}), ensure_ascii=False)[:150])
        else:
            log_step("创建SourceConfig", "FAIL", f"status={r.status_code}, body={r.text[:200]}")
            return
    except Exception as e:
        log_step("创建SourceConfig", "FAIL", str(e))
        return

    # ===== Step 5: 列出 Sources =====
    try:
        r = c.get("/api/v1/console/sources")
        if r.status_code == 200:
            data = r.json()
            sources = data.get("data", [])
            log_step("列出Sources", "OK", f"共 {len(sources)} 个源")
        else:
            log_step("列出Sources", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_step("列出Sources", "FAIL", str(e))

    # ===== Step 6: 触发 Fetch 任务 =====
    try:
        # 先获取 sources 列表拿到 id
        r = c.get("/api/v1/console/sources")
        sources = r.json().get("data", [])
        if not sources:
            log_step("触发Fetch", "SKIP", "没有可用 source")
        else:
            source_id = sources[0]["id"]
            r = c.post(f"/api/v1/console/sources/{source_id}/run", json={
                "lookback_hours": 24,
                "item_limit": 5,
                "dry_run": False
            })
            if r.status_code == 200:
                data = r.json()
                log_step("触发Fetch任务", "OK", json.dumps(data.get("data",{}), ensure_ascii=False)[:200])
            else:
                log_step("触发Fetch任务", "FAIL", f"status={r.status_code}, body={r.text[:300]}")
    except Exception as e:
        log_step("触发Fetch任务", "FAIL", str(e))

    # ===== Step 7: 列出 Fetch Runs =====
    try:
        r = c.get("/api/v1/console/fetch-runs")
        if r.status_code == 200:
            data = r.json()
            runs = data.get("data", {}).get("items", data.get("data", []))
            log_step("列出FetchRuns", "OK", f"共 {len(runs)} 条记录")
        else:
            log_step("列出FetchRuns", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_step("列出FetchRuns", "FAIL", str(e))

    # ===== 输出摘要 =====
    print("\n" + "="*60)
    print("  执 行 摘 要")
    print("="*60)
    for r in results:
        print(f"  {r['status']:5s} | {r['step']:20s} | {r['detail'][:80]}")
    
    if errors:
        print(f"\n!!! 发现 {len(errors)} 个错误/异常:")
        for e in errors:
            print(f"  - [{e['step']}] {e['detail']}")
        print("\n结论: 流程执行存在错误，请检查上述异常信息")
    else:
        print("\n结论: 流程执行整体正常，未发现异常错误")

if __name__ == "__main__":
    main()
