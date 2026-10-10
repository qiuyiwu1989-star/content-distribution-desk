# 片序模板编辑器：Codex 接口

页面：`/static/layout-editor/index.html?base=T01`，已保存模板用 `?id=<id>`。

读取 `GET /api/layouts`、`GET /api/layouts/<id>`。
新建 `POST /api/layouts`，请求 `{ "document": {...} }`。
保存 `PUT /api/layouts/<id>`，请求 `{ "revision": 读取的版本, "document": {...} }`。
写请求需 `X-Desk-Token`，从本机首页 `meta[name=desk-token]` 读取，勿记录或公开令牌。仅供本机。

文档 schema 为 `desk-layout.v1`，含 `name`、`base`（T01–T12）、`layers` 数组；数组顺序为从底到顶。
每层有稳定 `id`，`kind` 为 `source/text/subtitle/image`。
`source` 的 `index` 对应原始 SVG 顶层非 defs 元素顺序，`x/y` 为相对原始图层位置的像素偏移，`scale` 为缩放。
新增层 `x/y` 是左上位置，文字按顶部对齐；`image` 的 `width/height` 为边框，图片保持比例。
文字属性 `text`（换行符分行）、`font`（字体库 ID）、`fontSize`、`weight`、`fill`（#RRGGBB）。通用 `opacity`（0–1）、`hidden`。
图片 `src` 只接受 `/api/brand-assets/<id>/file` 或 `/static/creative/logos/<filename>.png|svg`。
字体 ID：smiley-sans、harmonyos-sans、alimama-shuhei、alibaba-puhuiti、source-han-sans、source-han-serif。

先读取模板，按稳定图层 ID 修改，再携带原 revision 保存。409 表示他人已经修改，必须重新读取并合并。每次保存保留历史版本。
不传入 HTML、脚本或任意外网地址。字幕层控制静态样式，不包含时间轴。原视频窗口是样张图片，当前不渲染视频。
导出的 SVG 嵌入字体与图片；JSON 保留素材库引用，应连同素材库备份。SVG 仍为文字对象，第三方编辑器对嵌入字体支持可能不同。
