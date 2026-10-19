#!/usr/bin/env python3
"""Refresh a previously localized deployment, with a rollback on failed health."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from localization import install_ui

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--install-dir', default='/opt/sftpcn')
    parser.add_argument('--name', default='sftpcn')
    args = parser.parse_args()
    if sys.platform != 'linux' or os.geteuid() != 0:
        parser.error('请在 Ubuntu 上使用 sudo 执行')
    base = Path(args.install_dir)
    if not re.fullmatch(r'/opt/[a-zA-Z0-9_-]+', str(base)) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,50}', args.name):
        parser.error('目录或容器名不正确')
    ui = base / 'ui'
    if not ui.exists():
        ui = base / 'ui-zh'
    template = ui / 'templates/common/base.html'
    locale = ui / 'locales/zh/translation.json'
    if not template.is_file() or not locale.is_file():
        parser.error('未发现已适配的中文 UI，拒绝直接更新')
    config = json.loads((base / 'config/sftpgo.json').read_text())
    binding = config['httpd']['bindings'][0]
    address = binding['address']
    if address in ['', '0.0.0.0']:
        address = '127.0.0.1'
    backup = base / ('locale-backup-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S'))
    backup.mkdir(mode=0o700)
    shutil.copyfile(template, backup / 'base.html')
    shutil.copyfile(locale, backup / 'zh.json')
    source = Path(__file__).resolve().parents[1] / 'locale/zh.json'
    try:
        count = install_ui(ui, source)
        subprocess.run(['docker', 'restart', args.name], check=True)
        for _ in range(30):
            try:
                with urllib.request.urlopen(f'http://{address}:{binding["port"]}/healthz', timeout=2) as response:
                    assert response.status == 200
                break
            except (OSError, AssertionError):
                time.sleep(1)
        else:
            raise RuntimeError('更新后健康检查失败')
    except Exception:
        shutil.copyfile(backup / 'base.html', template)
        shutil.copyfile(backup / 'zh.json', locale)
        subprocess.run(['docker', 'restart', args.name], check=True)
        raise
    print(f'Chinese copy updated: {count} entries; backup: {backup}')
if __name__ == '__main__':
    main()
