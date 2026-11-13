"""Check drag feedback without changing learner code or submitting a mission."""
from playwright.sync_api import sync_playwright, expect


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1400})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://127.0.0.1:28097/", wait_until="networkidle")
    page.locator('.home-mission[data-problem="P23"]').click()
    card = page.locator('.block-lab-palette-item:not([hidden])').first
    stack = page.locator('.block-lab-stack:visible')
    card.scroll_into_view_if_needed()
    source, destination = card.bounding_box(), stack.bounding_box()
    assert source and destination
    start = (source["x"] + source["width"] / 2, source["y"] + 25)
    end = (destination["x"] + destination["width"] / 2,
           destination["y"] + destination["height"] / 2)
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*end, steps=12)
    expect(page.locator('.block-lab-drag-preview')).to_be_visible()
    expect(page.locator('.block-lab-insertion:not([hidden])')).to_be_visible()
    assert page.evaluate('window.getSelection().toString()') == ''
    page.mouse.up()
    expect(page.locator('.block-lab-drag-preview')).to_have_count(0)
    expect(page.locator('.block-lab-workspace li[data-block]')).to_have_count(1)
    assert page.evaluate('window.getSelection().toString()') == ''
    assert not errors, errors
    print('PASS: drag preview, insertion target, no selected text, one placed block')
    browser.close()
