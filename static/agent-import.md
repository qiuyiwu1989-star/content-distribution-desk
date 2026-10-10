# 内容工作台 · Agent 批次导入规范

本规范用于剪辑完成后整批入库。保留内容身份、版本、批次和用户确认的顺序；不创建发布任务、不确认人工审阅、不执行公开发布。

## 连接 MCP

当前为本机 stdio MCP。Agent 必须能访问这台电脑上的文件和本机服务；复制本规范链接不等于已经安装 MCP。远端 Agent 需要本机执行器；云端 MCP 尚未开放。

MCP 配置（把项目路径改为本机实际位置）：

```json
{"mcpServers":{"content-desk":{"command":"python3","args":["/绝对路径/content-distribution-desk/mcp/desk_mcp.py"]}}}
```

先读取同一服务的 `/api/agent-import-info`（例如 http://127.0.0.1:4318/api/agent-import-info），获取本机实际 MCP 配置，避免猜测安装路径。

依次调用 desk_status、preview_library_batch、import_library_batch。

## 批次清单

在视频目录旁保存 manifest.json。视频和封面使用可读的绝对路径，或相对 manifest 的路径。

```json
{"batch_name":"示例课程批次","items":[{"id":"course-001","version":"v1","sequence":1,"title":"内容内部名称","video":"001-video.mp4","cover":"001-cover.png","body":"发布正文","tags":["相关话题"],"source":{"file":"原始课程.mp4","start":120,"end":190},"review":{"status":"pending"},"intent":"publish"}]}
```

- id 是稳定内容身份，version 标记成片版本；同一清单不能重复身份与版本。
- sequence 为正整数，同批次不能重复。不要按文件修改时间重新排序。
- video 必须真实存在且非空；cover 可暂缺，预演会明确报告。
- body、tags、source、review 按实际内容填写。技术检查不等于人工审阅。
- preview_library_batch({"manifest_path":"/绝对路径/manifest.json"}) 先检查。
- import_library_batch 同样参数整批入库。保留旁边的 .desk-receipt.json，失败后重试会继续未完成部分。
- 新版本会形成新内容记录，当前不自动替代旧版；入库后明确关联版本。不要并行导入同一清单。
- intent 和 review 交接信息目前保存在内部备注，不能冒充已应用的发布决策。

## 回溯数据

调用 desk_content_history({"package_id":"内容库ID"}) 读取渠道任务、发布操作、版本批注及人工补记的策划、评价、数据。数据必须注明来源与统计时间；当前没有自动抓取平台统计。

## 完成回执

返回批次名、入库数量、内容库 ID、缺失封面及未完成项。不得把“入库成功”写成“发布成功”。

## 素材来源与未来编辑器回溯

来源记录绑定实际 `video_id`。在入库完成后调用 POST `/api/packages/<id>/provenance`：

```json
{"video_id":"成片素材ID","render_revision":"r1","sources":[{"id":"source-1","path":"/原片路径.mp4","duration_ms":3600000}],"segments":[{"source_id":"source-1","source_start_ms":120000,"source_end_ms":150000,"output_start_ms":0,"output_end_ms":30000}]}
```

时间码必须来自实际剪辑工程，不能根据标题推断。剪辑顺序由 output_start_ms 表达，支持从同一原片取多段和多原片组合。

ReelMind 后续对接预留工程身份（project_id）、工程版本（project_revision）、时间线/片段ID，以及编辑器定位链接。只有存在可用工程与定位能力时才显示“返回编辑器微调”；当前不生成虚构工程链接。
