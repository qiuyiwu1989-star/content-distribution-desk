# Agent 统一接入

## 当前入口

- 工作台：http://127.0.0.1:4318/#skill-center → Agent 接入。
- HTTP 开工入口：GET /api/agent/bootstrap。
- 只读自检：GET /api/agent/preflight?skills=course-video-editing。
- MCP 服务名称：content-desk；启动命令为本项目 .venv/bin/python 加 mcp/desk_mcp.py 的绝对路径。
- 共同规范：技能 platform-onboarding，正文为 skills/platform-onboarding/SKILL.md，通过技能中心版本历史审计。

平台是资源、标准和经验中心；不同 Agent 独立处理内容，不要求共同接单。本轮不引入抢任务、租约或自动发布。

## Agent 开工顺序

1. desk_agent_bootstrap 获取规范、资源目录及技能清单。
2. desk_agent_preflight 显式传 skill_ids，查看可用性、指纹及 Markdown 链接发现的依赖候选。
3. desk_read_skill 读取所需技能与参考正文；依赖发现不完整，不代替实际加载。
4. find_brand_assets 检索品牌资源，desk_find_cases / desk_read_case 检索和读取 oral / excellent 案例。
5. 核对项目当前版本及用户决定，在执行电脑验证所需工具；再执行本次获授权的工作。
6. 交付与回流遵守共同规范。既有内容记录、口语案例 HTTP 接口和技能审计接口继续使用；没有新增自动推广规则或发布授权。

自检只证明平台侧资源可读：execution_ready=null、media_review=not_performed。不会运行渲染、ASR、媒体听看，不写内容库。现有 /api/skills 接口可能登记技能审计观察，此行为与纯自检分开。

## 两端固定配置

Codex：在 ~/.codex/config.toml 注册 mcp_servers.content-desk。
Harness：在 ~/.dsh/profiles/desktop/cordis.patch.yml 注册 @deepseek-ai/dsh-mcp-client，serverName=content-desk。使用产品支持的配置，不修改应用包。
两端均指向同一 MCP 脚本。MCP initialize 返回简短 instructions，要求相关创作任务先读取平台；业务正文仍按需读取。
共享轻量入口为 ~/.agents/skills/content-workbench/SKILL.md，Codex 对应目录是指向它的链接。Codex 的旧 experience-summary 入口改为读取平台正本，旧 references 保留历史用途，不再作为当前规则。

配置写入不等于已打开的每个会话自动加载。先在新会话检查 content-desk 工具；未出现时在空闲时重载 MCP 或重启客户端，不中断正在执行的任务。不能将裸 stdio 协议测试描述为已经完成两个模型的新会话行为验收。

## 边界与迁移

当前是本机 stdio → 本机 HTTP，不能把另一台电脑的 localhost 当作这台机器。远程访问、用户认证与权限隔离未建设；不能直接开放本机服务端口到公网。
平台文件有本机绝对路径，尚未完成跨机器资源存储迁移。现有 MCP 包含之前已有的受授权写工具；共同规范是行为约束，并非新增权限沙箱。
旧剪辑引擎的词表自动删词未在本轮改造；自检将其列为使用前须核对的风险，不能宣称同步 skill 已统一剪辑效果。

## 验证

运行 .venv/bin/python -m unittest discover -s tests -p 'test_agent_onboarding.py' -v。
验收新会话可输入：

> 先只读接入我的创作工作台：读取共同规范，为课程原声剪辑检查相关资源和版本，说明尚需核实的工具及听审条件。不制作、不入库、不发布。

合格表现是实际调用 bootstrap / preflight，引用返回版本，说明 execution_ready 未验证；不能只复述提示词就报告接入成功。
