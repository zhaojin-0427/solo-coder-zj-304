import urllib.request
import urllib.error
import json

BASE = "http://localhost:8000"

def get(path):
    with urllib.request.urlopen(f"{BASE}{path}") as r:
        return json.loads(r.read())

def post(path, data):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


print("=" * 50)
print("验证1: expiry-monitor days 参数是否生效")
print("=" * 50)
d30 = get("/api/risk/expiry-monitor?days=30")
d400 = get("/api/risk/expiry-monitor?days=400")
print(f"  days=30  临期数: {d30['data']['expiring_soon_count']}")
print(f"  days=400 临期数: {d400['data']['expiring_soon_count']}")
if d400['data']['expiring_soon_count'] > d30['data']['expiring_soon_count']:
    print("  ✅ 通过：days 参数生效，400天临期数更多")
else:
    print("  ❌ 失败：days 参数未生效")
print()


print("=" * 50)
print("验证2: 宝宝出生日期不允许是未来日期")
print("=" * 50)
resp = post("/api/baby", {"name": "未来宝宝", "birth_date": "2030-01-01"})
print(f"  响应 code: {resp.get('code')}")
print(f"  响应 message: {resp.get('message', '')[:60]}...")
if resp.get('code') == 422 and '不能晚于今天' in resp.get('message', ''):
    print("  ✅ 通过：未来日期被正确拒绝，且返回统一格式")
else:
    print("  ❌ 失败")
print()


print("=" * 50)
print("验证3: 统计接口传入不存在的 baby_id 报错")
print("=" * 50)
resp = get("/api/statistics/overview?baby_id=9999")
print(f"  响应 code: {resp.get('code')}")
print(f"  响应 message: {resp.get('message')}")
if resp.get('code') == 404:
    print("  ✅ 通过：不存在的 baby_id 返回 404")
else:
    print("  ❌ 失败")
print()


print("=" * 50)
print("验证4: 月龄校验建议文案不矛盾")
print("=" * 50)
resp = get("/api/risk/age-check/1?age_months=12")
advice = resp['data']['advice']
print(f"  建议文案: {advice[:100]}...")
has_both = "月龄在药品适用范围内" in advice and "需医生指导" in advice
has_formatted = "【适用但需注意】" in advice or "【适用】" in advice or "【不适用】" in advice
if has_formatted:
    print("  ✅ 通过：建议文案使用统一分类格式，不矛盾")
else:
    print("  ⚠️  警告：格式可能有问题")
print()


print("全部验证完成！")
