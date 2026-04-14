# DouYinSparkFlow（超详细小白教程）

> 这是一个用于“抖音火花续火”的自动化工具。  
> 你可以用 **Web 控制台** 配置账号、目标好友，然后一键运行任务。

---

## 0. 这个项目能做什么？

- 自动给抖音好友发消息，维持火花
- 支持多账号、多目标好友
- 支持可视化配置（Web 控制台）
- 支持在线更新脚本（控制台里点按钮）

---

## 1. 小白先看：你需要准备什么

最少准备 4 样：

1. 一台能联网的 Linux 服务器（推荐 Ubuntu 22/24）
2. Python 3.8+（建议 3.10+）
3. 抖音账号 cookie（JSON 数组格式）
4. 目标好友（昵称或 short_id）

---

## 2. 下载项目

### 方式 A（推荐）：克隆仓库

```bash
git clone https://github.com/MeowAndy/DouYinSparkFlow.git
cd DouYinSparkFlow
```

### 方式 B：下载 ZIP

- 打开仓库页面下载 ZIP
- 解压后进入目录

---

## 3. 安装依赖（一步步）

> 以下命令在项目目录执行。

### 3.1 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3.2 升级 pip

```bash
python -m pip install -U pip
```

### 3.3 安装依赖

```bash
pip install -r requirements.txt
pip install flask
```

> 如果 requirements.txt 编码异常（极少数机器），可以用控制台的“更新脚本”自动处理。

---

## 4. 启动 Web 控制台（重点）

```bash
python web_console.py
```

默认地址：

- 本机：`http://127.0.0.1:8091`
- 远程：`http://你的服务器IP:8091`

---

## 5. 控制台怎么填（最重要）

页面里分 2 部分：

## A) 全局配置

- **proxy_address**：代理地址（可空）
- **match_mode**：匹配模式
  - `nickname`：targets 填好友昵称（推荐新手）
  - `short_id`：targets 填好友抖音号 short_id
- **browser_timeout**：浏览器超时（毫秒）
- **friend_list_wait_time**：好友列表等待时间（毫秒）
- **task_retry_times**：重试次数
- **log_level**：日志级别（DEBUG/INFO）
- **hitokoto_types**：一言类型 JSON 数组
- **message_template**：发送消息模板

## B) 账号任务（一个账号一块）

每个账号至少填：

- **username**：备注名（随便填，便于区分）
- **unique_id**：唯一标识（不能重复）
- **cookies_json**：该账号 cookie 的 JSON 数组
- **targets**：目标好友列表（英文逗号分隔）

### 推荐流程（避免出错）

1. 先填 `username / unique_id / cookies_json`
2. 点击 **自动拉取好友昵称+ID**
3. 再点：
   - **填入targets(昵称)**（如果你 match_mode=nickname）
   - **填入targets(ID)**（如果你 match_mode=short_id）
4. 点击 **保存配置**
5. 点击 **立即运行**

---

## 6. cookies_json 从哪来？

你可以使用两种输入方式（新版都支持）：

### 方式 A（推荐）：JSON 数组 cookies

常见来源：
- 浏览器开发者工具导出 cookies（JSON）
- 你现有脚本里已存的 cookie JSON

格式示例（简化）：

```json
[
  {
    "name": "sessionid",
    "value": "xxxx",
    "domain": ".douyin.com",
    "path": "/"
  }
]
```

### 方式 B：Cookie 字符串（也可直接粘贴）

例如：

```text
sessionid=xxxx; sid_tt=yyyy; passport_csrf_token=zzzz
```

控制台会自动转换为 Playwright 可用格式。

### 推荐获取 Cookie 的稳妥方法

1. 用 Chrome 打开：`https://creator.douyin.com/creator-micro/data/following/chat`
2. 登录后按 `F12` → `Application` → `Storage` → `Cookies`
3. 选择 `https://creator.douyin.com` 或 `.douyin.com`
4. 导出为 JSON（优先）或复制为 `name=value; ...`
5. 粘贴到控制台账号里的 `cookies_json`

> 说明：新版已自动处理 `sameSite`、`expires`、`domain/path` 等兼容问题，避免常见解析报错。

---

## 7. 如何运行与看结果

### 运行

- 点控制台里的 **立即运行**

### 看结果

- 左侧“运行日志”里会实时输出执行情况
- 有报错就按日志关键字排查（cookie失效、目标不存在、页面超时等）

---

## 8. 更新脚本怎么用

控制台有 **更新脚本** 按钮，点击会自动执行：

- `git fetch origin`
- `git reset --hard origin/main`
- 依赖安装

更新进度看右侧“更新日志”。

> 注意：如果更新包含 `web_console.py` 变更，建议重启控制台进程。

---

## 9. 常见问题（FAQ）

### Q1：打开控制台报 500 / Internal Server Error
- 先点更新脚本
- 或手动 `git pull` 后重启 `web_console.py`

### Q2：自动拉取好友为空
- 先检查 cookies 是否有效
- 检查账号是否能正常打开抖音创作者消息页

### Q3：targets 填昵称还是 ID？
- `match_mode=nickname` → 填昵称
- `match_mode=short_id` → 填 short_id

### Q4：多账号怎么配？
- 每个账号新增一个“账号任务卡片”
- `unique_id` 必须不同

---

## 10. 推荐部署方式

- 先在测试账号上验证
- 单账号跑通后再加多账号
- 生产环境建议用 `tmux` 或 `systemd` 守护进程

---

## 11. 更新日志

- 查看完整变更：[`CHANGELOG.md`](./CHANGELOG.md)
- 当前 Web 控制台版本请以页面右上角徽标为准

---

## 12. 免责声明

本项目仅供学习与个人研究，请遵守抖音平台规则与当地法律法规。使用风险自负。
