#!/usr/bin/env python3
"""Process allowlisted block submissions outside the web container."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / ".state/block-build-jobs"
PRACTICE = Path.home() / "owasp-llm-practice"
TARGETS = {
    "P01": ("P03-01", "P03-01_learner.py", "llm-security-guided-h01-gateway", "/app/learner.py"),
    "P05": ("P04-01", "P04-01_flows.co", "llm-security-guided-h05-nemo-dialog", "/app/learner/config/flows.co"),
    "P06": ("P04-02", "P04-02_actions.py", "llm-security-guided-h06-nemo-action", "/app/learner/actions.py"),
    "P07": ("P04-03", "P04-03_config.yml", "llm-security-guided-h07-content-safety", "/app/learner/config/config.yml"),
    "P08": ("P04-04", "P04-04_prompts.yml", "llm-security-guided-h08-self-check-input", "/app/learner/config/prompts.yml"),
    "P09": ("P04-05", "P04-05_policy.py", "llm-security-guided-h09-presidio-redaction", "/app/learner/policy.py"),
    "P10": ("P04-06", "P04-06_prompts.yml", "llm-security-guided-h10-self-check-output", "/app/learner/config/prompts.yml"),
    "P11": ("P04-07", "P04-07_policy.py", "llm-security-guided-h11-rag-provenance", "/app/learner/policy.py"),
    "P12": ("P04-08", "P04-08_pipeline.py", "llm-security-guided-h12-application-pipeline", "/app/learner/pipeline.py"),
    "P13": ("P05-01", "P05-01_promptfooconfig.yaml", "llm-security-guided-h13-promptfoo", "/work/promptfooconfig.yaml"),
    "P14": ("P05-02", "P05-02_garak-config.yaml", "llm-security-guided-h14-garak", "/work/garak-config.yaml"),
    "P15": ("P05-03", "P05-03_attack.py", "llm-security-guided-h15-pyrit", "/work/attack.py"),
    "P16": ("P05-04", "P05-04_policy.py", "llm-security-guided-h16-policy-promotion", "/app/policy.py"),
    "P17": ("P06-01", "P06-01_instrumentation.py", "llm-security-guided-h17-telemetry", "/app/instrumentation.py"),
    "P18": ("P06-02", "P06-02_queries.yaml", "llm-security-guided-h18-queries", "/app/h18.yaml"),
    "P19": ("P06-03", "P06-03_investigation.py", "llm-security-guided-h19-investigation", "/app/investigation.py"),
    "P20": ("P06-04", "P06-04_rules.yaml", "llm-security-guided-h20-alerts", "/app/rules.yaml"),
    "P21": ("P07-01", "P07-01_policy.py", "llm-security-guided-h21-host", "/app/policy.py"),
    "P22": ("P07-02", "P07-02_server.py", "llm-security-guided-h22-mcp-server", "/app/server.py"),
}
P20_SEPARATOR = b"\n# === P06-04_dashboard.json ===\n"


def wait_healthy(container: str, timeout_seconds: int = 180) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        state = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", container],
            text=True, capture_output=True, timeout=10, check=False,
        )
        if state.returncode == 0 and state.stdout.strip() == "healthy":
            return
        if state.returncode == 0 and state.stdout.strip() == "unhealthy":
            raise RuntimeError("mission service failed its readiness check")
        time.sleep(2)
    raise RuntimeError("mission service readiness timed out")


def write_result(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def require_container_digest(container: str, installed_path: str, digest: str) -> None:
    actual = subprocess.run(
        ["docker", "exec", container, "sha256sum", installed_path],
        text=True, capture_output=True, timeout=15, check=False,
    )
    if actual.returncode or actual.stdout.strip().split(" ", 1)[0] != digest:
        raise RuntimeError("running learner digest mismatch")


def process(path: Path) -> None:
    result = QUEUE / (path.name.removesuffix(".request.json") + ".result.json")
    try:
        if path.is_symlink():
            raise ValueError("invalid block build request")
        request = json.loads(path.read_text(encoding="utf-8"))
        problem = request.get("problem")
        digest = request.get("source_digest")
        if problem not in TARGETS or not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("unsupported block build request")
        mission, filename, container, installed_path = TARGETS[problem]
        if problem == "P20":
            files = {"P06-04_rules.yaml": PRACTICE / "P06-04_rules.yaml",
                     "P06-04_dashboard.json": PRACTICE / "P06-04_dashboard.json"}
            expected = request.get("file_digests")
            if not isinstance(expected, dict) or set(expected) != set(files):
                raise ValueError("P20 learner digests missing")
            if any(not source.is_file() or source.is_symlink() for source in files.values()):
                raise ValueError("learner file unavailable")
            data = {name: source.read_bytes() for name, source in files.items()}
            if any(hashlib.sha256(data[name]).hexdigest() != expected[name] for name in files):
                raise ValueError("learner file changed after submission")
            combined = data["P06-04_rules.yaml"] + P20_SEPARATOR + data["P06-04_dashboard.json"]
            if hashlib.sha256(combined).hexdigest() != digest:
                raise ValueError("P20 files changed after submission")
            completed = subprocess.run(
                [str(ROOT / "tools/apply-guided-practice.sh"), mission],
                cwd=ROOT, text=True, capture_output=True, timeout=240, check=False,
            )
            if completed.returncode:
                print(completed.stderr[-1200:], file=sys.stderr)
                raise RuntimeError("mission build failed; inspect guided block worker journal")
            for image, installed, name in (
                (container, "/app/rules.yaml", "P06-04_rules.yaml"),
                (container, "/app/dashboard.json", "P06-04_dashboard.json"),
                ("llm-security-guided-h20-prometheus", "/etc/prometheus/p20-rules.yml", "P06-04_rules.yaml"),
                ("llm-security-guided-h20-grafana", "/etc/grafana/p20/dashboard.json", "P06-04_dashboard.json"),
            ):
                require_container_digest(image, installed, expected[name])
            wait_healthy(container)
            write_result(result, {"state": "ready", "source_digest": digest})
            return
        source = PRACTICE / filename
        if not source.is_file() or source.is_symlink():
            raise ValueError("learner file unavailable")
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError("learner file changed after submission")
        completed = subprocess.run(
            [str(ROOT / "tools/apply-guided-practice.sh"), mission],
            cwd=ROOT, text=True, capture_output=True, timeout=240, check=False,
        )
        if completed.returncode:
            print(completed.stderr[-1200:], file=sys.stderr)
            raise RuntimeError("mission build failed; inspect guided block worker journal")
        require_container_digest(container, installed_path, digest)
        wait_healthy(container)
        if problem == "P22":
            # The learner edits the MCP server, but grading enters through its Host.
            wait_healthy("llm-security-guided-h22-host")
        write_result(result, {"state": "ready", "source_digest": digest})
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        write_result(result, {"state": "error", "message": str(exc)[:1200]})
    finally:
        path.unlink(missing_ok=True)


def main() -> None:
    for path in sorted(QUEUE.glob("*.request.json")):
        process(path)


if __name__ == "__main__":
    main()
