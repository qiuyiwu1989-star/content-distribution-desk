# MCP 配置与范围

把仓库安装在分发台同一主机。MCP 客户端配置示例（把路径改成实际绝对路径）：

```json
{"mcpServers":{"distribution-desk":{"command":"python3","args":["/absolute/content-distribution-desk/mcp/desk_mcp.py"]}}}
```

支持标准 stdio JSON-RPC：initialize、tools/list、tools/call。首次加载先调用 desk_status 确认接口。

生产批次必须已登记到相邻工作区的 `协作资料/工具/审阅工作台/批次.json`；目前 preview/sync 复用该工作区的导出、导入脚本，**不是独立仓库任意批次通用导入器**。依赖缺失返回失败；不要猜测成功。生产脚本导入时有版本回执保护，但失败可能留下部分入库结果，重试前查看回执。

sync_production_batch 参数：batch、account（必填）、only（可选，逗号分隔）。只创建待完善任务；不批准、排期、登录或公开发布。批次不在登记表时，先按原生产工作台规则登记，不修改别人的运行任务。

跨Agent安装：复制本skill目录到支持SKILL.md的技能目录即可。保持这一份项目skill为主；不要建立多份互相矛盾的经验源。任意标准批次可调用 preview_library_batch / import_library_batch。不发意愿目前保留为交付元数据，界面标签同步仍需扩展。清单示例：

```json
{"batch_name":"课程批次","items":[{"id":"C001","version":"v001","sequence":1,"title":"观点标题","video":"C001.mp4","cover":"C001.png","body":"发布简介","tags":["AI"],"intent":"publish","review":{"listening":"pending"}}]}
```

路径相对清单解析；导入前校验整批，回执与清单同目录保存，失败后复用回执恢复。相同清单和素材跳过已上传项；不同正文或素材形成新包。导入目前将标签、源信息、审核、不发原因保存在内部元数据，不擅自创建发布任务。批次名称应唯一；不要多客户端并发导入同一清单。
