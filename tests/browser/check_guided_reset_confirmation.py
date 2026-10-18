"""The reset bridge must not be contacted before the learner chooses Yes."""

import os

from playwright.sync_api import expect, sync_playwright


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page()
    page.goto(os.environ["GUIDED_UI_BASE_URL"], wait_until="networkidle")
    page.evaluate("""() => {
      const realFetch = window.fetch.bind(window);
      window.resetRequests = [];
      window.fetch = (input, options = {}) => {
        const url = String(input);
        if (!url.startsWith('http://127.0.0.1:28198/')) return realFetch(input, options);
        const path = new URL(url).pathname;
        window.resetRequests.push(`${options.method || 'GET'} ${path}`);
        const payload = path === '/scope'
          ? {practice_files: 2, mission_containers: 3, mission_volumes: 4,
             aws_resources: {s3: 0}, p00_request: false}
          : path === '/status' ? {state: 'complete'} : {state: 'running'};
        return Promise.resolve(new Response(JSON.stringify(payload), {
          status: 200, headers: {'Content-Type': 'application/json'}
        }));
      };
    }""")

    page.locator("#practice-reset-button").click()
    assert page.locator("#practice-reset-confirm").is_visible()
    assert page.evaluate("window.resetRequests") == []
    page.locator('#practice-reset-confirm button[value="no"]').click()
    expect(page.locator("#practice-reset-status")).to_have_text("초기화를 취소했습니다.")
    assert page.evaluate("window.resetRequests") == []

    page.locator("#practice-reset-button").click()
    assert page.locator("#practice-reset-confirm").is_visible()
    assert page.evaluate("window.resetRequests") == []
    page.locator('#practice-reset-confirm button[value="yes"]').click()
    page.locator("#practice-reset-complete").wait_for(state="visible", timeout=10000)
    assert page.evaluate("window.resetRequests") == [
        "GET /scope", "POST /reset", "GET /status"
    ]
    assert "복원 완료" in page.locator("#practice-reset-complete").inner_text()
    expect(page.locator("#practice-reset-status")).to_contain_text("복원 완료")
    assert page.locator("#practice-reset-reload-button").is_disabled()
    page.keyboard.press("Escape")
    assert page.locator("#practice-reset-complete").is_visible()
    expect(page.locator("#practice-reset-reload-button")).to_be_enabled(timeout=12000)
    assert page.locator("#practice-reset-reload-progress").evaluate("element => element.value") == 10
    assert page.locator("#practice-reset-reload-button").inner_text() == "확인하고 새로고침"
    with page.expect_navigation(wait_until="networkidle"):
        page.locator("#practice-reset-reload-button").click()
    assert not page.locator("#practice-reset-complete").is_visible()
    browser.close()

print("PASS: No makes no reset request; Yes checks scope before reset; completion waits 10 seconds")
