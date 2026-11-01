"""app 网页界面：桥（bridge）与业务层（service）的单元测试。

桥测试不依赖浏览器；service 测试把 .env 与 local.json 都指到临时目录，
绝不碰仓库里真实的配置。
"""

from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path

# 默认关闭真实系统任务注册（不同发现方式下 tests/__init__.py 未必生效）
os.environ.setdefault("SCHEDULER_BACKEND", "noop")
os.environ.setdefault("APP_SCHEDULE_AUTOREGISTER", "0")

from app.config import profile_store, settings
from app.errors import AppError
from app.web.bridge import Bridge
from app.web.service import Service


class BridgeTests(unittest.TestCase):
    def test_call_dispatches_to_registered_handler(self):
        bridge = Bridge()
        bridge.register_all(add=lambda p: {"sum": p["a"] + p["b"]})
        result = bridge.call("add", {"a": 1, "b": 2})
        self.assertEqual(result, {"sum": 3})

    def test_unknown_method_returns_error(self):
        bridge = Bridge()
        result = bridge.call("nope", None)
        self.assertIn("error", result)
        self.assertIn("nope", result["error"])

    def test_handler_exception_wrapped(self):
        bridge = Bridge()

        def boom(_payload):
            raise RuntimeError("炸了")

        bridge.register_all(boom=boom)
        result = bridge.call("boom", None)
        self.assertIn("RuntimeError", result["error"])
        self.assertIn("炸了", result["error"])

    def test_non_json_safe_return_rejected(self):
        bridge = Bridge()
        bridge.register_all(bad=lambda _p: {"data": object()})
        result = bridge.call("bad", None)
        self.assertIn("error", result)

    def test_emit_and_drain(self):
        bridge = Bridge()
        bridge.emit("progress", {"done": 1})
        bridge.emit("done", {"ok": True})
        self.assertEqual(
            bridge.drain(),
            [("progress", {"done": 1}), ("done", {"ok": True})],
        )
        self.assertEqual(bridge.drain(), [])

    def test_emit_is_thread_safe(self):
        bridge = Bridge()
        threads = [
            threading.Thread(target=lambda: [bridge.emit("tick", i) for i in range(50)])
            for _ in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(bridge.drain()), 200)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env_file = self.root / ".env"
        # 把 local.json 指到临时目录，别写进仓库
        self._settings_backup = settings.SETTINGS_FILE
        settings.SETTINGS_FILE = self.root / "local.json"
        # profiles.json 同样指到临时目录，避免测试污染真实账号
        self._profiles_backup = profile_store.INDEX_FILE
        profile_store.INDEX_FILE = self.root / "profiles.json"
        self.service = Service(self.env_file)

    def tearDown(self):
        settings.SETTINGS_FILE = self._settings_backup
        profile_store.INDEX_FILE = self._profiles_backup
        self.tmp.cleanup()

    def test_get_config_returns_defaults_when_no_env(self):
        data = self.service.get_config()
        self.assertEqual(data["config"]["run_time"], "09:00:00")
        self.assertEqual(data["config"]["accounts"], [])
        self.assertEqual(data["env_path"], str(self.env_file))
        self.assertIn("tz_options", data["options"])

    def test_save_then_load_roundtrip(self):
        payload = {
            "config": {
                "proxy_address": "http://127.0.0.1:7890",
                "run_time": "10:20:30",
                "tz": "Asia/Tokyo",
                "message_template": "第一行\n第二行",
                "hitokoto_types": ["文学", "诗词"],
                "browser_action_timeout": 30,
                "im_scan_timeout": 300,
                "im_ready_timeout": 50,
                "friend_list_wait_time": 5,
                "im_max_steps": 100,
                "task_retry_times": 3,
                "log_level": "Info",
                "accounts": [
                    {
                        "username": "盖瑞",
                        "unique_id": "abc_123",
                        "cookies": "[{\"name\":\"sessionid\"}]",
                        "targets": ["托尼"],
                        "profile_folder": "",
                        "fingerprint": "",
                    }
                ],
            },
            "proxy": {"enabled": True, "tunnel": "wss://x:443?path=/ws", "user": "u", "password": "p"},
        }
        result = self.service.save_config(payload)
        self.assertIn("saved_at", result)

        reloaded = Service(self.env_file).get_config()
        config = reloaded["config"]
        self.assertEqual(config["run_time"], "10:20:30")
        self.assertEqual(config["message_template"], "第一行\n第二行")
        self.assertEqual(config["accounts"][0]["unique_id"], "abc_123")
        self.assertEqual(config["accounts"][0]["cookies"], '[{"name":"sessionid"}]')
        # 写盘后键名是 COOKIES_ABC_123
        env_text = self.env_file.read_text(encoding="utf-8")
        self.assertIn("COOKIES_ABC_123", env_text)
        # 代理进了 local.json，不污染 .env
        self.assertNotIn("tunnel", env_text)
        self.assertEqual(settings.proxy_config()["user"], "u")

    def test_get_config_reflects_fresh_conversations(self):
        """拉完会话列表后 get_config 要返回新名单（浏览器线程直接写 profiles.json）。"""
        self.service.save_config(
            {
                "config": {
                    "run_time": "09:00:00",
                    "tz": "Asia/Shanghai",
                    "message_template": "x",
                    "hitokoto_types": ["文学"],
                    "accounts": [
                        {"username": "a", "unique_id": "AAA", "cookies": "[1]", "targets": []}
                    ],
                }
            }
        )
        profile_store.bind("AAA", "pabc", fingerprint="12345")
        profile_store.set_conversations("AAA", ["甲", "乙"], folder="pabc")

        data = self.service.get_config()
        self.assertEqual(data["config"]["accounts"][0]["conversations"], ["甲", "乙"])

    def test_orphan_after_account_removed(self):
        payload = {
            "config": {
                "run_time": "09:00:00",
                "tz": "Asia/Shanghai",
                "message_template": "x",
                "hitokoto_types": ["文学"],
                "accounts": [
                    {"username": "a", "unique_id": "AAA", "cookies": "[1]", "targets": ["t"]}
                ],
            }
        }
        self.service.save_config(payload)
        # 换掉抖音号 → 旧 COOKIES_AAA 变成孤儿
        payload2 = {
            "config": {
                "run_time": "09:00:00",
                "tz": "Asia/Shanghai",
                "message_template": "x",
                "hitokoto_types": ["文学"],
                "accounts": [
                    {"username": "a", "unique_id": "BBB", "cookies": "[1]", "targets": ["t"]}
                ],
            }
        }
        data = self.service.save_config(payload2)
        self.assertIn("COOKIES_AAA", data["orphans"])
        cleaned = self.service.clean_orphans()
        self.assertEqual(cleaned["removed"], 1)

    def test_open_external_url_requires_url(self):
        with self.assertRaises(AppError):
            self.service.open_external_url({})

    def test_open_external_url_opens_system_browser(self):
        from unittest import mock

        with mock.patch("webbrowser.open", return_value=True) as open_url:
            result = self.service.open_external_url({"url": "https://example.com"})
        self.assertTrue(result["ok"])
        open_url.assert_called_once_with("https://example.com")

    def test_elevate_register_parses_exit_markers(self):
        from unittest import mock

        cases = {
            "EXIT:CANCELLED": lambda res: (res["cancelled"] is True, res["ok"] is False),
            "EXIT:0": lambda res: (res["cancelled"] is False, "ok" in res),
            "EXIT:2": lambda res: (res["cancelled"] is False, res["ok"] is False and "管理员注册未成功" in res["message"]),
        }
        for marker, check in cases.items():
            with self.subTest(marker=marker):
                with mock.patch("subprocess.run") as run:
                    run.return_value = mock.Mock(stdout=marker + "\n", stderr="", returncode=0)
                    result = self.service.schedule_elevate_register({"mode": "scheduled", "run_time": "09:00"})
                self.assertTrue(check(result))

    def test_manual_run_uses_launcher_argv(self):
        """手动执行的子进程命令必须由 Launcher 生成——打包成 EXE 后
        sys.executable 是程序自身，拼 main.py 会得到退出码 2。"""
        from unittest import mock

        started = {}

        def fake_popen(argv, **kwargs):
            started["argv"] = list(argv)
            started["cwd"] = kwargs.get("cwd")
            proc = mock.Mock()
            proc.poll.return_value = None
            proc.returncode = None
            return proc

        self.service.save_config(
            {
                "config": {
                    "run_time": "09:00:00",
                    "tz": "Asia/Shanghai",
                    "message_template": "x",
                    "hitokoto_types": ["文学"],
                    "accounts": [
                        {"username": "a", "unique_id": "AAA", "cookies": "[1]", "targets": ["t"]}
                    ],
                }
            }
        )
        with mock.patch("subprocess.Popen", side_effect=fake_popen):
            result = self.service.manual_run_start()

        self.assertTrue(result["running"])
        from app.scheduler.core import Launcher
        expected = Launcher.detect().task_argv()
        self.assertEqual(started["argv"], expected)
        # 停止状态轮询会把进程标记为结束
        self.service.manual_run._process.poll.return_value = 0
        self.service.manual_run._process.returncode = 0
        status = self.service.manual_run_status()
        self.assertFalse(status["running"])

    def test_elevate_register_reports_failure_detail(self):
        from unittest import mock

        with mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(stdout="", stderr="boom", returncode=1)
            result = self.service.schedule_elevate_register({"mode": "scheduled"})
        self.assertFalse(result["ok"])
        self.assertIn("管理员注册未成功", result["message"])


if __name__ == "__main__":
    unittest.main()