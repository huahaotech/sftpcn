from pathlib import Path
import contextlib
import io
import json
import sys
import unittest
import subprocess
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import deploy
import localization
import sftpctl

class LocaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.en = json.loads((ROOT / 'locale/en.json').read_text(encoding='utf-8'))
        cls.zh = json.loads((ROOT / 'locale/zh.json').read_text(encoding='utf-8'))
    def test_all_keys_and_variables(self):
        self.assertEqual(localization.validate(self.en, self.zh), 1040)
    def test_reject_changed_variable(self):
        with self.assertRaises(ValueError):
            localization.validate({'x': '{{val}}'}, {'x': '{{value}}'})
    def test_reject_missing_key(self):
        with self.assertRaises(ValueError):
            localization.validate({'x': 'hello'}, {})
    def test_contextual_errors_corrected(self):
        self.assertEqual(self.zh['title']['groups'], '用户组')
        self.assertEqual(self.zh['title']['connections'], '在线连接')
        self.assertNotIn('删除', self.zh['connections']['disconnect_confirm'])
        self.assertIn('动态验证码', self.zh['2fa']['info1'])
        self.assertEqual(self.zh['storage']['key_prefix'], '对象路径前缀')
    def test_patch_is_idempotent(self):
        template = "const lngs = {};\n defaultVersion: 'old',\nload: 'languageOnly',"
        once = localization.patch_template(template)
        self.assertEqual(localization.patch_template(once), once)
        self.assertIn('简体中文', once)

class InstallerTests(unittest.TestCase):
    def test_public_web_and_persistent_host_key(self):
        c = deploy.config(2022, 8080, '0.0.0.0', 'test-code')
        self.assertEqual(c['httpd']['bindings'][0]['address'], '0.0.0.0')
        self.assertEqual(c['sftpd']['host_keys'], ['/var/lib/sftpgo/id_ed25519'])
        self.assertEqual(c['sftpd']['enabled_ssh_commands'], [])
        self.assertEqual(c['ftpd']['bindings'][0]['port'], 0)
        self.assertEqual(c['webdavd']['bindings'][0]['port'], 0)
    def test_container_retains_source_ip_and_limits_privileges(self):
        a = deploy.docker_args(Path('/opt/sftpcn'), 'sha256:test', 'sftpcn')
        self.assertEqual(a[a.index('--network') + 1], 'host')
        self.assertEqual(a[a.index('--user') + 1], '1000:1000')
        self.assertEqual(a.count('--mount'), 5)
        self.assertIn('--read-only', a)
        self.assertNotIn('/var/run/docker.sock', ' '.join(a))
    def test_invalid_arguments_do_not_touch_system(self):
        for args in [['--sftp-port', '22'], ['--sftp-port', '8080'],
                     ['--install-dir', '/'], ['--name', 'bad;name']]:
            with self.subTest(args=args), patch.object(sys, 'argv', ['deploy.py'] + args), \
                 patch.object(deploy, 'run') as run, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    deploy.main()
                run.assert_not_called()
    def test_fixed_official_image(self):
        self.assertEqual(deploy.IMAGE, 'drakkan/sftpgo:v2.7.6')
    def test_sources_do_not_contain_deployment_credentials(self):
        # Public source must not contain installation-generated secret files.
        self.assertFalse((ROOT / 'SETUP.txt').exists())
        self.assertFalse((ROOT / 'deployment.json').exists())

class AccountTests(unittest.TestCase):
    def test_ipv4_ipv6_whitelist(self):
        self.assertEqual(sftpctl.networks(['192.0.2.10', '2001:db8::1']), ['192.0.2.10/32', '2001:db8::1/128'])
    def test_empty_universal_and_injected_whitelists_rejected(self):
        for values in [[], ['::/0'], ['0.0.0.0/0'], ['example.com;id']]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                sftpctl.networks(values)
    def test_path_escape_rejected(self):
        for value in ['../root', '/etc', 'test\nAllowUsers *']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                sftpctl.username(value)
    def test_home_is_independent_and_no_symlinks(self):
        a = sftpctl.payload('alice', ['192.0.2.10'], 'test-password')
        b = sftpctl.payload('bob', ['192.0.2.10'], 'test-password')
        self.assertNotEqual(a['home_dir'], b['home_dir'])
        self.assertNotIn('create_symlinks', a['permissions']['/'])
    def test_apply_update_disconnects_and_preserves_password(self):
        class API:
            def request(self, method, path, data=None):
                if method == 'GET':
                    return {'password': '', 'username': 'alice', 'filters': {}}
                self.result = method, path, data
        api = API()
        sftpctl.apply_update(api, 'alice', lambda u: u.update(status=0))
        self.assertEqual(api.result[1], '/users/alice?disconnect=1')
        self.assertNotIn('password', api.result[2])

class FirewallTests(unittest.TestCase):
    def invoke(self, status, bind='0.0.0.0', skip=False):
        with patch.object(deploy.shutil, 'which', return_value='/usr/sbin/ufw'), \
             patch.object(deploy.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, status, '')) as run, \
             contextlib.redirect_stdout(io.StringIO()):
            deploy.configure_firewall(12022, 18080, bind, skip)
            return [call.args[0] for call in run.call_args_list]
    def test_active_custom_ports(self):
        self.assertEqual(self.invoke('Status: active\n'), [['/usr/sbin/ufw', 'status'],
            ['/usr/sbin/ufw', 'allow', '12022/tcp'], ['/usr/sbin/ufw', 'allow', '18080/tcp']])
    def test_inactive_is_not_enabled(self):
        self.assertEqual(self.invoke('Status: inactive\n'), [['/usr/sbin/ufw', 'status']])
    def test_loopback_backend_not_opened(self):
        self.assertEqual(self.invoke('Status: active\n', '127.0.0.1'),
            [['/usr/sbin/ufw', 'status'], ['/usr/sbin/ufw', 'allow', '12022/tcp']])
    def test_explicit_skip(self):
        self.assertEqual(self.invoke('Status: active\n', skip=True), [])
    def test_absent_ufw_no_commands(self):
        with patch.object(deploy.shutil, 'which', return_value=None), patch.object(deploy.subprocess, 'run') as run, contextlib.redirect_stdout(io.StringIO()):
            deploy.configure_firewall(2022, 8080, '0.0.0.0')
            run.assert_not_called()
    def test_failure_is_reported_without_reset(self):
        with patch.object(deploy.shutil, 'which', return_value='/usr/sbin/ufw'), \
             patch.object(deploy.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'ufw')), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            deploy.configure_firewall(2022, 8080, '0.0.0.0')
            self.assertIn('手动检查', err.getvalue())

class WebsiteTests(unittest.TestCase):
    def test_no_production_connection_or_credentials(self):
        content = (ROOT / 'docs/index.html').read_text(encoding='utf-8')
        script = (ROOT / 'docs/script.js').read_text(encoding='utf-8')
        self.assertNotIn('fetch(', script)
        self.assertIn('交互示意', content)
        self.assertNotIn('root@', content)
    def test_anchor_targets_exist(self):
        import re
        content = (ROOT / 'docs/index.html').read_text(encoding='utf-8')
        ids = set(re.findall(r'id="([^"]+)"', content))
        for anchor in re.findall(r'href="#([^"]+)"', content):
            self.assertIn(anchor, ids)

if __name__ == '__main__':
    unittest.main(verbosity=2)
