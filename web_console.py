#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import subprocess
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request, Response

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = DATA_DIR / 'web_console_config.json'
RUN_LOG = DATA_DIR / 'run.log'

app = Flask(__name__)

RUN_STATE = {
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
        'accounts': [],  # [{username, unique_id, targets:[...], cookies_json}]
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


def build_env_from_config(cfg):
    env = os.environ.copy()

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

        # cookie 先做一次 json 合法性校验
        json.loads(cookies_json)

        tasks.append({
            'username': username,
            'unique_id': uid,
            'targets': targets,
        })
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
        RUN_LOG.write_text(f'配置无效：{e}\n', encoding='utf-8')
        RUN_STATE['running'] = False
        RUN_STATE['finished_at'] = now_ts()
        RUN_STATE['exit_code'] = 2
        return

    py = str((BASE_DIR / '.venv' / 'bin' / 'python').resolve())
    if not Path(py).exists():
        py = 'python3'

    cmd = [py, 'main.py']
    ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    with RUN_LOG.open('w', encoding='utf-8') as f:
        f.write(f'[{ts}] === DouYinSparkFlow 任务开始 ===\n')
        f.flush()
        p = subprocess.Popen(cmd, cwd=str(BASE_DIR), env=env, stdout=f, stderr=subprocess.STDOUT)
        code = p.wait()
        ts2 = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        f.write(f'\n[{ts2}] === 任务结束 exit_code={code} ===\n')

    RUN_STATE['running'] = False
    RUN_STATE['finished_at'] = now_ts()
    RUN_STATE['exit_code'] = code


@app.after_request
def no_cache(resp):
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp


@app.route('/')
def index():
    return Response("""
<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>DouYinSparkFlow 控制台</title>
<style>
body{font-family:Arial,sans-serif;max-width:1100px;margin:18px auto;padding:0 12px}
textarea,input,select{width:100%;padding:6px;margin:4px 0}
button{padding:8px 12px;margin:6px 6px 6px 0}
.card{border:1px solid #ddd;border-radius:10px;padding:12px;margin:10px 0}
pre{background:#111;color:#eee;padding:12px;border-radius:8px;white-space:pre-wrap}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
</style></head><body>
<h2>DouYinSparkFlow Web 控制台（Dy0.0.1）</h2>
<div class='card'>
  <b>全局配置</b>
  <div class='grid'>
    <div><label>代理地址</label><input id='proxy_address' /></div>
    <div><label>匹配模式</label><select id='match_mode'><option value='nickname'>nickname</option><option value='short_id'>short_id</option></select></div>
    <div><label>浏览器超时(ms)</label><input id='browser_timeout' type='number' /></div>
    <div><label>好友列表等待(ms)</label><input id='friend_list_wait_time' type='number' /></div>
    <div><label>重试次数</label><input id='task_retry_times' type='number' /></div>
    <div><label>日志级别</label><input id='log_level' /></div>
  </div>
  <label>一言分类(JSON数组)</label><input id='hitokoto_types' />
  <label>消息模板</label><textarea id='message_template' rows='4'></textarea>
</div>

<div class='card'>
  <b>账号任务（一个账号一块）</b>
  <div id='accounts'></div>
  <button onclick='addAccount()'>+ 新增账号</button>
</div>

<div class='card'>
  <button onclick='saveCfg()'>保存配置</button>
  <button onclick='runTask()'>立即运行</button>
  <button onclick='reloadCfg()'>刷新配置</button>
  <span id='msg'></span>
</div>

<div class='card'>
  <b>运行日志</b>
  <pre id='log'>(暂无)</pre>
</div>

<script>
function accRow(a={username:'',unique_id:'',targets:[],cookies_json:''}){
  const t = Array.isArray(a.targets)?a.targets.join(','):(a.targets||'');
  return `<div class='card acc'>
    <label>账号备注(username)</label><input class='username' value='${a.username||''}' />
    <label>唯一ID(unique_id)</label><input class='unique_id' value='${a.unique_id||''}' />
    <label>目标好友(targets,逗号分隔)</label><input class='targets' value='${t}' />
    <label>Cookies(JSON数组)</label><textarea class='cookies_json' rows='6'>${a.cookies_json||''}</textarea>
    <button onclick='this.parentElement.remove()'>删除此账号</button>
  </div>`;
}

function addAccount(a){
  document.getElementById('accounts').insertAdjacentHTML('beforeend', accRow(a));
}

function readAccounts(){
  return Array.from(document.querySelectorAll('.acc')).map(el => ({
    username: el.querySelector('.username').value.trim(),
    unique_id: el.querySelector('.unique_id').value.trim(),
    targets: el.querySelector('.targets').value.split(',').map(x=>x.trim()).filter(Boolean),
    cookies_json: el.querySelector('.cookies_json').value.trim(),
  }));
}

async function reloadCfg(){
  const r = await fetch('/api/config');
  const d = await r.json();
  if(!d.ok) return;
  const c=d.config;
  for(const k of ['proxy_address','match_mode','browser_timeout','friend_list_wait_time','task_retry_times','log_level','message_template']){
    const el=document.getElementById(k); if(el) el.value = c[k] ?? '';
  }
  document.getElementById('hitokoto_types').value = JSON.stringify(c.hitokoto_types || []);
  const box=document.getElementById('accounts'); box.innerHTML='';
  (c.accounts||[]).forEach(addAccount);
}

async function saveCfg(){
  try{
    const body={
      proxy_address: document.getElementById('proxy_address').value.trim(),
      match_mode: document.getElementById('match_mode').value.trim(),
      browser_timeout: Number(document.getElementById('browser_timeout').value||120000),
      friend_list_wait_time: Number(document.getElementById('friend_list_wait_time').value||2000),
      task_retry_times: Number(document.getElementById('task_retry_times').value||3),
      log_level: document.getElementById('log_level').value.trim() || 'DEBUG',
      message_template: document.getElementById('message_template').value,
      hitokoto_types: JSON.parse(document.getElementById('hitokoto_types').value || '[]'),
      accounts: readAccounts(),
    };
    const r = await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d = await r.json();
    document.getElementById('msg').innerText = d.ok ? '✅ 已保存' : ('❌ '+(d.error||'保存失败'));
  }catch(e){
    document.getElementById('msg').innerText='❌ 保存失败: '+e;
  }
}

async function runTask(){
  const r = await fetch('/api/run',{method:'POST'});
  const d = await r.json();
  document.getElementById('msg').innerText = d.ok ? '🚀 已启动' : ('❌ '+(d.error||'启动失败'));
}

async function pollLog(){
  const r = await fetch('/api/run/log?_t='+Date.now());
  const d = await r.json();
  if(!d.ok) return;
  const s=d.state||{};
  const head=`[状态] ${s.running?'运行中':'空闲'} | exit=${s.exit_code} | 开始=${s.started_at||'-'} | 结束=${s.finished_at||'-'}\n\n`;
  document.getElementById('log').innerText = head + (d.log || '(暂无)');
}

reloadCfg();
setInterval(pollLog, 2000);
pollLog();
</script>
</body></html>
""", mimetype='text/html')


@app.route('/api/config')
def api_get_config():
    return jsonify({'ok': True, 'config': load_config()})


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

    # 基础校验
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8091)
