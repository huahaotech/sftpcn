#!/usr/bin/env bash
set -Eeuo pipefail
# SFTPCN bootstrap. All application secrets are generated on the target machine.
if [[ ${EUID} -ne 0 ]]; then
  echo '请使用 sudo bash install.sh 安装。' >&2
  exit 1
fi
if [[ ! -f /etc/os-release ]] || ! grep -qE '^ID="?ubuntu"?$' /etc/os-release; then
  echo '当前安装器仅支持 Ubuntu。' >&2
  exit 1
fi
if ! command -v python3 >/dev/null || ! command -v curl >/dev/null; then
  apt-get update
  apt-get install -y python3 curl ca-certificates
fi
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$script_dir/deploy.py" && -f "$script_dir/locale/zh.json" ]]; then
  exec python3 "$script_dir/deploy.py" "$@"
fi
task_download_dir="$(mktemp -d -t sftpcn-install.XXXXXXXX)"
trap 'rm -rf -- "$task_download_dir"' EXIT
base_url='https://raw.githubusercontent.com/huahaotech/sftpcn/main'
mkdir -p "$task_download_dir/locale"
for file in deploy.py localization.py locale/zh.json sftpctl.py backup.py README.md LICENSE THIRD_PARTY_NOTICES.md; do
  curl --fail --show-error --silent --location --retry 3 --connect-timeout 15 --max-time 120 \
    "$base_url/$file" -o "$task_download_dir/$file"
done
python3 "$task_download_dir/deploy.py" "$@"
