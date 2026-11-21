#!/usr/bin/env bash
set -Eeuo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
state="$root/llm-security-control-plane/.state"
compose_root="$root/examples/security-monitoring"
options=(--env-file "$state/guided-course.env" --file "$compose_root/compose.guided.yaml")
if [[ -f "$state/guided-ec2/public-ip.env" ]]; then
  unset GUIDED_EC2_PUBLIC_IP
  options+=(--env-file "$state/guided-ec2/public-ip.env" --file "$compose_root/compose.guided-ec2.yaml")
fi
if [[ -f "$state/guided-practice-build.override.yaml" ]]; then
  options+=(--file "$state/guided-practice-build.override.yaml")
fi

exec docker compose "${options[@]}" "$@"
