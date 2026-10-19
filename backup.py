#!/usr/bin/env python3
"""Create a consistent offline backup; restart the container even after failure."""
from datetime import datetime, timezone
import os
import json
from pathlib import Path
import subprocess
import sys
import tarfile

BASE = Path(__file__).resolve().parent


def main():
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise SystemExit('请在 Ubuntu 上使用 sudo python3 /opt/sftpcn/backup.py')
    destination = Path('/var/backups/sftpcn')
    destination.mkdir(parents=True, mode=0o700, exist_ok=True)
    target = destination / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.tar.gz')
    if not BASE.is_dir() or BASE.is_symlink():
        raise SystemExit('部署目录不存在或是符号链接，拒绝备份')
    container = json.loads((BASE / 'deployment.json').read_text())['name']
    running = subprocess.check_output(['docker', 'inspect', '--format', '{{.State.Running}}', container], text=True).strip() == 'true'
    if running:
        subprocess.run(['docker', 'stop', '--time', '30', container], check=True)
    try:
        with target.open('xb') as handle:
            os.chmod(target, 0o600)
            with tarfile.open(fileobj=handle, mode='w:gz', dereference=False) as archive:
                archive.add(BASE, arcname=container)
    finally:
        if running:
            subprocess.run(['docker', 'start', container], check=True)
    print('备份完成（包含账号、文件、配置和 SSH 主机密钥）：' + str(target))


if __name__ == '__main__':
    main()
