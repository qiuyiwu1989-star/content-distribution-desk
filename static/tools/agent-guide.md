# 片序工具中心 v0.3

目录：/static/tools/catalog.json。目录中的 available 表示已有调用入口，不表示当前宿主已连接或真实业务已验收。adapter_pending 不得作为已接通工具调用。

## 片序 MCP

先读取 /api/agent-import-info 获取本机实际启动配置。在宿主配置该 stdio MCP 后查询 tools/list，使用其真实 inputSchema，不猜参数。

- preview_library_batch：只读预检批次 manifest_path。
- import_library_batch：预检通过后导入；保持批次稳定身份，不自动发布。
- find_brand_assets：按 q/category 查询，遵循使用备注。
- desk_content_history：package_id 对应内容历史。
- desk_add_content_record：package_id、kind、author、note，可选 url；不修改审核和发布状态。

批次完整规范：/static/agent-import.md。

## ReelMind 待接入

ReelMind 全文资源检索、画面预览与交付检查暂为能力目录。实现来源包括远端 function-calling 1842c9b 与本机开发代码，两者不可互换。接入需固定工具版本、工程身份、输入输出、权限与真实验证证据。不要启动生产服务、读取其他账号或重复收费转录来完成接入。

统一结果应区分完成、失败、部分完成、结果未知，返回来源与版本引用。生成成片不等于人工审阅通过，登记记录不等于操作平台发布。

## 新增只读工具

desk_source_provenance 输入 package_id、video_id，返回已登记来源，不推断缺失记录。

desk_check_edit_plan 输入 plan，sources 每项 id/duration_ms；segments 每项 source_id/source_start_ms/source_end_ms/output_start_ms/output_end_ms。所有时间为整数毫秒，输出从零连续排列，当前仅支持原速硬切。success=false 时检查 errors；warnings 需要判断。指纹只对应输入方案，不证明媒体版本一致。

示例：
```json
{"plan":{"sources":[{"id":"s1","duration_ms":60000}],"segments":[{"source_id":"s1","source_start_ms":10000,"source_end_ms":15000,"output_start_ms":0,"output_end_ms":5000}]}}
```

画面预览与交付检查仍待接入；原片全文检索尚未接入。


## 接入与验证分别记录

目录 integration.state=entry_declared 只表示声明了调用入口；host_connection=unknown 表示工具中心没有检测当前 Agent 宿主连接。调用前查询宿主 tools/list 确认真实工具可用。

validation.state=not_recorded 表示目录没有绑定当前工具版本的验证证据，不等同于验证失败，也不否定此前局部测试。不要据此报告“已连接”或“已验收”。后续验证记录应注明工具版本、验证范围、输入引用、结果引用与时间，静态检查、真实执行和人工审阅分别记录。

剪辑方案检查的指纹对应输入 JSON。它不检查工程版本、媒体文件哈希，也不测量原片真实时长；sources.duration_ms 是调用者提供的声明。
