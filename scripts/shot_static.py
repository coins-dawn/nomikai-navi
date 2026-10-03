import asyncio, sys
from playwright.async_api import async_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010/"
HOMES = sys.argv[2].split(",") if len(sys.argv) > 2 else ["北千住", "綾瀬", "町屋"]


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--disable-dev-shm-usage"])
        pg = await b.new_page(viewport={"width": 1600, "height": 950}, color_scheme="dark")
        errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(URL, wait_until="networkidle")
        for h in HOMES:
            await pg.click("#add")
            row = pg.locator(".person").last
            await row.locator(".st").fill(h)
        await pg.click("#go")
        await pg.wait_for_selector(".cand", timeout=60000)
        await pg.wait_for_timeout(6000)
        await pg.screenshot(path="docs/20-static.png")
        print("status:", await pg.locator("#status").inner_text())
        print("1位:", await pg.locator(".cand").first.inner_text())
        print("console errors:", errs[:6] or "なし")
        await b.close()

asyncio.run(main())
