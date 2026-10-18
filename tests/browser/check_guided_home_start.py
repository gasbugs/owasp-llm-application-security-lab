"""The home start action follows P00 before the first graded mission."""

import os

from playwright.sync_api import expect, sync_playwright


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page()
    mutations = []
    page.on("request", lambda request: mutations.append(request.url) if request.method == "POST" else None)
    page.goto(os.environ["GUIDED_UI_BASE_URL"], wait_until="networkidle")
    page.evaluate("completedPractices.clear(); p00Completed = false; renderHomeProgress()")
    expect(page.locator("#home-next")).to_have_text("P00 시작하기")
    assert page.locator("#home-next").get_attribute("data-problem") == "P00"
    page.locator("#home-next").click()
    expect(page.locator("#tutorial-panel")).to_be_visible()

    page.evaluate("p00Completed = true; selectWorkspace('home'); renderHomeProgress()")
    expect(page.locator("#home-next")).to_have_text("P01-01 시작하기")
    assert page.locator("#home-next").get_attribute("data-problem") == "P23"
    page.locator("#home-next").click()
    expect(page.locator("#mission-guidance")).to_be_visible()
    assert page.evaluate("activeProblem") == "P23"
    assert not mutations, mutations
    browser.close()

print("PASS: home begins with P00, then advances to P01-01 without progress writes")
