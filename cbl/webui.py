# -*- coding: utf-8 -*-
"""CBL 预算实验台：网页演示（计划书加分项）。

浏览器里编辑 .cbl 源码、拖动"可用额度"滑块，实时看到编译诊断、各块的有效额度、
裁剪动作、规则检查，以及"AI 实际看到了什么"。纯标准库，零依赖。

用法：python -m cbl serve [examples/medical_assistant.cbl] [--materials 目录] [--port 8000] [--lan]
页面地址参数：?budget=6000 直接打开某个额度（便于答辩时切换场景、截图存档）。

接口：GET  /              页面
      GET  /static/<文件>  页面与 HTML 报告共用的渲染器（report.js / report.css）
      GET  /api/init       初始源码、提问、材料目录
      POST /api/analyze    {source, budget, query} → 编译 + 组装的全部结果
      POST /api/report     同上参数 → 独立 HTML 审计报告（下载用）

负责人：祝梦倩
"""
import json
import os
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .lexer import tokenize, LexError
from .parser import parse, ParseError
from .semantic import check, has_error
from .ir import to_ir
from .engine import (AssemblyError, BLOCK_SEP, Context, MaterialMissing,
                     assemble_parts, load_material, estimate_tokens)
from .report import render_text, build_html

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_BODY = 256 * 1024            # 请求体上限：源码与提问都很小，防止被塞大包
SUMMARY_TAG = "【早期对话摘要】"
PARTIAL_PROBE = 12               # 判定"部分保留"时比对的首尾字符数


def _unit_status(units, final, action):
    """给每个裁剪单位标状态：kept / partial / summarized / dropped。"""
    if action == "完整保留":
        return ["kept"] * len(units)
    if action in ("整块舍弃", "来源缺失", "error"):
        return ["dropped"] * len(units)
    has_summary = final.startswith(SUMMARY_TAG)
    kept = [u in final for u in units]
    first_kept = next((i for i, k in enumerate(kept) if k), len(units))
    out = []
    for i, u in enumerate(units):
        if kept[i]:
            out.append("kept")
        elif has_summary and i < first_kept:
            # 摘要覆盖保留原文之前的单位；须先于"部分保留"判断——摘要会引用这些单位的首句
            out.append("summarized")
        elif u[:PARTIAL_PROBE] in final or u[-PARTIAL_PROBE:] in final:
            out.append("partial")       # truncate 截掉尾巴、sliding_window 只留末尾
        else:
            out.append("dropped")
    return out


def _views(ir, ctx, parts, actions):
    """逐块视图：原始单位（带状态与用量）、摘要文本、最终文本。"""
    final_by = dict(parts)
    views = []
    for b in ir["blocks"]:
        view = {"name": b["name"], "source": b["source"], "source_kind": b["source_kind"],
                "unit_name": "段", "units": [], "summary": "", "final": final_by.get(b["name"], "")}
        views.append(view)
        try:
            units, sep, unit_name = load_material(b, ctx)
        except MaterialMissing:
            continue
        action = actions.get(b["name"])          # None：拒绝组装时后面的块还没轮到
        view["unit_name"] = unit_name
        status = (_unit_status(units, view["final"], action) if action
                  else ["pending"] * len(units))
        view["units"] = [{"text": u, "tokens": estimate_tokens(u), "status": s}
                         for u, s in zip(units, status)]
        if view["final"].startswith(SUMMARY_TAG):
            view["summary"] = view["final"].split(sep, 1)[0][len(SUMMARY_TAG):]
    return views


def analyze(source, materials, budget=None, query=None):
    """一次完整的编译 + 组装。返回页面所需全部数据（均可 JSON 序列化）。
    stage：lex / syntax / semantic（编译失败停在哪一步）/ rejected（拒绝组装）/ ok。"""
    res = {"stage": "ok", "error": None, "diags": [], "ir": None, "audit": None,
           "blocks": [], "prompt": "", "report_text": "", "query": ""}
    try:
        prog = parse(tokenize(source))
    except (LexError, ParseError) as e:
        res.update(stage="lex" if isinstance(e, LexError) else "syntax",
                   error={"line": e.line, "message": str(e)})
        return res
    diags = check(prog)
    res["diags"] = [{"level": d.level, "line": d.line, "code": d.code, "message": d.msg,
                     "text": repr(d)} for d in diags]
    if has_error(diags):
        res["stage"] = "semantic"
        return res
    ir = to_ir(prog)
    res["ir"] = ir
    ctx = Context.from_dir(materials, query=query, budget=budget)
    res["query"] = ctx.query
    try:
        parts, audit = assemble_parts(ir, ctx)
    except AssemblyError as e:
        parts, audit = [], e.audit
        res["stage"] = "rejected"
    res["audit"] = audit
    res["report_text"] = render_text(audit)
    res["prompt"] = BLOCK_SEP.join(t for _, t in parts if t)
    # 拒绝组装时没有任何内容送入模型：所有单位标 pending，避免把前面的块误显示为"保留"
    actions = ({} if res["stage"] == "rejected"
               else {a["name"]: a["action"] for a in audit["blocks"]})
    res["blocks"] = _views(ir, ctx, parts, actions)
    return res


# ---------- HTTP 服务 ----------

def make_handler(default_path, materials):
    with open(default_path, encoding="utf-8") as f:
        default_source = f.read()
    init = {"source": default_source, "file": os.path.basename(default_path),
            "materials": os.path.relpath(materials), "query": Context.from_dir(materials).query}

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, data, ctype):
            body = data.encode("utf-8") if isinstance(data, str) else data
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                return self._static("demo.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if path == "/api/init":
                return self._json(init)
            self._send(404, "not found", "text/plain; charset=utf-8")

        def _static(self, name):
            if "/" in name or "\\" in name or name.startswith("."):
                return self._send(404, "not found", "text/plain; charset=utf-8")
            fp = os.path.join(STATIC, name)
            if not os.path.isfile(fp):
                return self._send(404, "not found", "text/plain; charset=utf-8")
            ctype = {"html": "text/html", "js": "application/javascript",
                     "css": "text/css"}.get(name.rsplit(".", 1)[-1], "application/octet-stream")
            with open(fp, "rb") as f:
                self._send(200, f.read(), ctype + "; charset=utf-8")

        def _body(self, n):
            req = json.loads(self.rfile.read(n) or b"{}")
            budget = req.get("budget")
            budget = int(budget) if budget not in (None, "") else None
            if budget is not None and not 0 <= budget <= 10 ** 7:
                raise ValueError("budget 超出合理范围")
            return str(req.get("source", "")), budget, req.get("query")

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if path not in ("/api/analyze", "/api/report"):
                return self._send(404, "not found", "text/plain; charset=utf-8")
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._json({"error": "请求无效：Content-Length 不是整数"}, 400)
            if n > MAX_BODY:                  # 只看请求头就拒绝，不读请求体
                self.close_connection = True
                return self._json({"error": f"请求体过大（上限 {MAX_BODY} 字节）"}, 413)
            try:
                source, budget, query = self._body(n)
            except (ValueError, TypeError) as e:
                return self._json({"error": f"请求无效：{e}"}, 400)
            res = analyze(source, materials, budget, query)
            if path == "/api/analyze":
                return self._json(res)
            if res["audit"] is None:
                return self._json({"error": "编译未通过，无法生成报告"}, 400)
            res["file"] = init["file"]
            self._send(200, build_html(res), "text/html; charset=utf-8")

        def log_message(self, *args):     # 静默：演示时终端不刷屏
            pass

    return Handler


def _lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))       # 不真正发包，只为取出本机局域网地址
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def serve(path, materials, port=8000, lan=False, open_browser=True):
    host = "0.0.0.0" if lan else "127.0.0.1"
    server = ThreadingHTTPServer((host, port), make_handler(path, materials))
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"CBL 预算实验台已启动：{url}")
    if lan:
        print(f"局域网模式：同一 Wi-Fi 下的手机/电脑打开 http://{_lan_ip()}:{server.server_port}")
    print("关闭：在终端按 Ctrl+C")
    if open_browser:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已关闭")
    finally:
        server.server_close()
