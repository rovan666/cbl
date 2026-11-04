# -*- coding: utf-8 -*-
"""教程站演示数据生成器：用真实编译器/引擎跑出 data.js，保证教程与代码永不脱节。

生成内容（供 docs/tutorial 各课页面内嵌使用）：
  tokens_demo     两段源码的完整 Token 流（词法课步进动画）
  ast_demo        一个迷你程序的 AST 结构（语法课可折叠树）
  diag_demo       故意写错的程序及其真实诊断输出（语义课）
  engine_scenes   医疗示例在 B=7200 / 6000 / 1700 下的审计记录（引擎课）
  strategy_demos  同一材料分别触发四种非 error 策略的前后对比（引擎课）
  relative_cap    相对 cap（40% / window*0.4）的编译结果（语法课）

用法（cbl 目录下）：python docs/tutorial/build_data.py
改动了编译器行为后重跑本脚本即可让教程数据同步更新。
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from cbl.lexer import tokenize
from cbl.parser import parse, ParseErrors
from cbl.semantic import check
from cbl.ir import to_ir
from cbl.engine import (AssemblyError, Context, assemble_parts, estimate_tokens,
                        rule_summary, STRATEGIES)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "assets", "data.js")


def tokens_of(src):
    return [{"kind": t.kind, "value": t.value, "line": t.line, "col": t.col}
            for t in tokenize(src)]


def ast_of(node):
    from cbl.ast_nodes import WindowDecl, BlockDecl, RuleDecl
    if isinstance(node, WindowDecl):
        return {"label": "WindowDecl", "line": node.line,
                "detail": f"tokens={node.tokens} margin={node.margin}"}
    if isinstance(node, BlockDecl):
        return {"label": f"BlockDecl «{node.name}»", "line": node.line,
                "detail": (f"source={node.source!r} cap={node.cap} "
                           f"priority={node.priority} overflow={node.overflow}"
                           + (f" keep_recent={node.keep_recent}" if node.keep_recent else ""))}
    if isinstance(node, RuleDecl):
        from cbl.ir import _fmt_operand
        return {"label": f"RuleDecl «{node.name}»", "line": node.line,
                "detail": f"{node.metric} {node.op} {_fmt_operand(node.operand)} → {node.on_violation}"}
    return {"label": repr(node)}


def ast_node(node):
    return {"label": "Program",
            "children": ([("window", ast_of(node.window))] if node.window else [])
                        + [("block", ast_of(b)) for b in node.blocks]
                        + [("rule", ast_of(r)) for r in node.rules]}


MINI = '''window 8000 ;
block notes {
    source: "profile/allergy.md" ;
    cap: 300 ;
    priority: must_keep ;
}
rule keep_enough {
    assert: every_block_min_tokens >= 100 ;
    on_violation: warn ;
}
'''

BAD_SRC = '''window 8000 ;
block allergy_notes {
    source: "profile/allergy.md" ;
    cap: 300 ;
    priority: must_keep ;
    overflow: truncate_tail ;
}
block chat_history {
    source: chat_log ;
    cap: 3000 ;
    overflow: truncate_tail ;
    keep_recent: 4 ;
}
'''

SYNTAX_BAD = '''window 8000 ;
block a { source: "a.txt" ; cap: 100 }
block b { source: "b.txt" ; cap: ; }
'''


def run_scene(budget):
    from cbl.cli import compile_file
    ir, _ = compile_file(os.path.join(ROOT, "examples", "medical_assistant.cbl"))
    ctx = Context.from_dir(os.path.join(ROOT, "examples", "materials"), budget=budget)
    try:
        _, audit = assemble_parts(ir, ctx)
    except AssemblyError as e:
        audit = e.audit
    return audit


def strategy_demo():
    """同一份对话材料，四种策略各自的产出（引擎课对照表）。"""
    turns = [f"用户：第{i}个问题，关于最近症状的描述。\n助手：第{i}个回答，给出了具体建议。"
             for i in range(1, 7)]
    limit = 120
    out = {}
    for name in ("truncate_tail", "sliding_window", "summarize", "rerank_drop"):
        block = {"name": "demo", "keep_recent": 2}
        text, detail = STRATEGIES[name](turns, "\n", limit, block,
                                        Context(query="第5个问题"), estimate_tokens, rule_summary)
        out[name] = {"detail": detail, "text": text, "tokens": estimate_tokens(text)}
    return {"units": turns, "limit": limit, "results": out}


def main():
    data = {}
    data["tokens_demo"] = [
        {"src": "window 8000 ;", "tokens": tokens_of("window 8000 ;")},
        {"src": 'block allergy_notes {\n    source: "profile/allergy.md" ;\n    cap: 300 ;\n}',
         "tokens": tokens_of('block allergy_notes {\n    source: "profile/allergy.md" ;\n    cap: 300 ;\n}')},
    ]
    data["ast_demo"] = {"src": MINI, "tree": ast_node(parse(tokenize(MINI)))}
    diags = check(parse(tokenize(BAD_SRC)))
    data["diag_demo"] = {"src": BAD_SRC,
                         "diags": [{"level": d.level, "line": d.line, "code": d.code,
                                    "text": repr(d)} for d in diags]}
    try:
        parse(tokenize(SYNTAX_BAD))
    except ParseErrors as e:
        data["syntax_recovery"] = {"src": SYNTAX_BAD,
                                   "errors": [{"line": x.line, "col": x.col, "text": str(x)}
                                              for x in e.errors]}
    data["engine_scenes"] = {str(b): run_scene(b) for b in (7200, 6000, 1700)}
    data["strategy_demos"] = strategy_demo()
    rel = {}
    for label, src in [("percent", 'window 8000 ;\nblock a { source: "a.txt" ; cap: 40% ; }'),
                       ("scale", 'window 8000 ;\nblock a { source: "a.txt" ; cap: window * 0.4 ; }')]:
        ir = to_ir(parse(tokenize(src)))
        rel[label] = {"src": src, "cap": ir["blocks"][0]["cap"]}
    data["relative_cap"] = rel

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("// 本文件由 docs/tutorial/build_data.py 用真实编译器生成，请勿手改；"
                "改了编译器行为后重跑该脚本即可。\n")
        f.write("window.TUTORIAL_DATA = ")
        f.write(json.dumps(data, ensure_ascii=False, indent=1))
        f.write(";\n")
    print("written:", OUT, f"({os.path.getsize(OUT) // 1024} KB)")


if __name__ == "__main__":
    main()
