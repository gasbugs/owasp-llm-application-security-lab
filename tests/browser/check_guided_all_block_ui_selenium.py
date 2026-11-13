"""Exercise learner block submissions through the real Control Center browser UI.

Run with Selenium and a local Chromium/ChromeDriver against the isolated practice
deployment. This mutates learner work and progress; reset the test environment
afterward. The source-side block map supplies candidate IDs, while every action
and verdict is observed through browser controls.
"""

import os
import sys
import time
import importlib.util
import json
from pathlib import Path
import shutil

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select


BASE = os.environ.get("GUIDED_UI_BASE", "http://127.0.0.1:28097/")
BINARY = os.environ.get("CHROMIUM_BINARY") or shutil.which("chromium") or shutil.which("google-chrome")
if not BINARY:
    candidates = sorted((Path.home() / ".cache/ms-playwright").glob("chromium-*/chrome-linux/chrome"))
    BINARY = str(candidates[-1]) if candidates else None
BLOCK_SPEC = os.environ.get("GUIDED_BLOCK_SPEC", str(Path(__file__).resolve().parents[2] / "llm-security-control-plane/guided-control-center/block_submission.py"))
spec = importlib.util.spec_from_file_location("guided_block_submission", BLOCK_SPEC)
block_submission = importlib.util.module_from_spec(spec)
spec.loader.exec_module(block_submission)
ORDER = {
    "P00": ["message", "max_tokens"],
    "P23": ["client", "model_id", "output_tokens", "converse"],
    "P02": ["embedding_model_id", "embedding_dimensions", "s3", "runtime", "put", "embed"],
    "P03": ["agent", "job", "runtime", "knowledge_base_id", "retrieval_count", "retrieve"],
    "P04": ["guardrail_identifier", "guardrail_version", "apply", "converse"],
    "P01": ["limit", "reserve", "model", "settle"],
    "P05": ["refusal", "safe_flow"],
    "P06": ["read_action", "allowlist"],
    "P07": ["safety_model", "safety_flow"],
    "P08": ["secret", "role", "format", "safe"],
    "P09": ["recognizer_import", "entities_both", "register", "release_safe"],
    "P10": ["yes_intro", "recovery_marker", "note_marker", "safe"],
    "P11": ["principal_roles", "tenant", "approved", "provenance", "role_match"],
    "P12": ["authenticate", "authorize_tenant", "protect_input", "retrieve_and_check", "main_and_check", "protect_output"],
    "P13": ["risk_case", "risk_payload", "parse_result", "risk_condition"],
    "P14": ["cap_one", "one_generation", "one_parallel"],
    "P15": ["three_turns", "impact_marker", "sequential", "http_error"],
    "P16": ["regex_import", "direct_pattern", "normalize_text", "match_direct", "match_scope", "block_or_allow"],
    "P17": ["root_span", "child_span", "signal_values", "root_attributes", "structured_log", "decision_counter"],
    "P18": ["current_log", "decision_counts", "exact_trace"],
    "P19": ["closed_calls", "stage_evidence", "same_request", "stop_boundary", "six_fields"],
    "P20": ["alert_expr", "hold_four", "decision_panel"],
    "P21": ["model_check", "server_check", "tool_check", "owner_check", "policy_limits"],
    "P22": ["reject_self", "signed_nonce"],
}


def wait_for(driver, predicate, seconds=300):
    return WebDriverWait(driver, seconds, poll_frequency=0.5).until(predicate)


def resource_status(driver, problem):
    button = driver.find_element(By.CSS_SELECTOR, f'[data-resource-status="{problem}"]')
    driver.execute_script("arguments[0].click()", button)
    wait_for(driver, lambda d: not button.get_attribute("disabled"), 90)
    return driver.execute_script("return arguments[0].parentElement.nextElementSibling.textContent", button)


def wait_for_resource_ready(driver, problem):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        status = resource_status(driver, problem)
        ready = "AWS 자원 확인 완료" in status
        if problem == "P03":
            ready = ready and driver.find_element(By.ID, "knowledge-search-submit").get_attribute("data-resource-ready") == "true"
        if ready:
            print(f"RESOURCE_READY {problem}: {status[:180]}", flush=True)
            return
        time.sleep(5)
    raise AssertionError(f"{problem}: AWS resource readiness not confirmed by UI: {status[:600]}")


def main():
    options = Options()
    if BINARY:
        options.binary_location = BINARY
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,1000")
    targets = sys.argv[1:] or list(ORDER)
    with webdriver.Chrome(options=options) as driver:
        driver.get(BASE)
        for problem in targets:
            if problem not in ORDER:
                raise ValueError(problem)
            # Open the same mission menu and tab a learner uses.
            if problem == "P00":
                driver.find_element(By.ID, "mission-menu-toggle").click()
                driver.find_element(By.ID, "p00-menu").click()
            else:
                tab = driver.find_element(By.CSS_SELECTOR, f'.tab[data-problem="{problem}"]')
                driver.execute_script("arguments[0].closest('details').open = true", tab)
                driver.execute_script("arguments[0].click()", tab)
            if problem in {"P02", "P03", "P04"} and os.environ.get("GUIDED_UI_PROVISION") == "1":
                driver.execute_script("arguments[0].click()", driver.find_element(By.ID, f"h{problem[1:]}-provision"))
                operation = wait_for(driver, lambda d: d.find_element(By.ID, "resource-operation-label").get_attribute("textContent") if
                    "준비 완료" in d.find_element(By.ID, "resource-operation-label").get_attribute("textContent") or
                    "완료 여부" in d.find_element(By.ID, "resource-operation-label").get_attribute("textContent") else None, 900)
                print(f"RESOURCE {problem}: {operation}", flush=True)
                if "준비 완료" not in operation:
                    raise AssertionError(f"{problem}: AWS resource preparation failed")
                wait_for_resource_ready(driver, problem)
            if problem in {"P02", "P03", "P04"} and os.environ.get("GUIDED_UI_DIRECT_ONLY") == "1":
                if problem in {"P03", "P04"}:
                    print(f"STATUS {problem}: {resource_status(driver, problem)[:180]}", flush=True)
                driver.execute_script("arguments[0].click()", driver.find_element(By.ID, "h23-experience-tab"))
                action = {"P02": "document-upload-submit", "P03": "knowledge-search-submit", "P04": "guardrail-chat-submit"}[problem]
                driver.execute_script("arguments[0].click()", driver.find_element(By.ID, action))
                direct = wait_for(driver, lambda d: d.find_element(By.ID, "mission-experience-status").get_attribute("textContent") if
                    any(word in d.find_element(By.ID, "mission-experience-status").get_attribute("textContent") for word in ("완료", "찾았습니다", "응답을 받았습니다", "오류", "진행 중")) else None, 90)
                print(f"DIRECT {problem}: {direct}; raw={driver.find_element(By.ID, 'mission-experience-raw').get_attribute('textContent')[:2500]}", flush=True)
                continue
            board = wait_for(driver, lambda d: next((x for x in d.find_elements(By.CSS_SELECTOR, ".block-lab:not([hidden])") if x.get_attribute("data-problem") == problem), None))
            for block_id in ORDER[problem]:
                card = board.find_element(By.CSS_SELECTOR, f'.block-lab-palette-item[data-block="{block_id}"]')
                driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click()", card)
                if problem in block_submission.BLOCKS:
                    slot = block_submission.BLOCKS[problem][block_id][0]
                    row = board.find_element(By.CSS_SELECTOR, f'.block-lab-row[data-block="{block_id}"]')
                    selects = row.find_elements(By.CSS_SELECTOR, "select.block-lab-slot-select")
                    if selects:
                        Select(selects[0]).select_by_value(slot)
            selected = [x.get_attribute("data-block") for x in board.find_elements(By.CSS_SELECTOR, ".block-lab-row")]
            assert set(selected) == set(ORDER[problem]), (problem, selected)
            button = next(x for x in board.find_elements(By.TAG_NAME, "button") if x.text == "조립한 정답 제출")
            driver.execute_script("arguments[0].click()", button)
            wait_for(driver, lambda d: not button.get_attribute("disabled") or "제출 실패:" in board.find_element(By.CSS_SELECTOR, ".block-lab-status").text)
            status = board.find_element(By.CSS_SELECTOR, ".block-lab-status").text
            if "제출 실패:" in status:
                raise AssertionError(f"{problem}: {status}")
            grade = "tutorial-grade-tab" if problem == "P00" else "p01-grade-tab" if problem == "P01" else "h23-grade-tab"
            wait_for(driver, lambda d: d.find_element(By.ID, grade).get_attribute("aria-selected") == "true", 30)
            if problem != "P00":
                outcome = wait_for(driver, lambda d: d.find_element(By.ID, "request-status").get_attribute("textContent") if
                    any(word in d.find_element(By.ID, "request-status").get_attribute("textContent") for word in ("응답을 받았습니다", "응답 오류")) else None, 180)
                completion = driver.find_element(By.ID, "task-completion").get_attribute("textContent")
                print(f"GRADE {problem}: {outcome} {completion}", flush=True)
                payload = json.loads(driver.find_element(By.ID, "raw").get_attribute("textContent"))
                assert payload.get("activity_id") == problem, (problem, payload.get("activity_id"))
                if "응답 오류" in outcome or "과제: 완료" not in completion:
                    first_case = ((payload.get("result") or {}).get("cases") or [None])[0]
                    raise AssertionError(f"{problem}: grade did not complete: {completion}; execution_id={payload.get('execution_id')}; reason={payload.get('reason')}; first_case={first_case}; diagnosis={payload.get('diagnosis')}; payload={str(payload)[:1800]}")
                assert payload.get("task_completed") is True, (problem, payload)
                assert payload.get("course_verdict") in {"PASS", "HIT"}, (problem, payload)
                assert payload.get("verified_by") == "guided-evidence-verifier", (problem, payload)
                if problem == "P01":
                    driver.execute_script("arguments[0].click()", driver.find_element(By.ID, "p01-model-tab"))
                    driver.execute_script("arguments[0].click()", driver.find_element(By.ID, "chat-send"))
                    direct = wait_for(driver, lambda d: d.find_element(By.ID, "chat-meta").get_attribute("textContent") if
                        "requested " in d.find_element(By.ID, "chat-meta").get_attribute("textContent") else None, 180)
                    print(f"DIRECT {problem}: {direct}", flush=True)
                    continue
                if problem in {"P02", "P03", "P04"}:
                    if problem in {"P03", "P04"}:
                        resource_status(driver, problem)
                    driver.execute_script("arguments[0].click()", driver.find_element(By.ID, "h23-experience-tab"))
                    action = {"P02": "document-upload-submit", "P03": "knowledge-search-submit", "P04": "guardrail-chat-submit"}[problem]
                    driver.execute_script("arguments[0].click()", driver.find_element(By.ID, action))
                    direct = wait_for(driver, lambda d: d.find_element(By.ID, "mission-experience-status").get_attribute("textContent") if
                        any(word in d.find_element(By.ID, "mission-experience-status").get_attribute("textContent") for word in ("완료", "찾았습니다", "응답을 받았습니다", "오류")) else None, 180)
                    print(f"DIRECT {problem}: {direct}", flush=True)
                    if not any(word in direct for word in ("완료되었습니다", "찾았습니다", "응답을 받았습니다")):
                        raise AssertionError(f"{problem}: direct test failed: {direct}; raw={driver.find_element(By.ID, 'mission-experience-raw').get_attribute('textContent')[:1500]}")
                    continue
                if problem == "P23":
                    driver.execute_script("arguments[0].click()", driver.find_element(By.ID, "h23-experience-tab"))
                    driver.execute_script("arguments[0].click()", driver.find_element(By.ID, "h23-chat-send"))
                    result_id = "h23-chat-status"
                else:
                    driver.execute_script("arguments[0].click()", driver.find_element(By.ID, "h23-experience-tab"))
                    driver.execute_script("arguments[0].click()", driver.find_element(By.ID, "mission-experience-run"))
                    result_id = "mission-experience-status"
                direct = wait_for(driver, lambda d: d.find_element(By.ID, result_id).get_attribute("textContent") if
                    any(word in d.find_element(By.ID, result_id).get_attribute("textContent") for word in ("완료", "응답", "오류", "답변을 받았습니다")) else None, 180)
                print(f"DIRECT {problem}: {direct}", flush=True)
                if not any(word in direct for word in ("응답을 받았습니다", "답변을 받았습니다", "완료되었습니다")):
                    raise AssertionError(f"{problem}: direct test failed: {direct}; raw={driver.find_element(By.ID, 'mission-experience-raw').get_attribute('textContent')[:1500]}")
            else:
                tutorial = wait_for(driver, lambda d: d.find_element(By.ID, "tutorial-grade-status").get_attribute("textContent") if
                    "P00 미션 완료!" in d.find_element(By.ID, "tutorial-grade-status").get_attribute("textContent") else None, 60)
                tutorial_payload = json.loads(driver.find_element(By.ID, "tutorial-result").get_attribute("textContent"))
                assert tutorial_payload.get("completed") is True and len(tutorial_payload.get("cases", [])) == 4, tutorial_payload
                assert all(case.get("case_verified") is True for case in tutorial_payload["cases"]), tutorial_payload
                print(f"GRADE P00: {tutorial}", flush=True)
        if len(targets) == len(ORDER) and set(targets) == set(ORDER):
            driver.get(BASE)
            wait_for(driver, lambda d: d.find_element(By.ID, "home-progress").get_attribute("value") == "24", 30)
            assert driver.find_element(By.ID, "home-progress").get_attribute("max") == "24"
            print("HOME: 24 / 24", flush=True)


if __name__ == "__main__":
    main()
