#!/usr/bin/env python3
"""SFTPCN: Ubuntu installer with a version-matched Chinese UI."""
import argparse
import datetime
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from localization import install_ui

VERSION = '0.1.0'
SFTPGO_VERSION = '2.7.6'
IMAGE = 'drakkan/sftpgo:v' + SFTPGO_VERSION

def configure_firewall(sftp_port, web_port, web_bind, skip=False):
    """Only add rules to active UFW; never enable or reset it."""
    if skip:
        print('已按 --skip-firewall 跳过系统防火墙设置。')
        return
    ufw = shutil.which('ufw')
    if not ufw:
        print('未检测到 UFW，未修改系统防火墙；如使用其他防火墙，请自行放行服务端口。')
        return
    env = dict(os.environ, LC_ALL='C', LANG='C')
    try:
        result = subprocess.run([ufw, 'status'], check=True, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=env, timeout=15)
        if not re.search(r'^Status:\s*active\s*$', result.stdout, re.M):
            print('UFW 未启用，保持现状，不自动启用或改写已有规则。')
            return
        ports = [sftp_port]
        if not ipaddress.ip_address(web_bind).is_loopback:
            ports.append(web_port)
        for port in dict.fromkeys(ports):
            subprocess.run([ufw, 'allow', f'{port}/tcp'], check=True, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env=env, timeout=15)
            print(f'UFW 已放行 TCP {port}。')
    except (OSError, subprocess.SubprocessError) as exc:
        print(f'自动配置 UFW 未完成（{type(exc).__name__}）。服务已安装，请手动检查防火墙规则。', file=sys.stderr)

def run(*args, capture=False, timeout=None):
    return subprocess.run(args, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None, timeout=timeout).stdout

def obtain_image():
    existing = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', IMAGE],
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if existing.returncode == 0:
        print('使用本地已存在的固定版本镜像：' + IMAGE, flush=True)
        return IMAGE, existing.stdout.strip()
    for reference in [IMAGE, 'ghcr.io/drakkan/sftpgo:v' + SFTPGO_VERSION]:
        try:
            run('docker', 'pull', reference, timeout=120)
            return reference, run('docker', 'image', 'inspect', '--format', '{{.Id}}', reference, capture=True).strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            print('暂时无法访问镜像仓库：' + reference, flush=True)
    raise RuntimeError('两个官方仓库均无法连接。请先按 README 导入可信的官方镜像，再重新安装。')

def config(sftp_port, web_port, bind, code):
    return {
        'common': {'defender': {'enabled': True}, 'symlink_mode': 0},
        'sftpd': {'bindings': [{'address': '0.0.0.0', 'port': sftp_port, 'apply_proxy_config': False}],
                  'host_keys': ['/var/lib/sftpgo/id_ed25519'], 'enabled_ssh_commands': [],
                  'keyboard_interactive_authentication': False, 'password_authentication': True},
        'ftpd': {'bindings': [{'port': 0}]}, 'webdavd': {'bindings': [{'port': 0}]},
        'data_provider': {'driver': 'sqlite', 'name': '/var/lib/sftpgo/sftpgo.db',
                          'users_base_dir': '/srv/sftpgo/data', 'backups_path': '/srv/sftpgo/backups'},
        'httpd': {'bindings': [{'address': bind, 'port': web_port, 'enable_web_admin': True,
                               'enable_web_client': False, 'enable_rest_api': True,
                               'render_openapi': False, 'languages': ['zh', 'en']}],
                  'templates_path': '/usr/share/sftpgo/templates',
                  'static_files_path': '/usr/share/sftpgo/static',
                  'openapi_path': '/usr/share/sftpgo/openapi',
                  'setup': {'installation_code': code, 'installation_code_hint': '安装结束时显示的初始化代码'}},
        'telemetry': {'bind_port': 0}}

def docker_args(base, image_id, name):
    base = Path(base)
    args = ['docker', 'run', '-d', '--name', name, '--label', 'io.sftpcn.managed=true',
            '--restart', 'unless-stopped', '--network', 'host', '--user', '1000:1000',
            '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
            '--pids-limit', '256', '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
            '--log-opt', 'max-size=10m', '--log-opt', 'max-file=5']
    mounts = [('config/sftpgo.json', '/etc/sftpgo/sftpgo.json', True),
              ('data', '/srv/sftpgo', False), ('state', '/var/lib/sftpgo', False),
              ('ui/templates', '/usr/share/sftpgo/templates', True),
              ('ui/locales', '/usr/share/sftpgo/static/locales', True)]
    for src, dst, readonly in mounts:
        args += ['--mount', f'type=bind,src={base / src},dst={dst}' + (',readonly' if readonly else '')]
    return args + ['-e', 'SFTPGO_LOG_FILE_PATH=', image_id, 'sftpgo', 'serve', '--config-dir', '/etc/sftpgo', '--log-level', 'info']

def free_port(bind, port):
    with socket.socket() as s:
        s.bind((bind, port))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sftp-port', type=int, default=2022)
    p.add_argument('--web-port', type=int, default=8080)
    p.add_argument('--web-bind', default='0.0.0.0', help='默认支持 IP:端口直连；可设 127.0.0.1')
    p.add_argument('--install-dir', default='/opt/sftpcn')
    p.add_argument('--name', default='sftpcn')
    p.add_argument('--print-config', action='store_true')
    p.add_argument('--skip-firewall', action='store_true', help='跳过自动放行 UFW 端口')
    args = p.parse_args()
    if any(not 1024 <= v <= 65535 for v in [args.sftp_port, args.web_port]):
        p.error('端口须在 1024–65535 之间；保留原有 SSH 22 端口')
    if args.sftp_port == args.web_port:
        p.error('后台和 SFTP 不能使用同一端口')
    try:
        ipaddress.IPv4Address(args.web_bind)
    except ValueError:
        p.error('--web-bind 必须是 IPv4 地址')
    base = Path(args.install_dir)
    if not re.fullmatch(r'/opt/[a-zA-Z0-9_-]+', str(base)):
        p.error('安装目录必须是 /opt 下的独立目录，例如 /opt/sftpcn')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,50}', args.name):
        p.error('容器名称格式不正确')
    if args.print_config:
        print(json.dumps(config(args.sftp_port, args.web_port, args.web_bind, '生成于安装时'), ensure_ascii=False, indent=2))
        return
    if sys.platform != 'linux' or os.geteuid() != 0:
        p.error('请在 Ubuntu 上使用 sudo bash install.sh')
    release = Path('/etc/os-release').read_text()
    if not re.search(r'^ID="?ubuntu"?$', release, re.M):
        p.error('当前安装器仅支持 Ubuntu')
    if base.exists():
        p.error('安装目录已存在，为保护数据，拒绝覆盖：' + str(base))
    free_port('0.0.0.0', args.sftp_port)
    free_port(args.web_bind, args.web_port)
    needed = []
    if not shutil.which('docker'):
        needed += ['docker.io']
    if not shutil.which('ssh-keygen'):
        needed += ['openssh-client']
    if needed:
        run('apt-get', 'update')
        run('apt-get', 'install', '-y', *needed, 'ca-certificates')
    run('systemctl', 'enable', '--now', 'docker')
    if args.name in run('docker', 'ps', '-a', '--format', '{{.Names}}', capture=True).splitlines():
        p.error('同名容器已存在，未做修改')
    print('正在下载官方 SFTPGo 社区版镜像…', flush=True)
    image_ref, image_id = obtain_image()
    base.mkdir(mode=0o755)
    for sub in ['config', 'ui', 'state', 'data', 'data/data', 'data/backups']:
        directory = base / sub
        directory.mkdir(exist_ok=True, mode=0o755 if sub in ['config', 'ui'] else 0o700)
        if sub not in ['config', 'ui']:
            os.chown(directory, 1000, 1000)
    # Extract this exact version's UI without executing an auxiliary container.
    temporary = args.name + '-assets-' + secrets.token_hex(4)
    created = False
    try:
        run('docker', 'create', '--name', temporary, image_id)
        created = True
        run('docker', 'cp', temporary + ':/usr/share/sftpgo/templates', str(base / 'ui/templates'))
        run('docker', 'cp', temporary + ':/usr/share/sftpgo/static/locales', str(base / 'ui/locales'))
    finally:
        if created:
            run('docker', 'rm', temporary)
    count = install_ui(base / 'ui', Path(__file__).parent / 'locale/zh.json')
    key = base / 'state/id_ed25519'
    run('ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key))
    for file in [key, Path(str(key) + '.pub')]:
        os.chown(file, 1000, 1000)
    key.chmod(0o600)
    code = secrets.token_urlsafe(24)
    cfg = base / 'config/sftpgo.json'
    cfg.write_text(json.dumps(config(args.sftp_port, args.web_port, args.web_bind, code), ensure_ascii=False, indent=2), encoding='utf-8')
    os.chown(cfg, 1000, 1000)
    cfg.chmod(0o400)
    metadata = {'version': VERSION, 'sftpgo_version': SFTPGO_VERSION, 'image': image_ref,
                'image_id': image_id, 'name': args.name, 'web_port': args.web_port,
                'sftp_port': args.sftp_port, 'web_bind': args.web_bind}
    (base / 'deployment.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    for filename in ['deploy.py', 'localization.py', 'sftpctl.py', 'backup.py', 'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md']:
        shutil.copyfile(Path(__file__).parent / filename, base / filename)
    setup = base / 'SETUP.txt'
    setup.write_text(f'后台：http://服务器IP:{args.web_port}/web/admin?lng=zh\n初始化代码：{code}\nSFTP 端口：{args.sftp_port}\n', encoding='utf-8')
    setup.chmod(0o600)
    run(*docker_args(base, image_id, args.name))
    check_address = '127.0.0.1' if args.web_bind == '0.0.0.0' else args.web_bind
    for _ in range(40):
        try:
            with urllib.request.urlopen(f'http://{check_address}:{args.web_port}/healthz', timeout=2) as response:
                assert response.status == 200
            with urllib.request.urlopen(f'http://{check_address}:{args.web_port}/static/locales/zh/translation.json', timeout=2) as response:
                assert json.load(response)['title']['groups'] == '用户组'
            break
        except (OSError, AssertionError):
            time.sleep(1)
    else:
        raise RuntimeError('健康检查未通过。请运行 docker logs ' + args.name + ' 排查；数据已保留。')
    configure_firewall(args.sftp_port, args.web_port, args.web_bind, args.skip_firewall)
    print(f'\n安装完成，已加载 {count} 项中文翻译。')
    print(setup.read_text(encoding='utf-8'))
    if args.web_bind == '127.0.0.1':
        print('后台仅监听本机，请通过 SSH 隧道或反向代理访问。')
    else:
        print(f'请确认云安全组放行 TCP {args.web_port} 与 {args.sftp_port}；系统防火墙处理结果见上方。正式使用时配置 HTTPS。')
    print('原有系统 SSH 配置未修改；初始化代码保存在 ' + str(setup))

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print('安装未完成：' + str(exc) + '\n未删除已有数据。', file=sys.stderr)
        sys.exit(1)
