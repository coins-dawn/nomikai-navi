import asyncio, sys
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8000/"
STEP = sys.argv[1] if len(sys.argv) > 1 else "all"


async def setup(pg, initial=False):
    await pg.goto(URL, wait_until="networkidle")
    if initial:
        await pg.wait_for_timeout(4000)
        await pg.screenshot(path="docs/09-start.png")
    await pg.click("#sample")
    await pg.wait_for_timeout(2500)
    await pg.click("#go")
    await pg.wait_for_selector(".cand", timeout=90000)
    await pg.wait_for_timeout(7000)


async def shoot(scheme, suffix, zoom_in):
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--disable-dev-shm-usage"])
        pg = await b.new_page(viewport={"width": 1600, "height": 950},
                              device_scale_factor=1, color_scheme=scheme)
        errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await setup(pg, initial=not zoom_in and suffix == "")
        if zoom_in:
            # 戻り値に Map オブジェクトを返すと Playwright が丸ごと直列化して落ちるので null を返す
            await pg.evaluate("() => { MAP.easeTo({center:[DETAIL.lon,DETAIL.lat],zoom:15.3,duration:0}); return null; }")
            await pg.wait_for_timeout(5000)
            await pg.locator("#mapwrap").screenshot(path=f"docs/12-bars{suffix}.png")
        else:
            await pg.screenshot(path=f"docs/10-map{suffix}.png")
            await pg.locator(".cand").nth(2).click()
            await pg.wait_for_timeout(6000)
            await pg.screenshot(path=f"docs/11-map-other{suffix}.png")
        print("console errors:", errs[:6] or "なし")
        await b.close()


if STEP in ("all", "dark"):
    asyncio.run(shoot("dark", "", False))
if STEP in ("all", "bars"):
    asyncio.run(shoot("dark", "", True))
if STEP in ("all", "light"):
    asyncio.run(shoot("light", "-light", False))
