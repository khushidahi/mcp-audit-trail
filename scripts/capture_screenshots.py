"""Capture README screenshots from the demo report using Playwright."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

REPORT = Path(__file__).resolve().parent.parent / "audit_report.html"
OUT = Path(__file__).resolve().parent.parent / "docs" / "images"


async def main():
    OUT.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1060, "height": 900})
        await page.goto(f"file://{REPORT}")
        await page.wait_for_load_state("networkidle")

        # 1. Full overview — summary + tools + data access
        print("1. Capturing header + summary...")
        await page.screenshot(
            path=str(OUT / "summary.png"),
            clip={"x": 0, "y": 0, "width": 1060, "height": 580},
        )

        # 2. Tool usage + data access map
        print("2. Capturing tool usage + data access map...")
        tools_section = page.locator(".section-title", has_text="Tools Used")
        tools_box = await tools_section.bounding_box()
        # Capture from tools section through data access map
        await page.screenshot(
            path=str(OUT / "tools-and-data.png"),
            clip={
                "x": 0,
                "y": tools_box["y"] - 16,
                "width": 1060,
                "height": 460,
            },
        )

        # 3. Timeline with a couple events expanded
        print("3. Capturing timeline with expanded events...")
        # Click first 3 events to expand them
        cards = page.locator(".event-card")
        count = await cards.count()
        for i in range(min(3, count)):
            await cards.nth(i).click()
            await page.wait_for_timeout(100)

        timeline_section = page.locator(".section-title", has_text="Event Timeline")
        timeline_box = await timeline_section.bounding_box()
        await page.screenshot(
            path=str(OUT / "timeline.png"),
            clip={
                "x": 0,
                "y": timeline_box["y"] - 16,
                "width": 1060,
                "height": 820,
            },
        )

        # 4. Full-page for a nice hero shot
        print("4. Capturing full page...")
        # collapse events first, then expand just #3 and #4 (sensitive + write)
        for i in range(min(3, count)):
            await cards.nth(i).click()
            await page.wait_for_timeout(50)

        # expand the sensitive (pay info) and write (time off) events
        await cards.nth(2).click()  # get_pay_info
        await page.wait_for_timeout(100)
        await cards.nth(3).click()  # submit_time_off
        await page.wait_for_timeout(100)

        await page.screenshot(
            path=str(OUT / "full-report.png"),
            full_page=True,
        )

        await browser.close()

    print(f"\nScreenshots saved to {OUT}/")
    for img in sorted(OUT.glob("*.png")):
        print(f"  {img.name}")


asyncio.run(main())
