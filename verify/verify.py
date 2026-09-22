"""验收服务：通过真实 API 与无头浏览器对联调环境做端到端复核。

复核内容
--------
1. 等待前端 / 后端健康检查通过；
2. API 级校验：四类示例（唯一 / 歧义 / 无解 / 现场噪声）经 nginx 代理
   调用 POST /api/match，核对状态、目标值、见证数量与预算标记；
3. 浏览器级校验：加载页面 → 载入示例 → 发起对位 → 检查状态横幅、
   统计指标、环形图组弧、组明细表、双见证切换与差异高亮、超预算警示；
4. 输出截图到 /artifacts，全部通过时退出码为 0。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.request

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://frontend").rstrip("/")
API_URL = FRONTEND_URL + "/api"
ARTIFACTS = os.environ.get("ARTIFACTS_DIR", "/artifacts")
WAIT_TIMEOUT_S = float(os.environ.get("VERIFY_WAIT_TIMEOUT", "180"))

RESULTS: list[tuple[str, bool, str]] = []
API_CHECKS: list[tuple[str, object]] = []
UI_CHECKS: list[tuple[str, object]] = []


def _register(registry):
    def deco(fn):
        registry.append((fn.__doc__.strip() if fn.__doc__ else fn.__name__, fn))
        return fn

    return deco


api_check = _register(API_CHECKS)
ui_check = _register(UI_CHECKS)


def run_check(name: str, fn) -> None:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))
        print(f"[FAIL] {name}: {exc}", flush=True)
        if os.environ.get("VERIFY_DEBUG"):
            traceback.print_exc()
    else:
        RESULTS.append((name, True, ""))
        print(f"[ ok ] {name}", flush=True)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def wait_http(url: str, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(2)
    raise RuntimeError(f"等待 {url} 超时：{last}")


def http_json(method: str, url: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode() or "{}"
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw}


def load_example(name: str) -> dict:
    with urllib.request.urlopen(f"{FRONTEND_URL}/examples/{name}.json", timeout=10) as resp:
        return json.loads(resp.read().decode())


# ---------------------------------------------------------------------------
# API 级验收
# ---------------------------------------------------------------------------

@api_check
def api_health():
    """API：健康检查"""
    code, data = http_json("GET", f"{API_URL}/health")
    assert code == 200 and data["status"] == "ok", data


@api_check
def api_unique():
    """API：唯一解示例（漏检合并，改动=1，11 组）"""
    code, data = http_json("POST", f"{API_URL}/match", load_example("unique"))
    assert code == 200, data
    assert data["status"] == "unique", data["status"]
    assert data["objective"]["modifications"] == 1, data["objective"]
    assert data["objective"]["totalAbsError"] == 0, data["objective"]
    assert len(data["witnesses"]) == 1
    assert len(data["witnesses"][0]["groups"]) == 11
    assert data["budget"] == {"limit": 4, "used": 1, "within": True}
    assert data["configurationsExamined"] == 2 * 11


@api_check
def api_ambiguous():
    """API：歧义示例（两份不同最优见证）"""
    code, data = http_json("POST", f"{API_URL}/match", load_example("ambiguous"))
    assert code == 200, data
    assert data["status"] == "ambiguous", data["status"]
    assert data["optimalMappingCount"] >= 2
    assert len(data["witnesses"]) == 2
    a, b = data["witnesses"]
    assert a["mappingId"] != b["mappingId"], "两份见证的规范映射必须不同"
    for w in (a, b):
        mods = sum(g["modifications"] for g in w["groups"])
        tot = sum(g["absError"] for g in w["groups"])
        mx = max(g["absError"] for g in w["groups"])
        assert (mods, tot, mx) == (0, 0, 0), (mods, tot, mx)


@api_check
def api_no_solution():
    """API：无解示例"""
    code, data = http_json("POST", f"{API_URL}/match", load_example("no-solution"))
    assert code == 200, data
    assert data["status"] == "no_solution"
    assert data["witnesses"] == [] and data["objective"] is None


@api_check
def api_realistic():
    """API：现场噪声示例（唯一，改动=2，23 组）"""
    code, data = http_json("POST", f"{API_URL}/match", load_example("realistic"))
    assert code == 200, data
    assert data["status"] == "unique", data["status"]
    assert data["objective"]["modifications"] == 2, data["objective"]
    assert len(data["witnesses"][0]["groups"]) == 23


@api_check
def api_circumference_422():
    """API：周长不等返回 422"""
    body = load_example("unique")
    body["measured"] = {"intervals": [51] * 12}
    code, data = http_json("POST", f"{API_URL}/match", body)
    assert code == 422, (code, data)
    assert "周长" in json.dumps(data, ensure_ascii=False)


@api_check
def api_over_budget():
    """API：超预算标记"""
    body = load_example("unique")
    body["budget"] = 0
    code, data = http_json("POST", f"{API_URL}/match", body)
    assert code == 200, data
    assert data["budget"]["within"] is False and data["budget"]["used"] == 1


# ---------------------------------------------------------------------------
# 浏览器级验收
# ---------------------------------------------------------------------------

def run_browser_checks() -> None:
    from playwright.sync_api import expect, sync_playwright

    os.makedirs(ARTIFACTS, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.set_default_timeout(20_000)

        def load_preset(key: str) -> None:
            """点击示例按钮并等待异步加载完成（配置版本号递增即状态已应用）。"""
            version = page.locator('[data-testid="config-version"]').get_attribute("data-version")
            page.click(f'[data-testid="preset-{key}"]')
            expect(page.locator('[data-testid="config-version"]')).not_to_have_attribute(
                "data-version", version
            )
            expect(page.locator(f'[data-testid="preset-{key}"]')).to_have_class(
                re.compile(r"\bactive\b")
            )

        @ui_check
        def ui_home():
            """浏览器：首页加载并自动载入唯一解示例"""
            page.goto(FRONTEND_URL, wait_until="networkidle")
            expect(page).to_have_title("叶尖脉冲对位复核台")
            expect(page.locator('[data-testid="ref-count"]')).to_have_text("12 叶片")
            expect(page.locator('[data-testid="meas-count"]')).to_have_text("11 脉冲")

        @ui_check
        def ui_unique():
            """浏览器：唯一解对位（横幅 / 指标 / 组弧 / 组表）"""
            page.click('[data-testid="align-button"]')
            banner = page.locator('[data-testid="status-banner"]')
            expect(banner).to_have_attribute("data-status", "unique")
            expect(page.locator('[data-testid="stat-mods"]')).to_have_text("1")
            expect(page.locator('[data-testid="stat-total"]')).to_have_text("0")
            expect(page.locator('[data-testid="budget-line"]')).to_contain_text("在预算内")
            # 11 组 → 11 条参考侧组弧 + 11 行组表
            expect(page.locator(".group-arc-ref")).to_have_count(11)
            expect(page.locator('[data-testid="group-table"] tbody tr')).to_have_count(11)
            # 合并组：B02, B03 ↔ #1
            row1 = page.locator('[data-testid="group-row-1"]')
            expect(row1).to_contain_text("B02, B03")
            expect(row1).to_contain_text("100")
            page.screenshot(path=f"{ARTIFACTS}/01-unique.png", full_page=True)

        @ui_check
        def ui_group_highlight():
            """浏览器：组联动高亮"""
            page.hover('[data-testid="group-row-3"]')
            arc = page.locator('.group-arc[data-group-index="3"]')
            expect(arc).to_have_class(re.compile(r"\bactive\b"))
            expect(page.locator(".group-arc.dim").first).to_be_visible()

        @ui_check
        def ui_ambiguous():
            """浏览器：歧义示例（双见证 + 差异高亮）"""
            load_preset("ambiguous")
            page.click('[data-testid="align-button"]')
            banner = page.locator('[data-testid="status-banner"]')
            expect(banner).to_have_attribute("data-status", "ambiguous")
            expect(page.locator('[data-testid="witness-tab-0"]')).to_be_visible()
            expect(page.locator('[data-testid="witness-tab-1"]')).to_be_visible()
            id_a = page.locator('[data-testid="mapping-id"]').inner_text()
            # 差异高亮默认开启：重复间距数据下两份见证的组全部不同
            expect(page.locator(".group-arc.is-diff").first).to_be_visible()
            page.click('[data-testid="witness-tab-1"]')
            id_b = page.locator('[data-testid="mapping-id"]').inner_text()
            assert id_a != id_b, f"切换见证后映射 ID 应变化：{id_a} vs {id_b}"
            page.screenshot(path=f"{ARTIFACTS}/02-ambiguous.png", full_page=True)

        @ui_check
        def ui_no_solution():
            """浏览器：无解示例"""
            load_preset("no-solution")
            page.click('[data-testid="align-button"]')
            banner = page.locator('[data-testid="status-banner"]')
            expect(banner).to_have_attribute("data-status", "no_solution")
            expect(page.locator(".group-arc-ref")).to_have_count(0)
            expect(page.locator('[data-testid="no-solution-hint"]')).to_be_visible()
            page.screenshot(path=f"{ARTIFACTS}/03-no-solution.png", full_page=True)

        @ui_check
        def ui_realistic():
            """浏览器：现场噪声示例（24 叶片环形映射）"""
            load_preset("realistic")
            page.click('[data-testid="align-button"]')
            banner = page.locator('[data-testid="status-banner"]')
            expect(banner).to_have_attribute("data-status", "unique")
            expect(page.locator('[data-testid="stat-mods"]')).to_have_text("2")
            expect(page.locator(".group-arc-ref")).to_have_count(23)
            page.screenshot(path=f"{ARTIFACTS}/04-realistic.png", full_page=True)

        @ui_check
        def ui_over_budget():
            """浏览器：超预算警示"""
            load_preset("unique")
            page.fill('[data-testid="budget-input"]', "0")
            page.click('[data-testid="align-button"]')
            expect(page.locator('[data-testid="status-banner"]')).to_have_attribute(
                "data-status", "unique"
            )
            expect(page.locator('[data-testid="budget-line"]')).to_have_class(
                re.compile(r"\bover\b")
            )
            expect(page.locator('[data-testid="budget-line"]')).to_contain_text("超出预算")

        @ui_check
        def ui_client_validation():
            """浏览器：客户端校验（周长不等拦截）"""
            load_preset("unique")
            page.fill(
                '[data-testid="meas-input"]',
                "50, 100, 51, 49, 53, 47, 55, 45, 49, 51, 51",  # 周长 603 ≠ 600
            )
            page.click('[data-testid="align-button"]')
            expect(page.locator('[data-testid="error-box"]')).to_contain_text("周长")

        # 依次执行全部浏览器检查
        for name, fn in UI_CHECKS:
            run_check(name, fn)

        browser.close()


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> int:
    print(f"[verify] 前端地址：{FRONTEND_URL}", flush=True)
    print(f"[verify] 等待服务健康（最长 {WAIT_TIMEOUT_S:.0f}s）…", flush=True)
    try:
        wait_http(f"{FRONTEND_URL}/healthz", WAIT_TIMEOUT_S)
        wait_http(f"{API_URL}/health", WAIT_TIMEOUT_S)
    except RuntimeError as exc:
        print(f"[FAIL] 服务未就绪：{exc}", flush=True)
        return 1
    print("[ ok ] 服务健康检查通过", flush=True)

    # API 级验收
    for name, fn in API_CHECKS:
        run_check(name, fn)

    # 浏览器级验收（内部注册并执行其余检查项）
    try:
        run_browser_checks()
    except Exception as exc:  # noqa: BLE001
        RESULTS.append(("浏览器：Playwright 运行异常", False, str(exc)))
        print(f"[FAIL] 浏览器验收异常：{exc}", flush=True)
        traceback.print_exc()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print("=" * 60, flush=True)
    for name, ok, detail in RESULTS:
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {name}"
        if detail:
            line += f"  -- {detail}"
        print(line, flush=True)
    print(f"[verify] {passed}/{total} 项通过", flush=True)
    if passed == total:
        print("[verify] 验收通过 ✅", flush=True)
        return 0
    print("[verify] 验收失败 ❌", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
