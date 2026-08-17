import os
import subprocess
import sys
from pathlib import Path
from unittest import TestCase


PROJECT_DIR = Path(__file__).resolve().parents[1]


class SettingsSecurityTest(TestCase):
    def _import_settings(self, env_overrides: dict[str, str]):
        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": str(PROJECT_DIR),
                "DJANGO_SETTINGS_MODULE": "fipai.settings",
            }
        )
        for key in ("DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS", "DJANGO_DEBUG"):
            env.pop(key, None)
        env.update(env_overrides)

        cmd = [
            sys.executable,
            "-c",
            (
                "import fipai.settings as s; "
                "print('SECRET_OK', bool(s.SECRET_KEY)); "
                "print('ALLOWED_HOSTS', ','.join(s.ALLOWED_HOSTS))"
            ),
        ]
        return subprocess.run(cmd, cwd=PROJECT_DIR, env=env, capture_output=True, text=True)

    def test_production_requires_secret_key(self):
        result = self._import_settings(
            {
                "DJANGO_DEBUG": "false",
                "DJANGO_ALLOWED_HOSTS": "account.fipai.cn",
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)

    def test_production_requires_allowed_hosts(self):
        result = self._import_settings(
            {
                "DJANGO_DEBUG": "false",
                "DJANGO_SECRET_KEY": "prod-secret",
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_ALLOWED_HOSTS", result.stderr)

    def test_debug_mode_uses_local_defaults_when_env_missing(self):
        result = self._import_settings({"DJANGO_DEBUG": "true"})
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("ALLOWED_HOSTS localhost,127.0.0.1,[::1]", result.stdout)

    def test_production_parses_allowed_hosts_from_env(self):
        result = self._import_settings(
            {
                "DJANGO_DEBUG": "false",
                "DJANGO_SECRET_KEY": "prod-secret",
                "DJANGO_ALLOWED_HOSTS": "account.fipai.cn,home.fipai.cn",
            }
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("ALLOWED_HOSTS account.fipai.cn,home.fipai.cn", result.stdout)
