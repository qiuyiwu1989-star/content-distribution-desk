# 内容分发台 / Content Distribution Desk

一个面向个人创作者的本地内容分发工作台。导入文章、图片或视频成品后，为不同平台建立独立任务，检查素材与规则，确认发布版本，再执行并核对平台回执。

**当前状态：本地管理流程可用；自动连接器仍需用各平台真实账号逐一联调。** 请先在测试账号中验证草稿、发布和回执，再用于正式内容。

## 功能与流程

1. 在「渠道账号」登记账号，并选择人工交付或连接器。
2. 在「成品包」导入正文、图片和视频；MD/TXT 文件可导入正文。
3. 批量安排渠道，为每个渠道分别调整标题、正文、素材顺序和封面。
4. 运行发布检查，确认版本，并选择立即执行或排期。
5. 在「执行中心」核对结果；结果未知时先到平台检查，避免重复发布。公开作品以平台链接与核对说明收尾。

网站内容可以先在 `qiuyiwu.com` 写作后台通过发布闸，再点击「导出到本机分发台的内容快照」下载 JSON。在本机分发台的「新建发布包」中选择「选择网站内容快照」导入。导入只创建成品包；仍需预览、安排渠道、批准任务。相同来源和正文版本重复导入会打开已有成品包；来源正文更新后生成新包，旧渠道版本不被覆盖。导出的是正文快照及审批记录，不包含图片、视频，也不证明网站公开页面已上线。素材需在导入后追加。

平台规则、状态机和验收范围见[开发计划与验收](docs/开发计划与验收.md)。
创作 Agent 准备视频号内容时，使用[微信视频号发布包规范](docs/微信视频号发布包规范.md)中的文件清单、`manifest.json` 模板和交接检查。

## 本地启动

需要 Python 3.9+。在 macOS 上：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py
```

打开 <http://127.0.0.1:4318/>。也可以在完成环境安装后双击 `启动分发台.command`。运行测试：

```sh
.venv/bin/python -m unittest discover -s tests -v
```

默认仅监听 `127.0.0.1:4318`。可用 `PORT`、`DESK_BRIDGE_PORT`、`DESK_DATA_DIR` 指定端口和数据位置。默认数据位于 `~/Library/Application Support/内容分发台/data/`，包含数据库、原始素材、执行日志和桥接口令；**请自行备份，勿提交到 Git**。页面导出的备份含内容与附件，须作为私有文件保存。

调度器随服务运行，每 20 秒处理到期任务；关闭服务后不会执行。重启时，中断中的任务进入「待核对」而不会盲目重试。此版本只适合单人本机使用，不能直接开放公网或用多个 WSGI worker 运行。

## 给 AI Agent 使用的本机 CLI

保持分发台应用运行，然后执行 `./desk_cli.py --help`（或 `python3 desk_cli.py --help`）。CLI 输出 JSON，适合 Agent 解析；仅允许连接 `127.0.0.1` 或 `localhost`。

```sh
python3 desk_cli.py list packages
python3 desk_cli.py list accounts
python3 desk_cli.py import-site ./distribution-example.json
python3 desk_cli.py distribute 包ID --target 账号ID:article
python3 desk_cli.py preflight 任务ID
```

还可用 `create-package --title 标题 --body-file 正文.md` 新建成品包，或用 `list tasks`、`list runs` 查看进度。CLI **不提供提交发布、重试和回填发布结果的命令**；这些高影响操作仍在应用中由人确认。网站快照文件含未公开正文，调用 Agent 时不要把文件内容或本机会话令牌发送到外部服务。

本阶段先交付无额外依赖的 CLI。MCP 服务可在这一层复用相同的只读与草稿创建能力，但尚未作为独立服务安装。

## 平台连接

- **公众号、知乎、B 站文章：** 使用 [Wechatsync](https://github.com/wechatsync/Wechatsync) Chrome 扩展，经本机 WebSocket 桥接。安装扩展并在平台登录后，将扩展 Token 配入分发台。
- **视频号、小红书、抖音、B 站视频及部分图文：** 对接 [social-auto-upload](https://github.com/dreammis/social-auto-upload)。上游版本记录在 `integrations/versions.json`，其源码和浏览器登录态不包含在本仓库。要使用连接器，需另行按上游说明安装 Python 3.12 环境、Playwright/Patchright 和 Chromium，并完成平台登录。连接器适配代码见 `adapters.py`。
- **公众号短图文：** 当前使用人工交付。抖音精选没有单独的上传目标。

连接器操作可能受平台页面或政策变更影响；项目尚未完成所有真实平台的草稿和作品回执验收。请勿将「任务已发出」当作「平台已发布」。

## macOS 应用

仓库包含 Swift/WebKit 外壳源码，可构建双击启动的本机应用。当前构建脚本针对已安装 Xcode 命令行环境、项目 Python 虚拟环境及上传器运行时的 macOS 开发机器；它会把应用安装到 `~/Applications/内容分发台.app`。构建步骤和限制见 [macOS 应用说明](mac-app/README.md)。应用运行时仍需保持打开，才能执行定时任务。

## 安全与项目范围

服务校验 Host、跨站来源和写入令牌；账号登录状态留在本机，不应提交到仓库。网站内容快照在下载与导入期间也是私有文件，请勿转发或提交到 Git。仓库只提供源码和测试，不包含用户内容、数据库、浏览器 Cookie、密钥或构建产物。当前项目不附带开源许可证；公开可见不代表授予修改或再分发许可。
