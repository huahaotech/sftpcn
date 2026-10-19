#!/usr/bin/env python3
"""Optional account helper. WebAdmin remains the main management interface."""
import argparse
import base64
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = Path(__file__).resolve().parent
PERMISSIONS = ['list', 'download', 'upload', 'overwrite', 'delete', 'rename', 'create_dirs', 'chtimes']


def username(value):
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', value):
        raise ValueError('用户名限 1–32 位小写字母、数字、下划线和短横线，且以字母开头')
    return value


def networks(values):
    if not values:
        raise ValueError('必须至少设置一个允许登录的 IP 或 CIDR，空白名单不被本工具接受')
    result = []
    for value in values:
        net = ipaddress.ip_network(value.strip(), strict=True)
        if net.prefixlen == 0:
            raise ValueError('拒绝 /0 全网放行，请明确填写所需的来源地址')
        if str(net) not in result:
            result.append(str(net))
    return result


def payload(name, allowed, password):
    return {
        'username': username(name), 'status': 1,
        'password': password, 'home_dir': f'/srv/sftpgo/data/{name}',
        'permissions': {'/': PERMISSIONS}, 'max_sessions': 5,
        'filesystem': {'provider': 0},
        'filters': {'allowed_ip': networks(allowed),
                    'denied_protocols': ['FTP', 'DAV', 'HTTP'],
                    'allow_api_key_auth': False},
    }


class API:
    def __init__(self, port, admin, password):
        self.url = f'http://127.0.0.1:{port}/api/v2'
        basic = base64.b64encode(f'{admin}:{password}'.encode()).decode()
        token = self.request('GET', '/token', authorization='Basic ' + basic)
        self.auth = 'Bearer ' + token['access_token']

    def request(self, method, path, data=None, authorization=None):
        headers = {'Authorization': authorization or self.auth}
        if data is not None:
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(self.url + path, method=method, headers=headers,
                                     data=None if data is None else json.dumps(data).encode())
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'API 返回 HTTP {exc.code}，请在 WebAdmin 或服务日志查看详情') from None


def apply_update(api, name, modify):
    path = '/users/' + urllib.parse.quote(username(name), safe='')
    user = api.request('GET', path)
    # The API omits password hashes; leave the field absent to preserve credentials.
    user.pop('password', None)
    modify(user)
    api.request('PUT', path + '?disconnect=1', user)


def main():
    p = argparse.ArgumentParser(description='SFTP 账号辅助工具（也可以直接使用 WebAdmin）')
    p.add_argument('--admin', default='admin')
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('list')
    for action in ['create', 'allow', 'disable', 'enable', 'password', 'delete']:
        parser = sub.add_parser(action)
        parser.add_argument('username')
        if action in ['create', 'allow']:
            parser.add_argument('--ip', action='append', required=True, help='可重复，可填写 IPv4/IPv6 或 CIDR')
    args = p.parse_args()
    if args.action != 'list':
        username(args.username)
    allowed = networks(args.ip) if args.action in ['create', 'allow'] else None
    meta = json.loads((BASE / 'deployment.json').read_text())
    secret = getpass.getpass('Web 管理员密码：')
    api = API(meta['web_port'], args.admin, secret)
    del secret
    if args.action == 'list':
        offset = 0
        while True:
            users = api.request('GET', f'/users?limit=100&offset={offset}')
            for user in users:
                print(json.dumps({'username': user['username'], 'status': user['status'],
                                  'home_dir': user['home_dir'],
                                  'allowed_ip': user.get('filters', {}).get('allowed_ip', [])}, ensure_ascii=False))
            if len(users) < 100:
                break
            offset += 100
        return
    name = args.username
    if args.action == 'create':
        password = getpass.getpass('新 SFTP 账号密码（至少 12 位）：')
        if len(password) < 12 or password != getpass.getpass('再次输入密码：'):
            raise ValueError('密码长度不足或两次输入不一致')
        user = payload(name, allowed, password)
        api.request('POST', '/users', user)
        print(f'账号已创建；独立目录 {user["home_dir"]} 会在首次成功登录时自动创建。')
    elif args.action == 'delete':
        if input(f'删除账号 {name}，保留文件。输入用户名确认：') != name:
            raise ValueError('已取消')
        # First revoke and close existing sessions; do not delete any files.
        apply_update(api, name, lambda user: user.update(status=0))
        api.request('DELETE', '/users/' + urllib.parse.quote(name, safe=''))
        print('账号已删除，文件保留。重新使用同名目录会重新暴露原文件，请先核对。')
    elif args.action == 'allow':
        apply_update(api, name, lambda user: user.setdefault('filters', {}).update(allowed_ip=allowed))
        print('IP 白名单已替换，原有会话已断开。')
    elif args.action == 'password':
        password = getpass.getpass('新密码（至少 12 位）：')
        if len(password) < 12 or password != getpass.getpass('再次输入密码：'):
            raise ValueError('密码长度不足或两次输入不一致')
        apply_update(api, name, lambda user: user.update(password=password))
        print('密码已修改，原有会话已断开。')
    else:
        def change_status(user):
            if args.action == 'enable':
                networks(user.get('filters', {}).get('allowed_ip', []))
            user['status'] = 1 if args.action == 'enable' else 0
        apply_update(api, name, change_status)
        print('账号状态已更新，原有会话已断开。')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f'操作失败：{exc}', file=sys.stderr)
        sys.exit(1)
