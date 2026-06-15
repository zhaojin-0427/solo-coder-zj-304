import urllib.request
import urllib.error
import json
import sys

BASE = "http://localhost:8000"


def http_get(path):
    with urllib.request.urlopen(BASE + path) as r:
        return json.loads(r.read().decode('utf-8'))


def http_post(path, data):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode('utf-8'),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode('utf-8'))


def main():
    results = []

    # 准备数据
    print("\n=== 准备测试数据 ===")
    med_resp = http_post("/api/medicines", {
        "name": "布洛芬混悬液",
        "medicine_type": "FEVER",
        "expiry_date": "2027-05-01",
        "current_stock": 2,
        "min_stock": 1,
        "min_age_months": 6,
        "max_age_months": 216,
        "post_open_validity_days": 30
    })
    print("创建药品:", med_resp.get("message"))

    # 验证1: days 参数
    print("\n=== 验证1: expiry-monitor days 参数 ===")
    d30 = http_get("/api/risk/expiry-monitor?days=30")
    d400 = http_get("/api/risk/expiry-monitor?days=400")
    cnt30 = d30["data"]["expiring_soon_count"]
    cnt400 = d400["data"]["expiring_soon_count"]
    print(f"  days=30  临期数: {cnt30}")
    print(f"  days=400 临期数: {cnt400}")
    ok = cnt400 > cnt30
    results.append(("days参数生效", ok))
    print("  ", "✅ 通过" if ok else "❌ 失败")

    # 验证2: 宝宝出生日期未来日期校验
    print("\n=== 验证2: 宝宝出生日期不能是未来日期 ===")
    resp = http_post("/api/baby", {
        "name": "未来宝宝",
        "birth_date": "2030-01-01"
    })
    code = resp.get("code")
    msg = resp.get("message", "")
    print(f"  响应 code: {code}")
    print(f"  响应 message: {msg[:80]}")
    ok = (code == 422) and ("不能晚于今天" in msg)
    results.append(("未来日期校验", ok))
    print("  ", "✅ 通过" if ok else "❌ 失败")

    # 验证3: 统计接口不存在的 baby_id
    print("\n=== 验证3: 统计接口不存在的 baby_id 报错 ===")
    resp = http_get("/api/statistics/overview?baby_id=9999")
    code = resp.get("code")
    msg = resp.get("message", "")
    print(f"  响应 code: {code}")
    print(f"  响应 message: {msg}")
    ok = code == 404
    results.append(("不存在的baby_id报错", ok))
    print("  ", "✅ 通过" if ok else "❌ 失败")

    # 验证4: 月龄建议文案
    print("\n=== 验证4: 月龄校验建议文案 ===")
    med_id = med_resp["data"]["id"]
    resp = http_get(f"/api/risk/age-check/{med_id}?age_months=12")
    advice = resp["data"]["advice"]
    print(f"  建议: {advice[:100]}")
    ok = ("【适用" in advice) or ("【不适用】" in advice)
    results.append(("月龄建议文案格式", ok))
    print("  ", "✅ 通过" if ok else "❌ 失败")

    # 汇总
    print("\n" + "=" * 50)
    print("测试汇总:")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")
    print(f"\n共 {total} 项，通过 {passed} 项，失败 {total - passed} 项")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
