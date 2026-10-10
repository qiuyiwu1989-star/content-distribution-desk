"""Read-only onboarding: current canonical resources, explicit scope and honest gaps."""
import re
from pathlib import Path
from urllib.parse import unquote
from flask import jsonify, request


INSTRUCTIONS = ('创作任务以内容分发台为共同资源与标准中心，Codex/Harness 为执行入口。'
                '开始课程剪辑、封面、文案或经验整理前，先调用 desk_agent_bootstrap，'
                '再按任务调用 desk_agent_preflight 并读取相关技能与资源。'
                '不要求多 Agent 协同接单；不把接口自检当作听审，不把入库当发布授权。'
                '平台不可达时明确报告，不以旧副本冒充当前规则。')

RESOURCES = [
    dict(id='skills', label='技能正本与版本', url='/api/skills'),
    dict(id='oral-cases', label='个人口语案例', url='/api/oral-cases', query='q'),
    dict(id='brand-assets', label='品牌与个人素材', url='/api/brand-assets', query='q'),
    dict(id='excellent-cases', label='优秀案例', url='/api/excellent-cases', query='q'),
    dict(id='cover-templates', label='封面模板', url='/api/cover-design/catalog'),
    dict(id='library', label='内容与批次', url='/api/library'),
]


def summarize(value):
    return {k: value.get(k) for k in ('id', 'label', 'available', 'revision', 'version', 'error')}


def inspect_skills(catalog, ids):
    rows = catalog.rows()
    roots = {(Path(x['path']).expanduser().resolve() / 'SKILL.md'): x['id'] for x in rows}
    pending, found, missing = list(ids), {}, []
    while pending:
        sid = pending.pop(0)
        if sid in found or sid in missing:
            continue
        try:
            value = catalog.read(sid)
        except KeyError:
            missing.append(sid)
            continue
        found[sid] = summarize(value)
        if not value['available']:
            continue
        root = Path(value['source_path']).parent
        dependencies = set()
        # Only registered local SKILL.md links; never fetch URLs or execute references.
        for rel, text in value.get('supporting_texts', {}).items():
            if not rel.endswith('.md'):
                continue
            for target in re.findall(r'\]\(([^)]+)\)', text):
                target = unquote(target.split('#', 1)[0].strip('<>'))
                if '://' in target or not target.endswith('SKILL.md'):
                    continue
                dep = roots.get(((root / rel).parent / target).resolve())
                if dep and dep != sid:
                    dependencies.add(dep)
        found[sid]['linked_skill_ids'] = sorted(dependencies)
        pending.extend(sorted(dependencies))
    return list(found.values()), missing


def install(app, catalog, fail):
    def policy():
        try:
            value = catalog.read('platform-onboarding')
        except KeyError:
            fail('平台接入规范尚未登记', 503)
        if not value['available']:
            fail('平台接入规范正本不可用', 503)
        return value

    @app.get('/api/agent/bootstrap')
    def agent_bootstrap():
        value = policy()
        return jsonify(schema='desk.agent-bootstrap.v1', policy={**summarize(value), 'content': value['content'],
                       'url': '/api/skills/platform-onboarding'}, instructions=INSTRUCTIONS,
                       resources=RESOURCES, skills=[summarize(catalog.read(x['id'])) for x in catalog.rows()],
                       limits=['本机接入；未启用远程网络', '资源目录不代表已读取资料或已验证媒体',
                               '各 Agent 独立处理内容；无强制共同接单'],
                       preflight_url='/api/agent/preflight', read_only=True)

    @app.get('/api/agent/preflight')
    def agent_preflight():
        value = policy()
        ids = [s.strip() for s in request.args.get('skills', '').split(',') if s.strip()]
        if len(ids) > 32 or any(not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', x) for x in ids):
            fail('技能 ID 无效或超过 32 个', 400)
        skills, missing = inspect_skills(catalog, ids)
        unavailable = [s['id'] for s in skills if not s['available']]
        ready = bool(ids) and not missing and not unavailable
        return jsonify(schema='desk.agent-preflight.v1', read_only=True,
                       scope='platform-resource-availability-only', requested_skill_ids=ids,
                       policy_revision=value['revision'], skills=skills, missing=missing,
                       unavailable=unavailable, resource_status='ready' if ready else 'needs_attention',
                       execution_ready=None, media_review='not_performed',
                       checks_remaining=['按任务实际读取返回技能及参考资料', '核对素材、用户决定和当前版本',
                                         '在执行电脑验证渲染、ASR、音视频感知工具', '核对旧引擎自动删词与逐句判断的冲突'],
                       dependency_discovery='registered-local-markdown-links; not a complete execution graph')
