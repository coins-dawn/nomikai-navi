#!/usr/bin/env python3
"""site/ の中身を点検し、静的版とサーバ版が同じ答えを出すか突き合わせる。

    python3 scripts/verify_static.py            # ファイルの点検だけ
    python3 scripts/verify_static.py --compare  # サーバ版（:8000）との突き合わせも行う
"""
import asyncio, json, random, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
STATIC_URL = "http://127.0.0.1:8010/"
SERVER_URL = "http://127.0.0.1:8000"

DEPART, MIN_BARS, MAX_TRAVEL = 19 * 60, 30, 90


def check_files():
    meta = json.loads((SITE / "data" / "meta.json").read_text())
    nc = len(meta["stations"])
    print(f"駅 {nc} / 路線 {len(meta['rails'])} / 集合時刻 {meta['presets']} / 作成 {meta['built']}")
    assert meta.get("contact", {}).get("contact_url"), "問い合わせ先が meta.json に入っていない"
    assert meta.get("acquired"), "取得日が meta.json に入っていない"
    homes = list((SITE / "data" / "home").glob("*.json"))
    routes = list((SITE / "data" / "route").glob("*.json"))
    shapes = json.loads((SITE / "data" / "rail_shapes.json").read_text())
    real = sum(1 for v in shapes.values() for sgm in v if len(sgm) > 2)
    tot = sum(len(v) for v in shapes.values())
    print(f"home {len(homes)} / route {len(routes)} / 線路なりの駅間 {real}/{tot}")
    assert len(homes) == nc, "自宅ファイルが足りない"
    assert len(routes) == nc, "経路ファイルが足りない"
    for f in random.sample(homes, min(30, len(homes))):
        d = json.loads(f.read_text())
        assert len(d["limit"]) == nc
        for p in meta["presets"]:
            assert len(d["travel"][str(p)]) == nc, f"{f.name} に集合時刻 {p} がない"
        assert len(d["back"]) == nc, f"{f.name} に帰りの所要時間がない（build_back.py）"
    total = sum(f.stat().st_size for f in SITE.rglob("*") if f.is_file())
    print(f"合計 {total/1e6:.1f}MB / {sum(1 for f in SITE.rglob('*') if f.is_file())} ファイル")
    return meta


def server_top(people):
    body = json.dumps({"people": people, "depart": DEPART,
                       "min_bars": MIN_BARS, "max_travel": MAX_TRAVEL}).encode()
    req = urllib.request.Request(f"{SERVER_URL}/api/search", data=body)
    j = json.loads(urllib.request.urlopen(req).read())
    return [(c["name"], c["cost"], c["min_limit"], c["min_stay"]) for c in j["candidates"]]


async def static_top():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--disable-dev-shm-usage"])
        pg = await b.new_page(viewport={"width": 1500, "height": 950})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        await pg.goto(STATIC_URL, wait_until="networkidle")
        await pg.click("#sample")
        await pg.wait_for_timeout(1200)
        await pg.click("#compare")                 # 2. 日付と駅を比べる
        await pg.wait_for_selector(".day", timeout=60000)
        await pg.locator(".day").first.click()      # いちばん移動が少ない候補を開く
        await pg.wait_for_selector(".who", timeout=60000)
        await pg.wait_for_timeout(5000)
        rows = await pg.evaluate("() => RESULT.candidates.map(c => [c.name, c.cost, c.min_limit, c.min_stay])")
        people = await pg.evaluate("() => RESULT._people.map(({ci, ...p}) => p)")
        await pg.screenshot(path="docs/20-static.png")
        await pg.evaluate("() => { MAP.easeTo({center:[139.76,35.70],zoom:12.2,duration:0}); return null }")
        await pg.wait_for_timeout(5000)
        await pg.locator("#mapwrap").screenshot(path="docs/21-static-zoom.png")
        print("console errors:", errs[:5] or "なし")
        await b.close()
        return [tuple(r) for r in rows], people


if __name__ == "__main__":
    check_files()
    if "--compare" in sys.argv:
        t, people = asyncio.run(static_top())
        s = server_top(people)   # 静的版で選んだ日の参加者（会社から／自宅から）をそのまま渡す
        print("サーバ版:", s)
        print("静的版　:", t)
        print("一致" if s == t else "**不一致**")
        sys.exit(0 if s == t else 1)
