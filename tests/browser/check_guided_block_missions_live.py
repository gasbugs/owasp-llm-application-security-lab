"""Exercise every block mission through the learner-facing navigation."""
from playwright.sync_api import sync_playwright, expect


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    for width in (1440, 390):
        page = browser.new_page(viewport={"width": width, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:28097/", wait_until="networkidle")
        page.locator("#mission-menu-toggle").click()
        page.locator("#p00-menu").click()
        expect(page.locator("#tutorial-panel")).to_be_visible()
        expect(page.locator("#block-lab-tutorial .block-lab-palette-item")).to_have_count(5)
        for number in range(1, 24):
            problem = f"P{number:02}"
            if width < 761:
                page.locator("#mission-menu-toggle").click()
            category = page.locator(f'.tab[data-problem="{problem}"]').locator("xpath=ancestor::details")
            if not category.evaluate("element => element.open"):
                category.locator("summary").click()
            page.locator(f'.tab[data-problem="{problem}"]').click()
            expect(page.locator(f'.tab[data-problem="{problem}"]')).to_have_attribute("aria-selected", "true")
            expect(page.locator("#mission-panel")).to_be_visible()
            mission_title = page.locator(f'.tab[data-problem="{problem}"] strong').inner_text()
            expect(page.locator("#activity-title")).to_have_text(mission_title)
            board = page.locator(".block-lab:visible")
            expect(board).to_have_count(1)
            count = board.locator(".block-lab-palette-item").count()
            assert 5 <= count <= 8, (width, problem, count)
            ids = board.locator(".block-lab-palette-item").evaluate_all(
                "elements => elements.map(element => element.dataset.block)")
            assert len(ids) == len(set(ids)), (width, problem, ids)
            palette_text = board.locator(".block-lab-palette").inner_text()
            assert all(phrase not in palette_text for phrase in
                       ("다른 미션", "다른 실습", "미션에서 쓰는", "문제에서 쓰는")), (width, problem)
            expect(board.get_by_role("button", name="조립한 정답 제출")).to_be_visible()
            assert page.locator("#resource-operation").count() == 1, (width, problem)
        page.locator("#navigation-home").click()
        expect(page.locator("#home-panel")).to_be_visible()
        assert not errors, (width, errors)
        print(f"PASS: {width}px, P00-P23, 5-8 blocks, sidebar and home")
        page.close()
    browser.close()
