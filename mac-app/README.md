# 内容分发台 macOS 应用

Swift/WebKit 外壳会启动本机服务并展示独立窗口。退出应用时，它会停止自己启动的服务；如果 4318 端口已有分发台服务，则只连接已有服务。

## 构建

当前 `build.sh` 是开发机打包脚本，已在 Apple Silicon/macOS 及 Xcode 自带 Python 3.9 环境下使用。它要求项目根目录已有 `.venv`，并且安装了上传器 `.sau-venv`、`integrations/social-auto-upload`。还需 Xcode 命令行工具、Swift 编译器、Python 图标依赖。上传器是外部项目，需要先按[根 README](../README.md)与上游说明安装。其他 Mac 或 Python/Xcode 版本可能需要调整 `build.sh` 中的运行时路径。

```sh
./mac-app/build.sh
```

脚本构建 `dist/内容分发台.app` 并安装到 `~/Applications/内容分发台.app`，不会将业务数据打进应用。构建过程使用本机临时签名；跨机器分发还需要解决签名、公证与运行时安装问题。当前仓库不提供可直接下载的通用安装包。

业务数据在 `~/Library/Application Support/内容分发台/data/`，应用日志为该目录中的 `mac-app.log`。首次构建的迁移脚本可能将项目 `data/` 复制到应用数据目录；运行前请检查目标目录，避免把旧数据误当成新数据。应用退出后调度也会停止；文章扩展需在 Chrome 中保持连接。
