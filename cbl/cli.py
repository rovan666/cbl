# -*- coding: utf-8 -*-
"""CBL 命令行入口。

用法（在 cbl 项目根目录下）：
    python -m cbl check examples/medical_assistant.cbl   # 编译检查 + 输出 JSON 计划
    python -m cbl run   examples/medical_assistant.cbl   # TODO：接执行引擎
"""
import json
import sys

from .lexer import tokenize, LexError
from .parser import parse, ParseError
from .semantic import check, has_error
from .ir import to_ir


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


def main(argv=None):
    argv = argv or sys.argv[1:]
    if len(argv) != 2 or argv[0] not in ("check", "run"):
        print(__doc__)
        return 2
    cmd, path = argv
    try:
        ir, diags = compile_file(path)
    except (LexError, ParseError) as e:
        print(e)
        return 1
    for d in diags:
        print(d)
    if ir is None:
        print("编译失败：存在错误级诊断")
        return 1
    print(json.dumps(ir, ensure_ascii=False, indent=2))
    if cmd == "run":
        print("\n[TODO] 执行引擎尚未实现（杨晨），目前只能生成 JSON 计划")
    return 0


if __name__ == "__main__":
    sys.exit(main())
