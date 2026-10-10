"""Read-only, dependency-free checks for explicit millisecond edit plans."""
import hashlib
import json

def check_plan(plan):
    errors, warnings = [], []
    if not isinstance(plan, dict):
        return {'success': False, 'errors': ['方案必须是对象'], 'warnings': []}
    sources, segments = plan.get('sources'), plan.get('segments')
    if not isinstance(sources, list) or not isinstance(segments, list) or not segments or len(segments) > 2000:
        return {'success': False, 'errors': ['必须提供 sources 和 1–2000 条 segments'], 'warnings': []}
    durations = {}
    for i, source in enumerate(sources):
        if not isinstance(source, dict):
            errors.append('原片 %s 格式错误' % i); continue
        sid, duration = source.get('id'), source.get('duration_ms')
        if not isinstance(sid, str) or not sid or sid in durations:
            errors.append('原片 ID 缺失或重复'); continue
        if type(duration) is not int or duration <= 0:
            errors.append('原片 %s 必须提供正整数 duration_ms' % sid); continue
        durations[sid] = duration
    cursor, seen = 0, set()
    for i, segment in enumerate(segments):
        label = '片段 %s' % (i + 1)
        if not isinstance(segment, dict):
            errors.append(label + ' 格式错误'); continue
        sid = segment.get('source_id')
        if not isinstance(sid, str) or sid not in durations:
            errors.append(label + ' 引用了未声明原片'); continue
        values = [segment.get(k) for k in ['source_start_ms','source_end_ms','output_start_ms','output_end_ms']]
        if any(type(v) is not int for v in values):
            errors.append(label + ' 时间必须为整数毫秒'); continue
        a, b, x, y = values
        if not 0 <= a < b <= durations[sid]: errors.append(label + ' 原片区间越界或为空')
        if not 0 <= x < y: errors.append(label + ' 输出区间无效')
        if x != cursor: errors.append(label + ' 输出时间轴有空隙、重叠或顺序错误')
        if b-a != y-x: errors.append(label + ' 原片与输出时长不同；当前检查仅支持原速硬切')
        key = (sid, a, b)
        if key in seen: warnings.append(label + ' 重复使用同一区间，请确认是否有意重复')
        seen.add(key); cursor = y
    fingerprint = hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False, separators=(',',':')).encode()).hexdigest()
    return {'success': not errors, 'scope': 'normal-speed-hard-cuts', 'errors': errors, 'warnings': warnings,
            'duration_ms': cursor, 'segments': len(segments), 'plan_fingerprint': fingerprint,
            'semantic_review': 'not_performed', 'audio_visual_review': 'not_performed', 'modified': False}
