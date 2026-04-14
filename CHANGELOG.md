# 更新日志

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
