#!/usr/bin/env python3
"""Local, fixed-scope reset of Tenant 03 learner work after ownership audit."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "llm-security-control-plane"
PROGRESS_VOLUME = "llm-security-guided-course_guided-control-progress"
CONTROL_IMAGE = "localhost/llm-security-guided-control-center:0.1.0"
PROGRESS_FILE = ROOT / ".state/guided-reset-progress.json"


def report_progress(percent, detail):
    temporary = PROGRESS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"percent": percent, "detail": detail}, ensure_ascii=False))
    os.replace(temporary, PROGRESS_FILE)


def run(*args, capture=False):
    return subprocess.run(args, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def compose(*args):
    return run(str(ROOT / "tools/guided-compose.sh"), *args)


def load_audit():
    path = ROOT / "tools/check-guided-reset-ownership.py"
    spec = importlib.util.spec_from_file_location("guided_reset_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = json.loads(run(sys.executable, str(path), capture=True))
    return module, report


def stop_checked_container(name):
    existing = subprocess.run(("docker", "container", "inspect", name),
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if existing.returncode == 0:
        run("docker", "stop", name)


def delete_mission_aws(progress=None):
    # The Gateway already owns account, resource names, idle-job checks and absence validation.
    caller = """import json,os,sys,urllib.request
problem,operation=sys.argv[1:]
key={'P02':'GUIDED_LAB02_PROVISION_TOKEN','P03':'GUIDED_LAB03_PROVISION_TOKEN','P04':'GUIDED_LAB04_PROVISION_TOKEN'}[problem]
body=json.dumps({'operation_id':operation}).encode()
request=urllib.request.Request('http://127.0.0.1:8080/v1/resource-lifecycle/'+problem+'/delete',
    data=body,headers={'Authorization':'Bearer '+os.environ[key],'Content-Type':'application/json'},method='POST')
with urllib.request.urlopen(request,timeout=480) as response:
    print(response.read().decode())
"""
    for problem in ('P02', 'P03', 'P04'):
        operation = str(uuid.uuid4())
        result = json.loads(run('docker', 'exec', 'llm-security-guided-bedrock-gateway',
                                'python', '-c', caller, problem, operation, capture=True))
        if result.get('practice_id') != problem or result.get('operation_id') != operation or result.get('state') != 'deleted':
            raise RuntimeError(f'{problem} AWS deletion response mismatch')
        if progress:
            progress(problem)


def delete_all_mission_aws(progress=None):
    _, report = load_audit()
    if any(report["aws_resources"].values()):
        delete_mission_aws(progress=progress)
    _, after = load_audit()
    if any(after["aws_resources"].values()):
        raise RuntimeError("Mission AWS resources remain after audited deletion")


def clear_all_progress():
    clear = ("import sqlite3,uuid; db=sqlite3.connect('/state/progress.sqlite3'); "
             "db.execute('DELETE FROM progress'); "
             "db.execute('DELETE FROM tutorial_completion'); "
             "db.execute(\"INSERT INTO installation_meta(key,value) VALUES('reset_generation',?) "
             "ON CONFLICT(key) DO UPDATE SET value=excluded.value\",(uuid.uuid4().hex,)); "
             "db.commit()")
    run("docker", "exec", "llm-security-guided-control-center", "python", "-c", clear)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args()
    audit, report = load_audit()
    if not args.execute:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    if args.confirm != "RESET TENANT 03":
        parser.error("--confirm 'RESET TENANT 03' is required")
    practice = importlib.util.spec_from_file_location(
        "guided_scope", ROOT / "tools/check-guided-reset-scope.py")
    scope = importlib.util.module_from_spec(practice)
    practice.loader.exec_module(scope)
    files = scope.practice_files()
    sources = {}
    for line in (ROOT / "tools/guided-practice-files.tsv").read_text().splitlines():
        if line and not line.startswith("#"):
            _mission, source, name, _services = line.split("|")
            sources[name] = source
    # Validate every Starter before changing cloud or learner resources.
    starters = {name: subprocess.check_output(["git", "-C", str(ROOT), "show",
                f"HEAD:llm-security-control-plane/{source}"])
                for name, source in sources.items()}
    report_progress(5, "초기화 대상과 Starter 원본을 확인했습니다.")
    if any(report["aws_resources"].values()):
        delete_all_mission_aws()
    report_progress(15, "AWS 실습 자원 정리를 확인했습니다.")
    report_progress(25, "풀이 코드를 초기 상태로 되돌릴 준비를 마쳤습니다.")
    services = report["mission_services"]
    # A pending block build must not reapply old learner code after reset.
    subprocess.run(("systemctl", "--user", "stop", "guided-block-build.path"), check=False)
    subprocess.run(("systemctl", "--user", "stop", "guided-block-build.service"), check=False)
    queue = ROOT / ".state/block-build-jobs"
    if queue.is_dir():
        for job in queue.iterdir():
            if job.is_file() and not job.is_symlink() and job.name.endswith((".request.json", ".result.json", ".tmp")):
                job.unlink()
    try:
        stop_checked_container("llm-security-guided-control-center")
        stop_checked_container("llm-security-guided-evidence-verifier")
        # A learner may create P00 after the ownership preview. Remove it
        # only after the server is stopped.
        p00_path = Path.home() / "work/control-center-tutorial/request.json"
        if p00_path.exists():
            if p00_path.is_symlink() or not p00_path.is_file():
                raise RuntimeError("P00 request path is not a regular file")
            p00_path.unlink()
        for container in report["mission_containers"]:
            run("docker", "rm", "-f", container)
        for volume in report["mission_volumes"]:
            run("docker", "volume", "rm", volume)
        report_progress(45, "미션 전용 Docker 자원을 정리했습니다.")
        for row in files:
            name = Path(row["path"])
            data = starters[name.name]
            temporary = name.with_name(name.name + ".reset-new")
            temporary.write_bytes(data)
            temporary.chmod(0o664 if name.name in {"P01-02_learner.py", "P01-03_learner.py", "P02-01_learner.py", "P03-01_learner.py", "P04-01_flows.co", "P04-02_actions.py", "P04-03_config.yml", "P04-04_prompts.yml", "P04-05_policy.py", "P04-06_prompts.yml", "P04-07_policy.py", "P04-08_pipeline.py", "P05-01_promptfooconfig.yaml", "P05-02_garak-config.yaml", "P05-03_attack.py", "P05-04_policy.py", "P06-01_instrumentation.py", "P06-02_queries.yaml", "P06-03_investigation.py", "P06-04_rules.yaml", "P06-04_dashboard.json", "P07-01_policy.py", "P07-02_server.py"} else 0o644)
            os.replace(temporary, name)
        report_progress(55, "풀이 코드를 Starter로 되돌렸습니다.")
        clear = ("import sqlite3,uuid; db=sqlite3.connect('/state/progress.sqlite3'); "
                 "db.execute('DELETE FROM progress'); "
                 "db.execute('DELETE FROM tutorial_completion'); "
                 "db.execute(\"INSERT INTO installation_meta(key,value) VALUES('reset_generation',?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value\",(uuid.uuid4().hex,)); "
                 "db.commit()")
        run("docker", "run", "--rm", "--network", "none", "--user", "0:0",
            "--entrypoint", "python", "-v", f"{PROGRESS_VOLUME}:/state:rw",
            CONTROL_IMAGE, "-c", clear)
        report_progress(65, "완료 기록을 초기화했습니다.")
        run("bash", str(ROOT / "tools/prepare-guided-practice-build.sh"))
        report_progress(75, "미션 실행 파일을 준비했습니다.")
        compose("build", *services)
        report_progress(85, "미션 이미지를 다시 만들었습니다.")
        compose("up", "-d", "--no-deps", "--force-recreate", *services)
        report_progress(90, "미션 서비스를 다시 시작했습니다.")
    finally:
        try:
            compose("up", "-d", "--no-deps", "guided-evidence-verifier", "guided-control-center")
        finally:
            subprocess.run(("systemctl", "--user", "start", "guided-block-build.path"), check=False)
    report_progress(95, "초기화 결과를 검증하고 있습니다.")
    print("Reset complete; verify zero progress, Starter digests, and service health.")


if __name__ == "__main__":
    main()
