#!/usr/bin/env bash
set -Eeuo pipefail

SETUP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTROL_ROOT="$SETUP_ROOT/llm-security-control-plane"
MANIFEST="$SETUP_ROOT/tools/guided-practice-files.tsv"
PRACTICE_ROOT="${GUIDED_PRACTICE_DIR:-$HOME/owasp-llm-practice}"
BUILD_ROOT="$SETUP_ROOT/.state/guided-practice-build"
OVERRIDE_FILE="$CONTROL_ROOT/.state/guided-practice-build.override.yaml"

# 빌드된 image의 non-root 사용자가 추적 중인 source를 읽을 수 있어야 합니다.
umask 022
rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT" "$(dirname "$OVERRIDE_FILE")"
git -C "$SETUP_ROOT" archive HEAD llm-security-control-plane |
  tar -x --strip-components=1 -C "$BUILD_ROOT"

# P01-01의 블록 제출 API와 Starter는 현재 제공 서버·Containerfile을 사용합니다.
# 학습자 learner.py만 아래 manifest에서 교체합니다.
for provided in Containerfile server.py learner-starter.py; do
  install -D -m 0644 \
    "$CONTROL_ROOT/guided-labs/h23-model-call/$provided" \
    "$BUILD_ROOT/guided-labs/h23-model-call/$provided"
done

# P04-06 제공 실행기와 Main 출력 상한을 현재 정본에서 빌드합니다.
for provided in server.py config/config.yml; do
  install -D -m 0644 \
    "$CONTROL_ROOT/guided-labs/h10-self-check-output/$provided" \
    "$BUILD_ROOT/guided-labs/h10-self-check-output/$provided"
done

# P05-04의 현재 제공 서버는 여섯 회귀 사례를 실행합니다.
# 학습자 정책만 교체하더라도 이 서버 계약이 이전 Git image로 되돌아가지 않게 합니다.
install -D -m 0644 \
  "$CONTROL_ROOT/guided-labs/h16-policy-promotion/server.py" \
  "$BUILD_ROOT/guided-labs/h16-policy-promotion/server.py"

# P06-03의 손상 사본 검사기는 현재 제공 실행기와 검증기에 같은 원문을 사용합니다.
install -D -m 0644 \
  "$CONTROL_ROOT/guided-labs/h19-incident-investigation/analysis_inputs.py" \
  "$BUILD_ROOT/guided-labs/h19-incident-investigation/analysis_inputs.py"

# P07-02의 제공 Host는 서버 직접 자기 승인 검사를 포함합니다.
# 학습자 Server만 교체할 때 이전 Git image의 Host가 다시 배포되지 않게 합니다.
install -D -m 0644 \
  "$CONTROL_ROOT/guided-labs/h22-mcp-approval/host.py" \
  "$BUILD_ROOT/guided-labs/h22-mcp-approval/host.py"

services=()
while IFS='|' read -r display_id source_path workspace_name service_list; do
  [[ -n "$display_id" && "$display_id" != \#* ]] || continue
  workspace_file="$PRACTICE_ROOT/$workspace_name"
  [[ -f "$workspace_file" ]] || { printf '작업 파일이 없습니다: %s\n' "$workspace_file" >&2; exit 1; }
  install -D -m 0644 "$workspace_file" "$BUILD_ROOT/$source_path"
  IFS=',' read -ra row_services <<< "$service_list"
  services+=("${row_services[@]}")
done < "$MANIFEST"

{
  printf 'services:\n'
  printf '%s\n' "${services[@]}" | sort -u | while IFS= read -r service; do
    printf '  %s:\n    build:\n      context: %s\n' "$service" "$BUILD_ROOT"
  done
} > "$OVERRIDE_FILE"

printf '%s\n' "$OVERRIDE_FILE"
