"""无显示环境（云服务器）下的 Web 版控制台。

桌面版用 Chromium WebView 承载 UI：页面里的 window.$py 通过 CDP 直调 Python。
服务器上没有显示器开不了窗口，这里把同一套桥换成 HTTP：

    GET  /                 官方 UI（app/web/dist/index.html），头部注入 Web 桥
    POST /api/py/<method>  与桌面版 window.$py 完全同一张方法表（bridge.call）
    GET  /api/events       SSE：把 bridge 事件（notify / browser_event）推给页面
    GET  /api/health       健康检查
    GET  /api/env          下载当前 .env
    POST /api/env          上传 .env（扫码登录在桌面版完成后，把配置带上来）

页面注入的桥把 window.$py 换成 fetch /api/py/...，事件流把
window.__pyOn(event, data) 喂回给 UI —— 对 Vue 代码零改动。

所有接口都要 Basic 认证：WEBUI_USER / WEBUI_PASSWORD（未设置时启动会
随机生成一个并打印在日志里）。端口 9000 上直接浏览器打开即用。

扫码登录（添加账号/刷新登录）需要弹出浏览器窗口，无显示的服务器上不可用：
请先在桌面版完成登录，再通过「上传 .env」或 /api/env 把配置带上来。
拉取会话列表、聊天导出是无头流程，在服务器上可以直接用。
"""

from __future__ import annotations

import base64
import json
import os
import queue
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "0.0.0.0"
PORT = int(os.getenv("WEBUI_PORT", "9000"))
AUTH_USER = os.getenv("WEBUI_USER", "douyin")
AUTH_PASSWORD = os.getenv("WEBUI_PASSWORD", "") or secrets.token_urlsafe(12)

SHIM = """<script>
(function(){
  window.__WEB_MODE__ = true;
  window.$py = function(method, payload){
    return fetch('/api/py/' + encodeURIComponent(method), {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload === undefined ? null : payload)
    }).then(function(r){ return r.json(); }).then(function(res){
      if (res && typeof res === 'object' && 'error' in res){
        var err = new Error(String(res.error)); err.pyError = true; throw err;
      }
      return res;
    });
  };
  function connect(){
    var es = new EventSource('/api/events');
    es.onmessage = function(e){
      try { var m = JSON.parse(e.data); if (window.__pyOn) window.__pyOn(m.event, m.data); }
      catch (_){ /* 忽略坏帧 */ }
    };
    es.onerror = function(){ es.close(); setTimeout(connect, 2000); };
  }
  function ready(fn){
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }
  ready(connect);
  ready(function(){
    function upload(){
      var input = document.createElement('input');
      input.type = 'file'; input.accept = '.env,.txt'; input.style.display = 'none';
      input.onchange = function(){
        var file = input.files[0]; if (!file) return;
        var reader = new FileReader();
        reader.onload = function(){
          fetch('/api/env', {method: 'POST', headers: {'Content-Type': 'text/plain'}, body: reader.result})
            .then(function(r){ return r.text(); })
            .then(function(t){ alert(t); location.reload(); });
        };
        reader.readAsText(file, 'utf-8');
      };
      input.click();
    }
    var btn = document.createElement('button');
    btn.textContent = '上传 .env 配置';
    btn.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:9999;'
      + 'padding:8px 14px;border-radius:8px;border:none;background:#4f7cff;color:#fff;'
      + 'cursor:pointer;font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.25)';
    btn.onclick = upload;
    document.body.appendChild(btn);
  });
})();
</script>"""

# ---------------------------------------------------------------------------
# 桥：与桌面版完全同一套业务（app/web/service.make_bridge）
# ---------------------------------------------------------------------------
bridge = None
ops = None

_SUBSCRIBERS: "list[queue.Queue]" = []
_SUB_LOCK = threading.Lock()


def _broadcast(event: str, data) -> None:
    with _SUB_LOCK:
        subs = list(_SUBSCRIBERS)
    for q in subs:
        try:
            q.put_nowait((event, data))
        except Exception:
            pass


def _pump_loop() -> None:
    """与桌面版宿主主循环等价：泵 worker 事件、转发 bridge 队列。"""
    import time

    while True:
        try:
            ops.pump()
            for event, data in bridge.drain():
                _broadcast(event, data)
        except Exception:
            pass
        time.sleep(0.4)


def _init_bridge():
    global bridge, ops
    from app.web.bridge import Bridge
    from app.web.service import make_bridge

    bridge = Bridge()
    ops = make_bridge(bridge)
    threading.Thread(target=_pump_loop, daemon=True, name="webui-pump").start()


# ---------------------------------------------------------------------------
# HTTP 处理
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "DouYinSparkFlow-WebUI"

    # -- 基础 ---------------------------------------------------------------
    def log_message(self, fmt, *args):  # 精简访问日志
        print(f"[webui] {self.address_string()} {fmt % args}")

    def _authed(self) -> bool:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            raw = base64.b64decode(header[6:].strip()).decode("utf-8")
            user, _, password = raw.partition(":")
        except Exception:
            return False
        return secrets.compare_digest(user, AUTH_USER) and secrets.compare_digest(password, AUTH_PASSWORD)

    def _deny(self) -> None:
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="DouYinSparkFlow"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send(self, code: int, content: bytes, content_type: str, extra=None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(content)

    def _json(self, payload, code: int = 200) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    # -- 路由 ---------------------------------------------------------------
    def do_GET(self):
        if not self._authed():
            self._deny()
            return
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._serve_index()
        elif path == "/api/health":
            self._json({"ok": True, "mode": "web"})
        elif path == "/api/events":
            self._serve_events()
        elif path == "/api/env":
            from app.paths import ENV_FILE

            try:
                content = Path(ENV_FILE).read_text(encoding="utf-8")
            except OSError:
                content = ""
            self._send(200, content.encode("utf-8"), "text/plain; charset=utf-8")
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._authed():
            self._deny()
            return
        path = self.path.split("?")[0]
        if path.startswith("/api/py/"):
            method = path[len("/api/py/"):]
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"null"
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else None
            except json.JSONDecodeError:
                self._json({"error": "请求体不是合法 JSON"}, 400)
                return
            result = bridge.call(method, payload)
            self._json(result)
        elif path == "/api/env":
            length = int(self.headers.get("Content-Length") or 0)
            content = self.rfile.read(length).decode("utf-8", "replace")
            ok, message = self._save_env(content)
            self._json({"ok": ok, "message": message}, 200 if ok else 400)
        else:
            self._json({"error": "not found"}, 404)

    # -- 各端点 -------------------------------------------------------------
    def _serve_index(self):
        import sys

        here = Path(__file__).resolve().parent          # 源码：…/app/webui_server.py → …/app
        candidates = [
            here / "web" / "dist" / "index.html",                        # 源码布局
            here.parent / "_internal" / "app" / "web" / "dist" / "index.html",  # PyInstaller onedir
            here / "_internal" / "app" / "web" / "dist" / "index.html",
        ]
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.insert(0, Path(meipass) / "app" / "web" / "dist" / "index.html")
        for candidate in candidates:
            if candidate.is_file():
                html = candidate.read_text(encoding="utf-8")
                # 注入 Web 桥：必须出现在应用脚本之前，页面才会走 HTTP 而不是 CDP
                if "<head>" in html:
                    html = html.replace("<head>", "<head>" + SHIM, 1)
                else:
                    html = SHIM + html
                return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        tried = "、".join(str(c) for c in candidates)
        self._json({"error": f"找不到 UI 构建产物（找过：{tried}）。请在 app/web/ui 执行 npm run build"}, 500)

    def _serve_events(self):
        """SSE：每个订阅者一个连接，事件逐帧推送。"""
        q: queue.Queue = queue.Queue()
        with _SUB_LOCK:
            _SUBSCRIBERS.append(q)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                try:
                    event, data = q.get(timeout=15)
                except Exception:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                frame = json.dumps({"event": event, "data": data}, ensure_ascii=False, default=str)
                self.wfile.write(f"event: message\ndata: {frame}\n\n".encode("utf-8"))
                self.wfile.flush()
        except Exception:
            pass
        finally:
            with _SUB_LOCK:
                if q in _SUBSCRIBERS:
                    _SUBSCRIBERS.remove(q)

    def _save_env(self, content: str) -> tuple:
        from app import paths

        text = content.strip()
        if not text:
            return False, "内容为空"
        if not any(key in text for key in ("TASKS=", "COOKIES_", "MESSAGE_TEMPLATE=")):
            return False, "内容不像 DouYinSparkFlow 的 .env（缺少 TASKS/COOKIES_/MESSAGE_TEMPLATE）"
        env_file = Path(paths.ENV_FILE)
        backup = env_file.with_suffix(".env.bak")
        try:
            if env_file.exists():
                backup.write_text(env_file.read_text(encoding="utf-8"), encoding="utf-8")
            env_file.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
        except OSError as exc:
            return False, f"写入失败：{type(exc).__name__}: {exc}"
        return True, "已保存（原文件备份为 .env.bak）。定时任务在下一轮触发时自动使用新配置。"


def main() -> int:
    _init_bridge()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[webui] 控制台入口: http://0.0.0.0:{PORT}  账号: {AUTH_USER}  密码: {AUTH_PASSWORD}")
    print(f"[webui] 可用方法与桌面版一致；扫码登录需在桌面版完成后上传 .env")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
