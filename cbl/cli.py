# -*- coding: utf-8 -*-
"""CBL 命令行入口。

用法（在 cbl 项目根目录下）：
    python -m cbl check examples/medical_assistant.cbl        # 编译检查 + 输出 JSON 计划
    python -m cbl run   examples/medical_assistant.cbl        # 编译 + 组装，打印审计报告
        [--materials 目录]   材料目录，缺省为 .cbl 同目录下的 materials/
        [--budget N]         本次可用额度 B，缺省 window×margin
        [--query 文本]       本轮用户提问，缺省读材料目录下的 query.txt
        [--out 文件]         最终 Prompt 写入文件
        [--json 文件]        审计记录（JSON）写入文件
        [--html 文件]        独立 HTML 审计报告写入文件
    python -m cbl serve [examples/medical_assistant.cbl]      # 网页演示：预算实验台
        [--materials 目录] [--port 8000] [--lan 局域网访问] [--no-browser]
"""
import argparse
import json
import os
import sys

from .lexer import tokenize, LexError
from .parser import parse, ParseError
from .semantic import check, has_error
from .ir import to_ir
from .engine import Context, AssemblyError, assemble
from .report import render_text, render_json, render_html

DEFAULT_EXAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "examples", "medical_assistant.cbl")


def compile_file(path: str):
    """完整编译链：源码 → Token → AST → 语义检查 → IR。
    返回 (ir, diags)；任何阶段失败抛异常或返回 None。"""
    text = open(path, encoding="utf-8").read()
    tokens = tokenize(text)          # 词法分析
    prog = parse(tokens)             # 语法分析
    diags = check(prog)              # 语义检查
    if has_error(diags):
        return None, diags
    return to_ir(prog), diags        # 生成 JSON 组装计划


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m cbl", description="CBL 上下文预算语言")
    ap.add_argument("cmd", choices=["check", "run", "serve"])
    ap.add_argument("path", nargs="?")
    ap.add_argument("--materials")
    ap.add_argument("--budget", type=int)
    ap.add_argument("--query")
    ap.add_argument("--out")
    ap.add_argument("--json")
    ap.add_argument("--html")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--lan", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    if args.path is None:
        if args.cmd != "serve":
            ap.error(f"{args.cmd} 需要指定 .cbl 文件")
        args.path = DEFAULT_EXAMPLE
    materials = args.materials or os.path.join(os.path.dirname(os.path.abspath(args.path)), "materials")

    if args.cmd == "serve":
        from .webui import serve
        serve(args.path, materials, port=args.port, lan=args.lan, open_browser=not args.no_browser)
        return 0

    try:
        ir, diags = compile_file(args.path)
    except (LexError, ParseError) as e:
        print(e)
        return 1
    for d in diags:
        print(d)
    if ir is None:
        print("编译失败：存在错误级诊断")
        return 1
    if args.cmd == "check":
        print(json.dumps(ir, ensure_ascii=False, indent=2))
        return 0

    ctx = Context.from_dir(materials, query=args.query, budget=args.budget)
    try:
        prompt, audit = assemble(ir, ctx)
        code = 0
    except AssemblyError as e:
        prompt, audit, code = None, e.audit, 1
    print(render_text(audit))
    if args.json:
        _write(args.json, render_json(audit))
    if args.out and prompt is not None:
        _write(args.out, prompt)
        print(f"\n最终 Prompt 已写入 {args.out}")
    if args.html:
        from .webui import analyze
        with open(args.path, encoding="utf-8") as f:
            data = analyze(f.read(), materials, args.budget, args.query)
        data["file"] = os.path.basename(args.path)
        render_html(data, args.html)
        print(f"HTML 审计报告已写入 {args.html}")
    return code


if __name__ == "__main__":
    sys.exit(main())
