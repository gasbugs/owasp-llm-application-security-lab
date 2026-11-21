#!/usr/bin/env bash
set -Eeuo pipefail

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(mktemp -d "/tmp/ldl-ec2-check.XXXXXXXX")"
test_name=""
cleanup() {
  if [[ -n "$test_name" ]]; then
    docker rm -f "$test_name" >/dev/null 2>&1 || true
  fi
  rm -rf -- "$scratch"
}
trap cleanup EXIT
cd "$scratch"
mkdir -p examples/security-monitoring llm-security-control-plane/guided-front-proxy tools
cp "$source_root"/examples/security-monitoring/compose.guided*.yaml examples/security-monitoring/
cp "$source_root"/llm-security-control-plane/guided-front-proxy/{nginx.conf,ec2-viewers.conf} llm-security-control-plane/guided-front-proxy/
cp "$source_root"/tools/{guided-compose.sh,guided_ec2_config.py,install-guided-practice.sh,apply-guided-practice.sh,reset-guided-practice.py} tools/

for shell_file in tools/install-guided-practice.sh tools/guided-compose.sh tools/apply-guided-practice.sh; do
  bash -n "$shell_file"
done
python3 -m py_compile tools/guided_ec2_config.py tools/reset-guided-practice.py
new_ip_dir=llm-security-control-plane/.state/guided-ec2
mkdir -p llm-security-control-plane/.state
grep -oE '\$\{[A-Z][A-Z0-9_]+:\?' examples/security-monitoring/compose.guided.yaml |
  sed -E 's/^\$\{([^:]+):\?$/\1=isolated-test-value/' | sort -u > llm-security-control-plane/.state/guided-course.env
docker compose version
base_config=$(mktemp "$scratch/render.XXXXXXXX")
before_config=$(mktemp "$scratch/render.XXXXXXXX")
after_config=$(mktemp "$scratch/render.XXXXXXXX")

tools/guided-compose.sh config --format json > "$base_config"
for ip in 198.51.100.10 198.51.100.20; do
  python3 - "$new_ip_dir" "$ip" <<'PY'
from ipaddress import IPv4Address
from pathlib import Path
import sys
from tools.guided_ec2_config import write_config
write_config(Path(sys.argv[1]), IPv4Address(sys.argv[2]))
PY
  if [[ "$ip" == 198.51.100.10 ]]; then
    tools/guided-compose.sh config --format json > "$before_config"
  else
    tools/guided-compose.sh config --format json > "$after_config"
  fi
done
python3 - "$base_config" "$before_config" "$after_config" <<'PY'
import json, sys

def load(path):
    with open(path) as f:
        return json.load(f)

def public_services(cfg):
    return {int(p["published"]): (name, p["target"])
            for name, service in cfg["services"].items() for p in service.get("ports", [])
            if p.get("host_ip") != "127.0.0.1"}

base, old, new = map(load, sys.argv[1:])
assert public_services(base) == {}
expected = {
    9010: ("guided-front-proxy", 18097),
    9011: ("guided-front-proxy", 18192),
    9012: ("guided-grafana", 3000),
    9013: ("guided-h20-grafana", 3000),
    9014: ("guided-front-proxy", 19014),
    9015: ("guided-front-proxy", 19015),
}
assert public_services(old) == public_services(new) == expected
for cfg, ip in ((old, "198.51.100.10"), (new, "198.51.100.20")):
    svc = cfg["services"]
    center = svc["guided-control-center"]["environment"]
    assert f"{ip}:9010" in center["GUIDED_ALLOWED_HOSTS"]
    assert f"http://{ip}:9010" in center["GUIDED_ALLOWED_ORIGINS"]
    assert {value for name, value in center.items() if name.endswith("_BROWSER_URL")} == {
        f"http://{ip}:9011/", f"http://{ip}:9012/explore", f"http://{ip}:9013/d/guided-p20",
        f"http://{ip}:9014/", f"http://{ip}:9015/",
    }
    assert svc["guided-front-proxy"]["environment"]["GUIDED_EC2_PUBLIC_IP"] == ip
    assert svc["guided-model-call"]["environment"]["AWS_DEFAULT_REGION"] == "us-east-1"
    for service in ("guided-model-call", "guided-h01-gateway", "guided-bedrock-gateway"):
        env = svc[service]["environment"]
        assert env["AWS_EC2_METADATA_DISABLED"] == "false"
        removed = {"AWS_PROFILE", "AWS_SHARED_CREDENTIALS_FILE", "AWS_CONFIG_FILE"}
        assert not (removed & env.keys()), (service, {k: env[k] for k in removed & env.keys()})
        aws_mount = [v for v in svc[service]["volumes"] if v["target"] == "/tmp/.aws"]
        assert len(aws_mount) == 1 and aws_mount[0]["type"] == "volume" and aws_mount[0]["read_only"]
        assert all(v in svc[service]["volumes"] for v in base["services"][service]["volumes"] if v["target"] != "/tmp/.aws")
    assert len({svc[name]["environment"]["GF_AUTH_LOGIN_COOKIE_NAME"]
                for name in ("guided-grafana", "guided-h20-grafana")}) == 2
print("WSL loopback, EC2 ports and IP rotation, Grafana cookies, role isolation, and learner mounts PASS")
PY
root="$PWD/llm-security-control-plane"
image=docker.io/nginxinc/nginx-unprivileged:1.29.1-alpine
docker run --rm --entrypoint nginx --tmpfs /tmp --tmpfs /var/cache/nginx:uid=101,gid=101,mode=0700 \
  --mount "type=bind,src=$root/guided-front-proxy/nginx.conf,dst=/etc/nginx/nginx.conf,readonly" \
  "$image" -t
docker run --rm --entrypoint nginx --tmpfs /tmp --tmpfs /var/cache/nginx:uid=101,gid=101,mode=0700 \
  --mount "type=bind,src=$root/guided-front-proxy/nginx.conf,dst=/etc/nginx/nginx.conf,readonly" \
  --mount "type=bind,src=$root/.state/guided-ec2/hosts,dst=/etc/nginx/guided-ec2/hosts,readonly" \
  --mount "type=bind,src=$root/guided-front-proxy/ec2-viewers.conf,dst=/etc/nginx/guided-ec2/servers/viewers.conf,readonly" \
  "$image" -t


test_name="ldl-ec2-port-check-$$"
docker run -d --name "$test_name" --entrypoint nginx --read-only --tmpfs /tmp \
  --tmpfs /var/cache/nginx:uid=101,gid=101,mode=0700 \
  -p 127.0.0.1::18097 -p 127.0.0.1::19014 -p 127.0.0.1::19015 \
  --mount "type=bind,src=$root/guided-front-proxy/nginx.conf,dst=/etc/nginx/nginx.conf,readonly" \
  --mount "type=bind,src=$root/.state/guided-ec2/hosts,dst=/etc/nginx/guided-ec2/hosts,readonly" \
  --mount "type=bind,src=$root/guided-front-proxy/ec2-viewers.conf,dst=/etc/nginx/guided-ec2/servers/viewers.conf,readonly" \
  "$image" -g 'daemon off;' >/dev/null
home_url="http://$(docker port "$test_name" 18097/tcp)"
curl -fsS --retry 5 --retry-connrefused -H 'Host: 198.51.100.20:9010' "$home_url/proxy-healthz" | grep -q front-proxy-ready
[[ $(curl -sS -o /dev/null -w '%{http_code}' -H 'Host: 198.51.100.10:9010' "$home_url/proxy-healthz") == 421 ]]
for port in 19014 19015; do
  url="http://$(docker port "$test_name" "$port/tcp")"
  [[ $(curl -sS -X POST -o /dev/null -w '%{http_code}' -H 'Host: 198.51.100.20' "$url/") == 403 ]]
done
echo 'Nginx accepts the updated IP, rejects the old IP and blocks writes to viewer ports'

# Exercise both installer commands with a fixture for AWS metadata and role identity.
# Stub only process startup before the install can register user-level systemd units.
mkdir -p "$scratch/bin"
export LDL_CHECK_ROOT="$scratch"
export LDL_CHECK_PYTHON="$(command -v python3)"
export LDL_CHECK_DOCKER="$(command -v docker)"
cat > "$scratch/bin/aws" <<'MOCK_AWS'
#!/usr/bin/env bash
set -eu
[[ "$*" == 'sts get-caller-identity --region us-east-1 --query Arn --output text' ]]
[[ "${AWS_CONFIG_FILE:-}" == /dev/null && "${AWS_SHARED_CREDENTIALS_FILE:-}" == /dev/null ]]
[[ "${AWS_EC2_METADATA_DISABLED:-}" == false && -z "${AWS_PROFILE:-}" && -z "${AWS_ACCESS_KEY_ID:-}" ]]
echo 'arn:aws:sts::111111111111:assumed-role/ldl-check/instance'
MOCK_AWS
cat > "$scratch/bin/python3" <<'MOCK_METADATA'
#!/usr/bin/env bash
set -eu
if [[ "${1:-}" == */tools/guided_ec2_config.py ]]; then
  exec "$LDL_CHECK_PYTHON" -c '
import os, sys
from ipaddress import IPv4Address
from unittest.mock import patch
sys.path.insert(0, os.environ["LDL_CHECK_ROOT"])
from tools import guided_ec2_config
with patch("tools.guided_ec2_config.public_ipv4", return_value=IPv4Address(os.environ["LDL_CHECK_IP"])):
    sys.argv = sys.argv[1:]
    raise SystemExit(guided_ec2_config.main())
' "$@"
fi
exec "$LDL_CHECK_PYTHON" "$@"
MOCK_METADATA
cat > "$scratch/bin/docker" <<'MOCK_DOCKER'
#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >> "$LDL_CHECK_ROOT/docker.log"
case " $* " in
  *' info '*) printf '{"MemTotal":1073741824}\n' ;;
  *' ps '*) exit 0 ;;
  *' start '*) exit 0 ;;
  *' up '*' --no-build '*) exit 0 ;;
  *' up '*) exit 86 ;;
  *) exec "$LDL_CHECK_DOCKER" "$@" ;;
esac
MOCK_DOCKER
for helper in initialize-guided-practice prepare-guided-practice-build; do
  printf '#!/usr/bin/env bash\nexit 0\n' > "tools/$helper.sh"
  chmod +x "tools/$helper.sh"
done
cp "$source_root/tools/practice_preflight.py" "$source_root/tools/check_guided_isolation.py" tools/
mkdir -p tools/systemd
cp "$source_root/tools/systemd/guided-ec2-resume.service" tools/systemd/
cat > "$scratch/bin/systemctl" <<'MOCK_SYSTEMD'
#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >> "$LDL_CHECK_ROOT/systemd.log"
case "$*" in
  '--user show-environment'|'--user daemon-reload'|'--user enable guided-ec2-resume.service') ;;
  *) exit 2 ;;
esac
MOCK_SYSTEMD
cat > "$scratch/bin/loginctl" <<'MOCK_LOGINCTL'
#!/usr/bin/env bash
set -eu
[[ "$1" == show-user && "$3" == --property=Linger && "$4" == --value ]]
printf 'yes\n'
MOCK_LOGINCTL
chmod +x "$scratch/bin/"*
rm -f -- "$new_ip_dir/public-ip.env" llm-security-control-plane/.state/guided-course.env
status=0
PATH="$scratch/bin:$PATH" LDL_CHECK_IP=198.51.100.10 AWS_PROFILE=obsolete AWS_ACCESS_KEY_ID=fake \
  bash tools/install-guided-practice.sh --ec2 > "$scratch/install.log" || status=$?
if [[ "$status" != 86 ]]; then
  cat "$scratch/install.log"
  printf 'Expected install to reach Docker startup before stopping, got %s\n' "$status" >&2
  exit 1
fi
grep -E 'compose .*compose.guided-ec2.yaml up -d --build' "$scratch/docker.log" >/dev/null
grep -Fx 'GUIDED_EC2_PUBLIC_IP=198.51.100.10' "$new_ip_dir/public-ip.env" >/dev/null
cp llm-security-control-plane/.state/guided-course.env "$scratch/course-env-before"
PATH="$scratch/bin:$PATH" XDG_CONFIG_HOME="$scratch/config" LDL_CHECK_IP=198.51.100.20 \
  bash tools/install-guided-practice.sh --ec2 --resume > "$scratch/resume.log"
grep -E 'compose .*compose.guided-ec2.yaml start$' "$scratch/docker.log" >/dev/null
grep -E 'compose .*up -d --no-deps --no-build .*guided-control-center guided-front-proxy$' "$scratch/docker.log" >/dev/null
grep -Fx 'GUIDED_EC2_PUBLIC_IP=198.51.100.20' "$new_ip_dir/public-ip.env" >/dev/null
grep -Fx '198.51.100.20 1;' "$new_ip_dir/hosts/public-ip.conf" >/dev/null
grep -Fx 'LDL 홈: http://198.51.100.20:9010/' "$scratch/resume.log" >/dev/null
cmp llm-security-control-plane/.state/guided-course.env "$scratch/course-env-before"
echo 'Installer and resume: IAM role fixture, updated address and preserved course credentials PASS'

unit=guided-ec2-resume.service
cmp "tools/systemd/$unit" "$scratch/config/systemd/user/$unit"
grep -Fx -- '--user enable guided-ec2-resume.service' "$scratch/systemd.log" >/dev/null
grep -Fx 'WantedBy=default.target' "tools/systemd/$unit" >/dev/null
grep -Fx 'Environment=GUIDED_EC2_BOOT=1' "tools/systemd/$unit" >/dev/null
grep -Fx 'Restart=on-failure' "tools/systemd/$unit" >/dev/null
cp "$scratch/systemd.log" "$scratch/systemd-before.log"
PATH="$scratch/bin:$PATH" GUIDED_EC2_BOOT=1 LDL_CHECK_IP=198.51.100.30 \
  bash tools/install-guided-practice.sh --ec2 --resume > "$scratch/boot.log"
cmp "$scratch/systemd.log" "$scratch/systemd-before.log"
grep -Fx 'GUIDED_EC2_PUBLIC_IP=198.51.100.30' "$new_ip_dir/public-ip.env" >/dev/null
grep -Fx '198.51.100.30 1;' "$new_ip_dir/hosts/public-ip.conf" >/dev/null
echo 'Autostart enrollment and unattended boot mode PASS'
