# -*- coding: utf-8 -*-
"""CBL 审计报告：把引擎产出的审计记录渲染成可存档的报告。

审计记录本身就是 JSON 主格式（render_json）；纯文本视图用于课堂演示，
格式与计划书第 5 节示例一致；HTML 视图供正式报告使用——它与网页演示共用
static/report.js 渲染器，两边的视觉永远一致。

负责人：祝梦倩
"""
import datetime
import json
import os

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def render_json(audit: dict) -> str:
    return json.dumps(audit, ensure_ascii=False, indent=2)


NEGATE = {"<=": ">", ">=": "<"}


def _fmt_rule(r):
    bound = f"{r['bound']:g}"
    op = r["op"] if r["passed"] else NEGATE[r["op"]]     # 违例时写实际关系：0 < 100
    if r["metric"] == "every_block_min_tokens":
        value = f"最小有效额度 {r['actual']} {op} {bound}"
    else:
        value = f"{r['actual']} {op} {bound}"
    if r["passed"]:
        return "通过", value
    if r["where"]:
        value += f"：{r['where']}"
    return ("违例" if r["level"] == "error" else "警告"), value


def render_text(audit: dict) -> str:
    """纯文本审计报告，例如：
        === CBL 组装审计报告 ===  window=8000  可用=7200  占用=6744 (84.3%)
        [must_keep] system_prompt  cap=1500 used=1432 完整保留
        [high]      retrieved_docs cap=3200 used=3126 原始 5100
                    -> rerank_drop 丢弃相关度最低的 2 段
    """
    w, blocks = audit["window"], audit["blocks"]
    pct = audit["total_used"] / w * 100
    lines = [f"=== CBL 组装审计报告 ===  window={w}  可用={audit['budget']}  "
             f"占用={audit['total_used']} ({pct:.1f}%)"]
    name_w = max((len(b["name"]) for b in blocks), default=0) + 1
    for b in blocks:
        cols = [f"[{b['priority']}]".ljust(12) + b["name"].ljust(name_w), f"cap={b['cap']}".ljust(8)]
        if b["effective"] < b["cap"]:
            cols.append(f"有效={b['effective']}".ljust(8))
        cols.append(f"used={b['used']}".ljust(9))
        act = b["action"]
        if act in ("完整保留", "整块舍弃", "来源缺失"):
            note = f"{act}（{b['detail']}）" if act == "来源缺失" else act
            lines.append(" ".join(cols + [note]))
            continue
        lines.append(" ".join(cols + [f"原始 {b['original']}"]))
        lines.append(" " * 12 + f"-> {act} {b['detail']}")
    if audit["rules"]:
        rw = max(len(r["name"]) for r in audit["rules"]) + 1
        for i, r in enumerate(audit["rules"]):
            verdict, value = _fmt_rule(r)
            head = "规则检查：" if i == 0 else " " * 10
            lines.append(f"{head}{r['name'].ljust(rw)} {verdict} ({value})")
    if audit["status"] == "rejected":
        lines.append(f"!! 组装被拒绝：{audit['error']}")
    return "\n".join(lines)


def _static(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


def _embed_json(obj):
    """可安全放进 <script> 的 JSON：< > & 转义为 \\u 形式，材料里即使有 </script> 也截断不了脚本。"""
    s = json.dumps(obj, ensure_ascii=False)
    return s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def build_html(data: dict) -> str:
    """独立 HTML 审计报告：样式、渲染器、数据全部内嵌，单文件离线可看、可存档、可打印。
    data 为 webui.analyze() 的结果（含审计记录、逐块视图、文本报告、最终 Prompt）。"""
    data = dict(data)
    data.setdefault("generated_at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    a = data["audit"]
    title = f"CBL 审计报告 · B={a['budget']} · {'拒绝组装' if data.get('stage') == 'rejected' else '组装完成'}"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{_static("report.css")}
</style>
</head>
<body class="cbl">
<div class="report" id="app"><noscript>本报告需要启用 JavaScript 显示；原始审计记录见页面源码中的 cbl-data。</noscript></div>
<script type="application/json" id="cbl-data">{_embed_json(data)}</script>
<script>
{_static("report.js")}
</script>
<script>
CBLReport.renderStatic(document.getElementById("app"),
                       JSON.parse(document.getElementById("cbl-data").textContent));
</script>
</body>
</html>
"""


def render_html(data: dict, out_path: str) -> None:
    """把 build_html 的结果写盘。"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(build_html(data))
