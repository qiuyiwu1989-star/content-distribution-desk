"""Apply local Channels label and one-shot draft safety fixes to installed SAU."""
import argparse
from pathlib import Path

DRAFT_BRANCH = '''        # Desk: never force-click or resubmit an unconfirmed draft.
        if is_draft:
            button = page.get_by_role("button", name="保存草稿", exact=True).first
            await button.wait_for(state="visible", timeout=60000)
            if not await button.is_enabled():
                await self.desk_draft_diagnostic(page, "disabled", False)
                raise RuntimeError("保存草稿按钮不可用，请检查视频上传和必填项；未提交")
            await button.click(timeout=10000)
            # A navigation alone does not prove that a draft was persisted.
            for _ in range(30):
                for message in ("草稿保存成功", "保存草稿成功", "已保存草稿"):
                    confirmation = page.get_by_text(message, exact=True).first
                    if await confirmation.count() and await confirmation.is_visible():
                        tencent_logger.success("平台显示草稿保存成功；仍需核对草稿列表")
                        return
                await asyncio.sleep(1)
            await self.desk_draft_diagnostic(page, "unconfirmed", True)
            raise RuntimeError("已点击一次保存草稿，未获得明确保存提示；请核对草稿列表，禁止直接重试")
'''

DIAGNOSTIC_METHOD = '''    async def desk_draft_diagnostic(self, page, reason, submitted):
        # Private local evidence only; never store cookies or the full page.
        target = os.environ.get("DESK_DRAFT_DIAGNOSTIC")
        if not target:
            return
        import json
        alerts = []
        for selector in ("[role=alert]", ".weui-desktop-toast", ".weui-desktop-form__tips"):
            try:
                locator = page.locator(selector)
                for index in range(min(await locator.count(), 8)):
                    item = locator.nth(index)
                    if await item.is_visible():
                        alerts.append((await item.inner_text())[:300])
            except Exception:
                pass
        diagnostic = {"schema": "desk.channels-draft-diagnostic.v1",
                      "reason": reason, "submitted": submitted, "alerts": alerts}
        path = Path(target)
        path.write_text(json.dumps(diagnostic, ensure_ascii=False, indent=2))
        os.chmod(path, 0o600)

'''

def patch(path):
    text = path.read_text()
    original = text
    text = text.replace('getattr(self, "content_label", None) or "含AI生成内容"', 'getattr(self, "content_label", None) or "个人观点"')
    start = text.find('        # 视频号「视频标注」下拉：')
    if start != -1:
        end = text.index('        label_text =', start)
        text = text[:start] + '        # 视频标注默认采用用户指定的「个人观点」；与声明原创是独立字段。\n' + text[end:]
    text = text.replace('tencent_logger.info(_msg("🧾", "当前页面未发现「视频标注」入口，跳过标注继续发布"))\n                return', 'raise RuntimeError("未发现视频标注入口，无法确认个人观点；未提交")')
    text = text.replace('tencent_logger.warning(_msg("😵", f"设置视频标注「{label_text}」失败，跳过继续发布：{exc}"))', 'raise RuntimeError(f"设置视频标注「{label_text}」失败；未提交") from exc')
    marker = '        is_draft = getattr(self, "is_draft", False)\n'
    if '# Desk: never force-click' not in text:
        assert text.count(marker) == 1, 'Unexpected upstream layout; patch stopped'
        text = text.replace(marker, marker + DRAFT_BRANCH, 1)
    if 'async def desk_draft_diagnostic' not in text:
        text = text.replace('    async def submit_publish(self, page: Page)', DIAGNOSTIC_METHOD + '    async def submit_publish(self, page: Page)', 1)
    # Upgrade an earlier local one-shot branch as well as clean upstream copies.
    begin = text.index('        # Desk: never force-click')
    end = text.index('        # 先等待并清理', begin)
    text = text[:begin] + DRAFT_BRANCH + text[end:]
    compile(text, str(path), 'exec')
    if text != original:
        backup = path.with_suffix('.py.before-desk-draft-fix')
        if not backup.exists(): backup.write_text(original)
        path.write_text(text)
    return text != original

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path, help='social-auto-upload root')
    args = parser.parse_args()
    print('updated' if patch(args.root/'uploader/tencent_uploader/main.py') else 'already patched')
