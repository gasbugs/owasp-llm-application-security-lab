#!/usr/bin/env bash
set -Eeuo pipefail

SETUP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$SETUP_ROOT/tools/guided-practice-files.tsv"
PRACTICE_ROOT="${GUIDED_PRACTICE_DIR:-$HOME/owasp-llm-practice}"

mkdir -p "$PRACTICE_ROOT"
while IFS='|' read -r display_id source_path workspace_name services; do
  [[ -n "$display_id" && "$display_id" != \#* ]] || continue
  workspace_file="$PRACTICE_ROOT/$workspace_name"
  git -C "$SETUP_ROOT" cat-file -e "HEAD:llm-security-control-plane/$source_path" || {
    printf '커밋된 Starter 파일이 없습니다: %s\n' "$source_path" >&2
    exit 1
  }
  if [[ ! -e "$workspace_file" ]]; then
    git -C "$SETUP_ROOT" show "HEAD:llm-security-control-plane/$source_path" > "$workspace_file"
    if [[ "$display_id" == P01-02 || "$display_id" == P01-03 || "$display_id" == P02-01 || "$display_id" == P03-01 || "$display_id" == P04-01 || "$display_id" == P04-02 || "$display_id" == P04-03 || "$display_id" == P04-04 || "$display_id" == P04-05 || "$display_id" == P04-06 || "$display_id" == P04-07 || "$display_id" == P04-08 || "$display_id" == P05-01 || "$display_id" == P05-02 || "$display_id" == P05-03 || "$display_id" == P05-04 || "$display_id" == P06-01 || "$display_id" == P06-02 || "$display_id" == P06-03 || "$display_id" == P06-04 || "$display_id" == P07-01 || "$display_id" == P07-02 ]]; then
      chmod 0664 "$workspace_file"
    fi
    printf 'Starter 복제: %s\n' "$workspace_file"
  fi
done < "$MANIFEST"

printf 'Practice 작업 폴더: %s\n' "$PRACTICE_ROOT"
