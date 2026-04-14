#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import subprocess
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request, Response
from playwright.sync_api import sync_playwright

APP_VERSION = 'Dy0.0.3'
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = DATA_DIR / 'web_console_config.json'
RUN_LOG = DATA_DIR / 'run.log'
UPDATE_LOG = DATA_DIR / 'update.log'

app = Flask(__name__)

RUN_STATE = {
    'running': False,
    'started_at': None,
    'finished_at': None,
    'exit_code': None,
}

UPDATE_STATE = {
    'running': False,
    'started_at': None,
    'finished_at': None,
    'exit_code': None,
}


def now_ts():
    return int(time.time())


def default_config():
    return {
        'proxy_address': '',
        'message_template': '[盖瑞]今日火花[加一]\\n—— [右边] 每日一言 [左边] ——\\n[API]',
        'hitokoto_types': ['文学', '影视', '诗词', '哲学'],
        'match_mode': 'nickname',
        'browser_timeout': 120000,
        'friend_list_wait_time': 2000,
        'task_retry_times': 3,
        'log_level': 'DEBUG',
        'accounts': [],
    }


def load_config():
    if not CONFIG_FILE.exists():
        return default_config()
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            return default_config()
        out = default_config()
        out.update(data)
        if not isinstance(out.get('accounts', []), list):
            out['accounts'] = []
        return out
    except Exception:
        return default_config()


def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')


def get_python_bin():
    py = str((BASE_DIR / '.venv' / 'bin' / 'python').resolve())
    return py if Path(py).exists() else 'python3'


def build_env_from_config(cfg):
    env = dict(**__import__('os').environ)

    accounts = cfg.get('accounts', [])
    tasks = []
    for a in accounts:
        uid = str(a.get('unique_id', '')).strip()
        if not uid:
            continue

        username = str(a.get('username', '')).strip() or uid
        targets = a.get('targets', [])
        if isinstance(targets, str):
            targets = [x.strip() for x in targets.split(',') if x.strip()]

        cookies_json = str(a.get('cookies_json', '')).strip()
        if not cookies_json:
            continue

        json.loads(cookies_json)

        tasks.append({'username': username, 'unique_id': uid, 'targets': targets})
        env[f'COOKIES_{uid}'.upper()] = cookies_json

    env['TASKS'] = json.dumps(tasks, ensure_ascii=False)
    env['PROXY_ADDRESS'] = str(cfg.get('proxy_address', '') or '')
    env['MESSAGE_TEMPLATE'] = str(cfg.get('message_template', '') or '')
    env['HITOKOTO_TYPES'] = json.dumps(cfg.get('hitokoto_types', []), ensure_ascii=False)
    env['MATCH_MODE'] = str(cfg.get('match_mode', 'nickname'))
    env['BROWSER_TIMEOUT'] = str(cfg.get('browser_timeout', 120000))
    env['FRIEND_LIST_WAIT_TIME'] = str(cfg.get('friend_list_wait_time', 2000))
    env['TASK_RETRY_TIMES'] = str(cfg.get('task_retry_times', 3))
    env['LOG_LEVEL'] = str(cfg.get('log_level', 'DEBUG'))
    return env


def run_main_background():
    RUN_STATE['running'] = True
    RUN_STATE['started_at'] = now_ts()
    RUN_STATE['finished_at'] = None
    RUN_STATE['exit_code'] = None

    cfg = load_config()
    try:
        env = build_env_from_config(cfg)
    except Exception as e:
        RUN_LOG.write_text(f'配置无效：{e}\\n', encoding='utf-8')
        RUN_STATE['running'] = False
        RUN_STATE['finished_at'] = now_ts()
        RUN_STATE['exit_code'] = 2
        return

    cmd = [get_python_bin(), 'main.py']
    ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    with RUN_LOG.open('w', encoding='utf-8') as f:
        f.write(f'[{ts}] === DouYinSparkFlow 任务开始 ===\\n')
        f.flush()
        p = subprocess.Popen(cmd, cwd=str(BASE_DIR), env=env, stdout=f, stderr=subprocess.STDOUT)
        code = p.wait()
        ts2 = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        f.write(f'\\n[{ts2}] === 任务结束 exit_code={code} ===\\n')

    RUN_STATE['running'] = False
    RUN_STATE['finished_at'] = now_ts()
    RUN_STATE['exit_code'] = code


def clean_requirements_file():
    req = BASE_DIR / 'requirements.txt'
    if not req.exists():
        return None

    raw = req.read_bytes()
    txt = None
    for enc in ('utf-8-sig', 'utf-16', 'utf-16le', 'utf-16be'):
        try:
            txt = raw.decode(enc)
            break
        except Exception:
            continue
    if txt is None:
        txt = raw.decode('utf-8', errors='ignore')

    lines = []
    for ln in txt.splitlines():
        s = ln.strip().lstrip('\ufeff')
        if not s or s.startswith('#'):
            continue
        lines.append(s)

    clean = DATA_DIR / 'requirements.clean.txt'
    clean.write_text('\\n'.join(lines) + '\\n', encoding='utf-8')
    return clean


def run_cmd(logf, cmd, cwd=None):
    logf.write(f"$ {' '.join(cmd)}\\n")
    logf.flush()
    p = subprocess.Popen(cmd, cwd=str(cwd or BASE_DIR), stdout=logf, stderr=subprocess.STDOUT)
    return p.wait()


def update_background():
    UPDATE_STATE['running'] = True
    UPDATE_STATE['started_at'] = now_ts()
    UPDATE_STATE['finished_at'] = None
    UPDATE_STATE['exit_code'] = None

    py = get_python_bin()
    ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    with UPDATE_LOG.open('w', encoding='utf-8') as f:
        f.write(f'[{ts}] === 开始更新 DouYinSparkFlow ({APP_VERSION}) ===\\n')

        code = run_cmd(f, ['git', 'fetch', 'origin'])
        if code != 0:
            UPDATE_STATE['running'] = False
            UPDATE_STATE['finished_at'] = now_ts()
            UPDATE_STATE['exit_code'] = code
            return

        code = run_cmd(f, ['git', 'reset', '--hard', 'origin/main'])
        if code != 0:
            UPDATE_STATE['running'] = False
            UPDATE_STATE['finished_at'] = now_ts()
            UPDATE_STATE['exit_code'] = code
            return

        run_cmd(f, [py, '-m', 'pip', 'install', '-U', 'pip'])

        clean = clean_requirements_file()
        if clean and clean.exists():
            code = run_cmd(f, [py, '-m', 'pip', 'install', '-r', str(clean)])
            if code != 0:
                UPDATE_STATE['running'] = False
                UPDATE_STATE['finished_at'] = now_ts()
                UPDATE_STATE['exit_code'] = code
                return

        code = run_cmd(f, [py, '-m', 'pip', 'install', 'flask'])

        ts2 = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        f.write(f'\\n[{ts2}] === 更新完成 exit_code={code} ===\\n')
        f.write('提示：若更新涉及 web_console.py，请重启 tmux dyflow 会话生效。\\n')

    UPDATE_STATE['running'] = False
    UPDATE_STATE['finished_at'] = now_ts()
    UPDATE_STATE['exit_code'] = code


def sanitize_cookies(cookies):
    out = []
    for c in cookies:
        if not isinstance(c, dict):
            continue
        x = dict(c)
        x.pop('sameSite', None)
        if x.get('expires') in ('', None):
            x.pop('expires', None)
        out.append(x)
    return out


def fetch_friends_by_cookies(cookies_json: str, timeout_ms: int = 90000):
    cookies = json.loads(cookies_json)
    if not isinstance(cookies, list):
        raise ValueError('cookies_json 必须是 JSON 数组')

    users = {}

    def on_response(resp):
        if 'aweme/v1/creator/im/user_detail/' not in resp.url:
            return
        try:
            data = resp.json()
            for item in data.get('user_list', []) or []:
                user = item.get('user', {}) or {}
                nickname = str(user.get('nickname', '')).strip()
                short_id = str(user.get('ShortId', '')).strip()
                user_id = str(item.get('user_id', '')).strip()
                key = short_id or user_id or nickname
                if not key:
                    continue
                users[key] = {
                    'nickname': nickname,
                    'short_id': short_id,
                    'user_id': user_id,
                }
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context()
        context.add_cookies(sanitize_cookies(cookies))
        page = context.new_page()
        page.on('response', on_response)

        page.goto('https://creator.douyin.com/', timeout=timeout_ms)
        page.goto('https://creator.douyin.com/creator-micro/data/following/chat', timeout=timeout_ms)

        # 尝试点击“好友”标签并滚动列表，触发更多 user_detail 接口
        try:
            friends_tab_selector = 'xpath=//*[@id="sub-app"]/div/div/div[1]/div[2]'
            page.wait_for_selector(friends_tab_selector, timeout=20000)
            page.locator(friends_tab_selector).click()
        except Exception:
            pass

        time.sleep(1.5)

        scrollable_selector = 'xpath=//*[@id="sub-app"]/div/div[1]/div[2]/div[2]/div/div/div[3]/div/div/div/ul/div'
        for _ in range(16):
            try:
                handle = page.locator(scrollable_selector).element_handle()
                if not handle:
                    break
                page.evaluate('(el) => { el.scrollTop += 900; }', handle)
                time.sleep(0.8)
            except Exception:
                time.sleep(0.5)

        time.sleep(1.2)
        context.close()
        browser.close()

    items = list(users.values())
    items.sort(key=lambda x: (x.get('nickname') or '', x.get('short_id') or ''))
    return items


@app.after_request
def no_cache(resp):
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp


@app.route('/')
def index():
    return Response(f"""
<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>DouYinSparkFlow 控制台</title>
<style>
body{{font-family:Arial,sans-serif;max-width:1180px;margin:18px auto;padding:0 12px;background:#fafafa}}
textarea,input,select{{width:100%;padding:8px;margin:4px 0;border:1px solid #ccc;border-radius:6px}}
button{{padding:8px 12px;margin:6px 6px 6px 0;border-radius:6px;border:1px solid #aaa;background:#fff;cursor:pointer}}
button.primary{{background:#1677ff;color:#fff;border-color:#1677ff}}
.card{{border:1px solid #ddd;border-radius:10px;padding:12px;margin:10px 0;background:#fff}}
pre{{background:#111;color:#eee;padding:12px;border-radius:8px;white-space:pre-wrap;max-height:320px;overflow:auto}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.small{{color:#666;font-size:13px}}
.badge{{display:inline-block;padding:2px 8px;border-radius:20px;background:#e6f4ff;color:#1677ff;font-size:12px;margin-left:8px}}
</style></head><body>
<h2>DouYinSparkFlow Web 控制台 <span class='badge'>版本 {APP_VERSION}</span></h2>

<div class='card'>
  <b>新手填写说明（先看这个）</b>
  <ol>
    <li>先新增账号，至少填：<code>unique_id</code>、<code>cookies_json</code></li>
    <li>可点“自动拉取好友昵称+ID”从当前账号会话获取好友列表</li>
    <li>再点击“填入targets(昵称)”或“填入targets(ID)”</li>
    <li>点「保存配置」后，再点「立即运行」</li>
  </ol>
  <div class='small'>match_mode=nickname 用昵称匹配；match_mode=short_id 用抖音号(ShortId)匹配。</div>
</div>

<div class='card'>
  <b>全局配置</b>
  <div class='grid'>
    <div><label>代理地址（可空）</label><input id='proxy_address' placeholder='例如: http://127.0.0.1:7890' /></div>
    <div><label>匹配模式</label><select id='match_mode'><option value='nickname'>nickname（按昵称）</option><option value='short_id'>short_id（按抖音号）</option></select></div>
    <div><label>浏览器超时(ms)</label><input id='browser_timeout' type='number' /></div>
    <div><label>好友列表等待(ms)</label><input id='friend_list_wait_time' type='number' /></div>
    <div><label>重试次数</label><input id='task_retry_times' type='number' /></div>
    <div><label>日志级别</label><input id='log_level' placeholder='DEBUG/INFO/WARNING/ERROR' /></div>
  </div>
  <label>一言分类(JSON数组)</label><input id='hitokoto_types' placeholder='例如：["文学","影视"]' />
  <label>消息模板</label><textarea id='message_template' rows='4'></textarea>
</div>

<div class='card'>
  <b>账号任务（一个账号一块）</b>
  <div id='accounts'></div>
  <button onclick='addAccount()'>+ 新增账号</button>
</div>

<div class='card'>
  <button class='primary' onclick='saveCfg()'>保存配置</button>
  <button class='primary' onclick='runTask()'>立即运行</button>
  <button onclick='reloadCfg()'>刷新配置</button>
  <button onclick='startUpdate()'>更新脚本</button>
  <span id='msg'></span>
</div>

<div class='grid'>
  <div class='card'>
    <b>运行日志</b>
    <pre id='log'>(暂无)</pre>
  </div>
  <div class='card'>
    <b>更新日志</b>
    <pre id='ulog'>(暂无)</pre>
  </div>
</div>

<script>
function esc(s){{return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}}

function accRow(a={{username:'',unique_id:'',targets:[],cookies_json:''}}){{
  const t = Array.isArray(a.targets)?a.targets.join(','):(a.targets||'');
  return `<div class='card acc'>
    <label>账号备注(username)</label><input class='username' value='${{esc(a.username)}}' placeholder='例如：主号A' />
    <label>唯一ID(unique_id)</label><input class='unique_id' value='${{esc(a.unique_id)}}' placeholder='必须唯一，例如：user001' />
    <label>目标好友(targets,逗号分隔)</label><input class='targets' value='${{esc(t)}}' placeholder='例如：张三,李四' />
    <label>Cookies(JSON数组)</label><textarea class='cookies_json' rows='5' placeholder='例如：[{{"name":"sid_tt","value":"...","domain":".douyin.com","path":"/"}}]'>${{esc(a.cookies_json)}}</textarea>
    <button onclick='fetchFriends(this)'>自动拉取好友昵称+ID</button>
    <button onclick='fillTargetsFromFriends(this, "nickname")'>填入targets(昵称)</button>
    <button onclick='fillTargetsFromFriends(this, "short_id")'>填入targets(ID)</button>
    <button onclick='this.parentElement.remove()'>删除此账号</button>
    <pre class='friends_preview'>(尚未拉取好友)</pre>
  </div>`;
}}

function addAccount(a){{
  document.getElementById('accounts').insertAdjacentHTML('beforeend', accRow(a));
}}

function readAccounts(){{
  return Array.from(document.querySelectorAll('.acc')).map(el => ({
    username: el.querySelector('.username').value.trim(),
    unique_id: el.querySelector('.unique_id').value.trim(),
    targets: el.querySelector('.targets').value.split(',').map(x=>x.trim()).filter(Boolean),
    cookies_json: el.querySelector('.cookies_json').value.trim(),
  }));
}}

async function fetchFriends(btn){{
  const card = btn.closest('.acc');
  const cookies = card.querySelector('.cookies_json').value.trim();
  const preview = card.querySelector('.friends_preview');
  if(!cookies){{ preview.innerText='请先填写 cookies_json'; return; }}

  btn.disabled = true;
  preview.innerText = '正在拉取好友列表，请稍候...';
  try{{
    const r = await fetch('/api/friends/fetch', {{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{cookies_json: cookies}})
    }});
    const d = await r.json();
    if(!d.ok){{
      preview.innerText = '拉取失败：' + (d.error || 'unknown');
      return;
    }}
    card._friends = d.items || [];
    if(!card._friends.length){{
      preview.innerText = '未拉取到好友（可能 cookie 不可用或页面结构变动）';
      return;
    }}
    const lines = card._friends.slice(0, 200).map((x,i)=>`${{i+1}}. 昵称=${{x.nickname||'-'}} | short_id=${{x.short_id||'-'}}`);
    preview.innerText = `共拉取 ${{card._friends.length}} 个好友\\n` + lines.join('\\n');
  }}catch(e){{
    preview.innerText = '拉取失败：' + e;
  }}finally{{
    btn.disabled = false;
  }}
}}

function fillTargetsFromFriends(btn, mode){{
  const card = btn.closest('.acc');
  const items = card._friends || [];
  if(!items.length){{
    card.querySelector('.friends_preview').innerText = '请先点击“自动拉取好友昵称+ID”';
    return;
  }}
  const vals = items.map(x => mode==='short_id' ? (x.short_id||'') : (x.nickname||'')).filter(Boolean);
  const uniq = Array.from(new Set(vals));
  card.querySelector('.targets').value = uniq.join(',');
}}

async function reloadCfg(){{
  const r = await fetch('/api/config');
  const d = await r.json();
  if(!d.ok) return;
  const c=d.config;
  for(const k of ['proxy_address','match_mode','browser_timeout','friend_list_wait_time','task_retry_times','log_level','message_template']){{
    const el=document.getElementById(k); if(el) el.value = c[k] ?? '';
  }}
  document.getElementById('hitokoto_types').value = JSON.stringify(c.hitokoto_types || []);
  const box=document.getElementById('accounts'); box.innerHTML='';
  (c.accounts||[]).forEach(addAccount);
}}

async function saveCfg(){{
  try{{
    const body={{
      proxy_address: document.getElementById('proxy_address').value.trim(),
      match_mode: document.getElementById('match_mode').value.trim(),
      browser_timeout: Number(document.getElementById('browser_timeout').value||120000),
      friend_list_wait_time: Number(document.getElementById('friend_list_wait_time').value||2000),
      task_retry_times: Number(document.getElementById('task_retry_times').value||3),
      log_level: document.getElementById('log_level').value.trim() || 'DEBUG',
      message_template: document.getElementById('message_template').value,
      hitokoto_types: JSON.parse(document.getElementById('hitokoto_types').value || '[]'),
      accounts: readAccounts(),
    }};
    const r = await fetch('/api/config',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});
    const d = await r.json();
    document.getElementById('msg').innerText = d.ok ? '✅ 已保存' : ('❌ '+(d.error||'保存失败'));
  }}catch(e){{
    document.getElementById('msg').innerText='❌ 保存失败: '+e;
  }}
}}

async function runTask(){{
  const r = await fetch('/api/run',{{method:'POST'}});
  const d = await r.json();
  document.getElementById('msg').innerText = d.ok ? '🚀 已启动' : ('❌ '+(d.error||'启动失败'));
}}

async function startUpdate(){{
  const r = await fetch('/api/update',{{method:'POST'}});
  const d = await r.json();
  document.getElementById('msg').innerText = d.ok ? '🔄 更新已启动' : ('❌ '+(d.error||'更新启动失败'));
}}

async function pollLog(){{
  const r = await fetch('/api/run/log?_t='+Date.now());
  const d = await r.json();
  if(!d.ok) return;
  const s=d.state||{{}};
  const head=`[状态] ${{s.running?'运行中':'空闲'}} | exit=${{s.exit_code}} | 开始=${{s.started_at||'-'}} | 结束=${{s.finished_at||'-'}}\\n\\n`;
  document.getElementById('log').innerText = head + (d.log || '(暂无)');
}}

async function pollUpdateLog(){{
  const r = await fetch('/api/update/log?_t='+Date.now());
  const d = await r.json();
  if(!d.ok) return;
  const s=d.state||{{}};
  const head=`[状态] ${{s.running?'更新中':'空闲'}} | exit=${{s.exit_code}} | 开始=${{s.started_at||'-'}} | 结束=${{s.finished_at||'-'}}\\n\\n`;
  document.getElementById('ulog').innerText = head + (d.log || '(暂无)');
}}

reloadCfg();
setInterval(pollLog, 2000);
setInterval(pollUpdateLog, 2000);
pollLog();
pollUpdateLog();
</script>
</body></html>
""", mimetype='text/html')


@app.route('/api/config')
def api_get_config():
    return jsonify({'ok': True, 'config': load_config(), 'version': APP_VERSION})


@app.route('/api/config', methods=['POST'])
def api_set_config():
    body = request.get_json(silent=True) or {}
    cfg = default_config()
    cfg.update(body)

    if cfg.get('match_mode') not in ('nickname', 'short_id'):
        return jsonify({'ok': False, 'error': 'match_mode 仅支持 nickname/short_id'})

    accounts = cfg.get('accounts', [])
    if not isinstance(accounts, list):
        return jsonify({'ok': False, 'error': 'accounts 必须是数组'})

    for i, a in enumerate(accounts, 1):
        uid = str(a.get('unique_id', '')).strip()
        cookies_json = str(a.get('cookies_json', '')).strip()
        if uid and cookies_json:
            try:
                json.loads(cookies_json)
            except Exception as e:
                return jsonify({'ok': False, 'error': f'第{i}个账号 cookies_json 不是合法JSON: {e}'})

    save_config(cfg)
    return jsonify({'ok': True})


@app.route('/api/run', methods=['POST'])
def api_run():
    if RUN_STATE['running']:
        return jsonify({'ok': False, 'error': '任务正在运行'})
    t = threading.Thread(target=run_main_background, daemon=True)
    t.start()
    return jsonify({'ok': True})


@app.route('/api/run/log')
def api_run_log():
    log = RUN_LOG.read_text(encoding='utf-8', errors='ignore') if RUN_LOG.exists() else ''
    return jsonify({'ok': True, 'log': log[-12000:], 'state': RUN_STATE})


@app.route('/api/update', methods=['POST'])
def api_update():
    if UPDATE_STATE['running']:
        return jsonify({'ok': False, 'error': '更新正在执行'})
    t = threading.Thread(target=update_background, daemon=True)
    t.start()
    return jsonify({'ok': True})


@app.route('/api/update/log')
def api_update_log():
    log = UPDATE_LOG.read_text(encoding='utf-8', errors='ignore') if UPDATE_LOG.exists() else ''
    return jsonify({'ok': True, 'log': log[-12000:], 'state': UPDATE_STATE})


@app.route('/api/friends/fetch', methods=['POST'])
def api_fetch_friends():
    body = request.get_json(silent=True) or {}
    cookies_json = str(body.get('cookies_json', '')).strip()
    if not cookies_json:
        return jsonify({'ok': False, 'error': 'cookies_json 不能为空'})
    try:
        items = fetch_friends_by_cookies(cookies_json)
        return jsonify({'ok': True, 'items': items, 'count': len(items)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8091)
