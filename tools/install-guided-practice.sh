#!/usr/bin/env bash
set -Eeuo pipefail

SETUP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$SETUP_ROOT/examples/security-monitoring/compose.guided.yaml"
STATE_DIR="$SETUP_ROOT/llm-security-control-plane/.state"
ENV_FILE="$STATE_DIR/guided-course.env"

log() { printf '\n[%s] %s\n' "$1" "$2"; }
fail() { printf '\n[오류] %s\n' "$1" >&2; exit 1; }

ec2=false
resume=false
while (( $# )); do
  case "$1" in
    --ec2) ec2=true ;;
    --resume) resume=true ;;
    *) fail "사용법: $0 [--ec2 [--resume]]" ;;
  esac
  shift
done

EC2_STATE="$STATE_DIR/guided-ec2"
EC2_COMPOSE="$SETUP_ROOT/examples/security-monitoring/compose.guided-ec2.yaml"
guided_compose="$SETUP_ROOT/tools/guided-compose.sh"
if [[ "$resume" == true && ( "$ec2" == false || ! -f "$ENV_FILE" || ! -f "$EC2_STATE/public-ip.env" ) ]]; then
  fail "EC2에서 처음 한 번 --ec2로 설치한 뒤 --ec2 --resume을 사용하세요."
fi
if [[ "$ec2" == false && -f "$EC2_STATE/public-ip.env" ]]; then
  fail "이 실습실은 EC2용으로 설치되어 있습니다. --ec2를 사용하세요."
fi

enable_ec2_autostart() {
  [[ "${GUIDED_EC2_BOOT:-0}" != 1 ]] || return 0
  systemctl --user show-environment >/dev/null 2>&1 ||
    fail "LDL 자동 시작을 등록하려면 Ubuntu 사용자 systemd 세션이 필요합니다."
  if [[ "$(loginctl show-user "$(id -un)" --property=Linger --value)" != yes ]]; then
    sudo loginctl enable-linger "$(id -un)"
  fi
  local unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  install -d -m 0700 "$unit_dir"
  install -m 0644 "$SETUP_ROOT/tools/systemd/guided-ec2-resume.service" "$unit_dir/"
  systemctl --user daemon-reload
  systemctl --user enable guided-ec2-resume.service
  printf 'EC2 재시작 시 LDL 자동 시작을 등록했습니다.\n'
}

log "1/5" "필수 프로그램과 AWS 자격 증명을 확인합니다."
for command_name in docker aws openssl python3 grep sort git tar; do
  command -v "$command_name" >/dev/null 2>&1 ||
    fail "$command_name 명령을 찾지 못했습니다. 01 테넌트 환경 준비를 먼저 완료하세요."
done
docker info >/dev/null 2>&1 ||
  fail "Docker daemon에 접근할 수 없습니다. Docker 실행 상태와 docker 그룹 권한을 확인하세요."
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2를 사용할 수 없습니다."
if [[ "$ec2" == true ]]; then
  env -u AWS_PROFILE -u AWS_DEFAULT_PROFILE -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY \
    -u AWS_SESSION_TOKEN -u AWS_SECURITY_TOKEN -u AWS_WEB_IDENTITY_TOKEN_FILE -u AWS_ROLE_ARN \
    -u AWS_CONTAINER_CREDENTIALS_FULL_URI -u AWS_CONTAINER_CREDENTIALS_RELATIVE_URI \
    AWS_CONFIG_FILE=/dev/null AWS_SHARED_CREDENTIALS_FILE=/dev/null AWS_EC2_METADATA_DISABLED=false \
    aws sts get-caller-identity --region us-east-1 --query Arn --output text | grep -q ':assumed-role/' ||
    fail "EC2 IAM 역할을 확인하지 못했습니다."
else
  aws sts get-caller-identity --profile default --output json >/dev/null 2>&1 ||
    fail "AWS default 프로필로 현재 계정을 확인하지 못했습니다."
fi
[[ -f "$COMPOSE_FILE" ]] || fail "Compose 파일을 찾지 못했습니다: $COMPOSE_FILE"

if [[ "$resume" == true ]]; then
  public_ip="$(python3 "$SETUP_ROOT/tools/guided_ec2_config.py" "$EC2_STATE")"
  "$guided_compose" start
  "$guided_compose" up -d --no-deps --no-build --wait --wait-timeout 180 guided-control-center guided-front-proxy
  enable_ec2_autostart
  printf '\nLDL 홈: http://%s:9010/\n' "$public_ip"
  exit 0
fi

installed=false
if [[ -f "$ENV_FILE" ]]; then installed=true; fi
if docker compose --file "$COMPOSE_FILE" ps -q 2>/dev/null | grep -q .; then
  installed=true
fi
if [[ "$installed" == true ]]; then
  printf '\n기존 실습 플랫폼이 발견되었습니다. 기존 Token과 volume을 보존한 채 다시 Build·설치할까요? [y/N] '
  read -r answer
  [[ "$answer" == "y" || "$answer" == "Y" ]] || {
    printf '설치를 취소했습니다. 기존 플랫폼은 변경하지 않았습니다.\n'
    exit 0
  }
fi

preflight_files=(--file "$COMPOSE_FILE")
if [[ "$ec2" == true ]]; then
  public_ip="$(python3 "$SETUP_ROOT/tools/guided_ec2_config.py" "$EC2_STATE")"
  export GUIDED_EC2_PUBLIC_IP="$public_ip"
  preflight_files+=(--file "$EC2_COMPOSE")
fi

log "2/5" "서비스 Token 환경 파일을 준비합니다."
mkdir -p "$STATE_DIR/guided-gateway"
if [[ ! -f "$ENV_FILE" ]]; then
  umask 077
  {
    if [[ "$ec2" == false ]]; then
      printf 'AWS_PROFILE=default\n'
    elif [[ -n "${GUIDED_LDL_LEARNER_ROLE_ARN:-}" ]]; then
      printf 'GUIDED_LDL_LEARNER_ROLE_ARN=%s\n' "$GUIDED_LDL_LEARNER_ROLE_ARN"
    fi
    printf 'LOCAL_UID=%s\n' "$(id -u)"
    printf 'LOCAL_GID=%s\n' "$(id -g)"
    printf 'GUIDED_PROVIDER_MODE=aws\n'
    grep -oE '\$\{[A-Z][A-Z0-9_]+:\?' "$COMPOSE_FILE" |
      sed -E 's/^\$\{([^:]+):\?$/\1/' |
      sort -u |
      while IFS= read -r variable_name; do
        if [[ "$variable_name" == *PASSWORD ]]; then
          printf '%s=%s\n' "$variable_name" "$(openssl rand -hex 18)"
        else
          printf '%s=%s\n' "$variable_name" "$(openssl rand -hex 32)"
        fi
      done
  } > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  printf '새 환경 파일을 만들었습니다: %s\n' "$ENV_FILE"
else
  printf '기존 환경 파일을 재사용합니다: %s\n' "$ENV_FILE"
fi

# Compose에 새 필수값이 추가되어도 기존 Token과 volume은 보존하고 누락값만 채웁니다.
mapfile -t required_variables < <(
  grep -oE '\$\{[A-Z][A-Z0-9_]+:\?' "$COMPOSE_FILE" |
    sed -E 's/^\$\{([^:]+):\?$/\1/' |
    sort -u
)
for variable_name in "${required_variables[@]}"; do
  if ! grep -qE "^${variable_name}=" "$ENV_FILE"; then
    printf '%s=%s\n' "$variable_name" "$(openssl rand -hex 32)" >> "$ENV_FILE"
    printf '기존 환경 파일에 새 필수값을 추가했습니다: %s\n' "$variable_name"
  fi
done
chmod 600 "$ENV_FILE"

log "3/5" "Practice Starter를 사용자 작업 폴더에 복제하고 실행 환경을 점검합니다."
"$SETUP_ROOT/tools/initialize-guided-practice.sh"
"$SETUP_ROOT/tools/prepare-guided-practice-build.sh" >/dev/null
install -d -m 2770 "$SETUP_ROOT/.state/block-build-jobs"
python3 "$SETUP_ROOT/tools/practice_preflight.py" \
  --root "$SETUP_ROOT" --env-file "$ENV_FILE" "${preflight_files[@]}"

log "4/5" "실습 이미지를 Build하고 최신 이미지로 공통 플랫폼을 다시 생성합니다."
"$guided_compose" up -d --build --force-recreate --remove-orphans

log "5/5" "설치 결과를 확인합니다."
"$guided_compose" ps --all

stale_services=()
while IFS= read -r container_id; do
  configured_image="$(docker inspect --format '{{.Config.Image}}' "$container_id")"
  running_image="$(docker inspect --format '{{.Image}}' "$container_id")"
  current_image="$(docker image inspect --format '{{.Id}}' "$configured_image")"
  if [[ "$running_image" != "$current_image" ]]; then
    stale_services+=("$(docker inspect --format '{{index .Config.Labels \"com.docker.compose.service\"}}' "$container_id")")
  fi
done < <("$guided_compose" ps -q)

if (( ${#stale_services[@]} > 0 )); then
  fail "최신 로컬 이미지를 사용하지 않는 서비스가 남았습니다: ${stale_services[*]}"
fi

# 블록 제출은 Docker socket을 UI에 노출하지 않고 WSL 사용자 서비스가 적용합니다.
if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  install -d -m 0700 "$HOME/.config/systemd/user"
  install -m 0644 "$SETUP_ROOT/tools/systemd/guided-block-build.service" "$HOME/.config/systemd/user/guided-block-build.service"
  install -m 0644 "$SETUP_ROOT/tools/systemd/guided-block-build.path" "$HOME/.config/systemd/user/guided-block-build.path"
  systemctl --user daemon-reload
  systemctl --user enable --now guided-block-build.path
  systemctl --user link "$SETUP_ROOT/tools/guided-reset-bridge.service"
  systemctl --user enable --now guided-reset-bridge.service
else
  fail "블록 제출 뒤 자동 빌드에는 Ubuntu systemd 사용자 서비스가 필요합니다."
fi

printf '\n설치가 완료되었습니다.\n'
if [[ "$ec2" == true ]]; then
  enable_ec2_autostart
  printf 'LDL 홈: http://%s:9010/\n' "$public_ip"
  printf 'NeMo Chat UI: http://%s:9011/\n' "$public_ip"
  printf 'Grafana Explore: http://%s:9012/explore\n' "$public_ip"
  printf 'P20 Grafana: http://%s:9013/d/guided-p20\n' "$public_ip"
  printf 'Promptfoo Viewer: http://%s:9014/\n' "$public_ip"
  printf 'PyRIT Frontend: http://%s:9015/\n' "$public_ip"
else
  printf 'Control Center: http://127.0.0.1:28097\n'
  printf '관리자 답안:   http://127.0.0.1:28097/?mode=admin\n'
  printf 'NeMo Chat UI:  http://127.0.0.1:28192\n'
  printf 'P20 Grafana:    http://127.0.0.1:23002/d/guided-p20\n'
fi
printf 'Grafana 비밀번호 확인: grep -E '\''^(GUIDED_GRAFANA_PASSWORD|GUIDED_P20_GRAFANA_PASSWORD)='\'' %s\n' "$ENV_FILE"
