# -*- coding: utf-8 -*-
"""CBL 第一目标形式：JSON 组装计划（中间表示 IR）。

翻译链：源文件 → Token 序列 → AST → 语义检查 → JSON 计划。
JSON 计划是引擎无关的：预算执行引擎（engine.py）只消费这份数据，
这样编译器和运行期可以独立演化。
"""
from .ast_nodes import Program, Operand


def _operand_json(op: Operand):
    if op.kind == "int":
        return op.value
    if op.kind == "percent":
        return {"percent": op.value}
    return {"window_scale": op.value}


def to_ir(prog: Program) -> dict:
    return {
        "window": prog.window.tokens,
        "margin": prog.window.margin,
        "blocks": [
            {
                "name": b.name,
                "source": b.source,
                "source_kind": b.source_kind,   # 引擎据此决定读文件还是取内置来源
                "cap": b.cap,
                "priority": b.priority,
                "overflow": b.overflow,
                "keep_recent": b.keep_recent,
            }
            for b in prog.blocks
        ],
        "rules": [
            {
                "name": r.name,
                "assert": f"{r.metric} {r.op} {_fmt_operand(r.operand)}",
                "metric": r.metric,             # 引擎求值用，免得再解析 assert 原文
                "op": r.op,
                "operand": _operand_json(r.operand),
                "on_violation": r.on_violation,
            }
            for r in prog.rules
        ],
    }


def _fmt_operand(op: Operand) -> str:
    if op.kind == "int":
        return str(op.value)
    if op.kind == "percent":
        return f"{op.value}%"
    return f"window * {op.value:g}"   # 与源码写法一致，计划书 JSON 示例照此
