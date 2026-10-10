# 技能中心与 Agent 调用

技能正本在 `skill_sources.json` 登记。后端每次读取目录时检查正本与参考资源变化，目录页面每 15 秒检查更新；浏览器无需重新复制技能文件。内容指纹覆盖整个技能目录。技能不可用时显示缺失并拒绝调用，不以旧副本替代。

用户从内容详情或技能中心选择技能、内容与要求后创建 Agent 任务。任务固定技能全文、文本参考资源、版本指纹、内容与素材 ID、批次、审核意见及所选制作方案。素材本身沿用本机素材接口，未复制大视频。创建任务不等于开始执行。

MCP 入口：`mcp/desk_mcp.py`，使用已存在的分发台客户端会话校验。

- `desk_list_skills`：读取最新目录。
- `desk_read_skill`：读取技能与参考文件。
- `desk_create_skill_request`：创建任务，传 `skill_id`、`skill_revision`、`package_ids`、`instruction`、唯一 `idempotency_key`。
- `desk_skill_requests`：读取任务列表。
- `desk_skill_request`：按 `request_id` 读取固定快照。
- `desk_update_skill_request`：接单传 `status:running` 与 `worker`；回报传 `completed/failed`、相同 `worker` 与 `summary`。页面明确这是 Agent 回报。

标准任务路径：读取任务 → 接单 → 按快照处理 → 回报结果。当前分发台提供队列和 MCP 接口，未内置运行大模型的进程。用户可复制调用文本交给当前 Agent，或由本机 MCP 客户端接单。

技能更新影响后续调用。已有任务保留原始快照，避免处理中静默换规则。相同重试编号返回原任务；内容或要求不一致时拒绝复用。待接单任务可取消，运行任务只接受接单者回报。任务与制作选择都进入现有 SQLite 完整备份。

增加技能时在配置里登记 `id/label/path/hint`，路径必须是本机可访问的真实正本目录。远程 Agent 需要本机 MCP 或受控远程执行，其 localhost 不等于这台电脑。


## 技能版本与审计（2026-10-09）

技能卡片的“版本历史”显示完整基线、外部变更与受控修改。每次保存包含序号、父版本、完整文件清单、SHA256内容指纹、登记时间、修改者类型和署名、修改原因与可选来源/会话编号。正文与参考文件、二进制资源都按内容寻址保留，重复字节只存一次；不依赖可被覆写的正本来还原旧版。可比较任意两版，下载完整ZIP，检查版本链与资源完整性。

修改者是本机授权客户端的署名声明，不是密码学身份认证；Agent不得冒称用户。通过界面或MCP修改时必须先读取当前revision和audit_head.id，提交时匹配两者。落后版本返回409，不覆盖新内容；发生异常时仅在文件仍等于本次写入时恢复原文。进程崩溃或外部程序并发写入与SQLite不是跨系统事务，恢复后可能登记成未知外部变更，不能承诺绝对原子性。

外部改文件在读取时自动形成新记录，作者标未知。页面打开时每15秒检查，但不是系统级文件监控：两次读取之间多次改写、关闭页面期间未读取的中间状态可能无法逐次捕获。需要完整署名审计的Agent应使用desk_edit_skill，不直接改正本。首次基线不推断旧作者、旧修改时间。可核对的改前备份作为“接入前的修改证据”单独补录，保留前后全文和来源，明确不是完整历史版本。

- GET /api/skills/<id>/history：版本列表与历史补录，正本失效时仍可读已保存历史。
- GET /api/skills/<id>/history/<version-id>?base=<other-id>：指定版本与对比差异，base=empty为与空基线比较。
- GET /api/skills/<id>/history/<version-id>/download：完整快照和审计元数据、该版本关联的历史证据。
- GET /api/skills/<id>/history-integrity：验证版本链、文件指纹与历史证据哈希。
- POST /api/skills/<id>/edit：单个现有文本文件；字段expected_revision、expected_version_id、path、content、actor_type（human/agent）、actor_name、reason、可选source_ref。单文件上限512KB。沿用本机CSRF会话授权。
- POST /api/skills/<id>/history-evidence：受权的历史文本证据补录；修改后全文必须匹配当前版本，补录时间与历史发生时间不混淆。
- MCP新增desk_skill_history、desk_skill_version、desk_edit_skill。先desk_read_skill，后用返回的revision与audit_head.id提交修改；不要在冲突后直接替换版本号重试，应读新内容合并。

审计数据在现有desk.sqlite3的skill_audit_versions、skill_audit_blobs、skill_audit_evidence表中，随原有SQLite备份保存。表有禁止UPDATE/DELETE触发器，应用不提供清历史接口；哈希链可检测普通损坏，不抵抗能修改数据库结构并重算整条链的本机管理员。要达成强防篡改需另行签名或异机保管。本次不提供覆盖历史的回滚操作，也不改变发布库及旧Agent任务快照。
