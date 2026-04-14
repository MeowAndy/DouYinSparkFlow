# 更新日志

## Dy0.0.4 - 2026-04-14

### 修复
- 修复“自动拉取好友”在未安装 Playwright Chromium 时直接报错：
  - `BrowserType.launch: Executable doesn't exist`
- 现在会在拉取前自动尝试安装浏览器（`python -m playwright install chromium`），减少首次部署失败。

### 优化
- cookies 输入兼容性增强：
  - 支持 JSON 数组
  - 支持包含 `cookies` / `data` 数组的 JSON 对象
  - 支持直接粘贴 `name=value; ...` 字符串（自动转换）
- 自动规范化 cookie 字段（`sameSite` / `expires` / `domain` / `path`），降低因格式不规范导致的失败概率。
- 保存配置时改为按“可用性”校验 cookies，不再只限定 JSON 数组，错误提示更直观。

### 文档
- README 增补 Cookie 获取方法与两种输入格式说明，降低新手上手门槛。

## Dy0.0.3.1 - 2026-04-14

### 修复
- 修复主页模板中 JS 对象转义遗漏导致的 `Internal Server Error`。
- 问题表现：访问 `/` 时 Flask 在 f-string 渲染阶段抛出 `NameError: username is not defined`。

## Dy0.0.3 - 2026-04-14

### 新增
- 新增“自动拉取好友昵称+ID”功能：基于当前账号 cookies 自动进入创作者消息页抓取好友列表。
- 新增一键回填目标：
  - `填入targets(昵称)`
  - `填入targets(ID)`
- 新增接口：`POST /api/friends/fetch`

### 优化
- 页面引导文案补充了“自动拉取好友 → 一键填入targets”的推荐流程。

## Dy0.0.2 - 2026-04-14

### 优化
- Web 控制台 UI 重排，增加小白引导说明与字段占位提示。
- 首页显式展示当前版本号：`Dy0.0.2`。
- 运行日志与更新日志分栏展示，状态更清晰。

### 新增
- 新增“更新脚本”按钮（`/api/update`），支持在线执行：
  - `git fetch origin`
  - `git reset --hard origin/main`
  - 依赖安装（自动兼容 `requirements.txt` 编码）
- 新增更新日志接口：`/api/update/log`。

## Dy0.0.1 - 2026-04-14

### 新增
- 新增 `web_console.py`：为 DouYinSparkFlow 提供 Web 控制台（默认端口 `8091`）。
- 支持在 Web 页面编辑核心配置：代理、消息模板、一言分类、匹配模式、超时与重试参数。
- 支持多账号任务配置：`username / unique_id / targets / cookies_json`。
- 支持一键保存配置、启动任务、查看实时运行日志。
- 配置持久化到 `data/web_console_config.json`。

### 说明
- 控制台运行的是原仓库 `main.py`，通过环境变量注入配置，不破坏原有任务逻辑。
- 首版以“可用+易部署”为目标，后续可继续加账号测试、定时任务、导入导出等功能。
