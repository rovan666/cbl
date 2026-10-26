# -*- coding: utf-8 -*-
"""CBL 自检脚本：编译前端（lexer → parser → semantic → IR）+ 执行引擎与审计报告。

用法（项目根目录）：python tests/run_tests.py
引擎用例在 tests/engine_cases.py，这里统一收集运行。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cbl.cli import compile_file
from cbl.lexer import LexError
from cbl.parser import ParseError
from cbl.semantic import CATALOG, check, has_error
from cbl.ast_nodes import Program, WindowDecl, BlockDecl, RuleDecl, Operand

sys.path.insert(0, os.path.dirname(__file__))
from engine_cases import *  # noqa: E402,F401,F403  引擎用例（case_ 开头）一并收集
from webui_cases import *   # noqa: E402,F401,F403  网页演示与 HTML 报告用例

ROOT = os.path.join(os.path.dirname(__file__), "..")
results = []


def run_case(name, fn):
    try:
        fn()
        results.append((name, True, ""))
    except AssertionError as e:
        results.append((name, False, str(e)))
    except Exception as e:
        results.append((name, False, f"意外异常 {type(e).__name__}: {e}"))


def case_example_ok():
    ir, diags = compile_file(os.path.join(ROOT, "examples", "medical_assistant.cbl"))
    assert ir is not None, "示例应编译成功：" + repr(diags)
    assert ir["window"] == 8000
    assert len(ir["blocks"]) == 5, "应有 5 个块"
    assert len(ir["rules"]) == 2, "应有 2 条规则"
    names = [b["name"] for b in ir["blocks"]]
    assert names == ["system_prompt", "allergy_notes", "retrieved_docs",
                     "chat_history", "tool_output"], names
    assert ir["rules"][0]["assert"] == "total_reserved <= window * 0.9", ir["rules"][0]
    assert not diags, f"示例不应有任何诊断：{diags}"


def _compile_text(src):
    with tempfile.NamedTemporaryFile("w", suffix=".cbl", delete=False,
                                     encoding="utf-8") as f:
        f.write(src)
        path = f.name
    try:
        return compile_file(path)
    finally:
        os.unlink(path)


def case_syntax_error():
    try:
        _compile_text("window 8000\nblock a { cap: 100 ; }")  # window 少分号
        raise AssertionError("缺少分号应报语法错误")
    except ParseError as e:
        assert "行" in str(e), "错误信息应带行号"


def case_lex_error():
    try:
        _compile_text("window 8000 ;\nblock a { cap: 100 ; source: @ ; }")
        raise AssertionError("非法字符 @ 应报词法错误")
    except LexError:
        pass


def case_duplicate_block():
    src = ('window 8000 ;\n'
           'block dup { source: "x.txt" ; cap: 100 ; }\n'
           'block dup { source: "y.txt" ; cap: 200 ; }\n')
    ir, diags = _compile_text(src)
    assert ir is None, "重名块应编译失败"
    assert any("重复定义" in d.msg for d in diags), diags


def case_must_keep_unsolvable():
    src = ('window 1000 ;\n'
           'block a { source: "x.txt" ; cap: 800 ; priority: must_keep ; }\n'
           'block b { source: "y.txt" ; cap: 800 ; priority: must_keep ; }\n')
    ir, diags = _compile_text(src)
    assert ir is None, "must_keep 总额超窗应判无解"
    assert any("无解" in d.msg for d in diags), diags


def case_margin_decl():
    src = ('window 8000 margin 0.85 ;\n'
           'block a { source: "x.txt" ; cap: 100 ; }\n')
    ir, diags = _compile_text(src)
    assert ir is not None, diags
    assert ir["margin"] == 0.85, ir["margin"]


def case_missing_required():
    src = "window 8000 ;\nblock a { priority: high ; }\n"  # 缺 source 和 cap
    ir, diags = _compile_text(src)
    assert ir is None, "缺必填项应编译失败"
    assert any("必填项" in d.msg for d in diags), diags


def case_enum_string_rejected():
    # 字符串 "high" 与关键字 high 字面值相同，语法层必须拒绝
    try:
        _compile_text('window 8000 ;\nblock a { source: "a.txt" ; cap: 100 ; priority: "high" ; }')
        raise AssertionError("priority 写成字符串应报语法错误")
    except ParseError:
        pass


def case_ir_source_kind():
    ir, _ = compile_file(os.path.join(ROOT, "examples", "medical_assistant.cbl"))
    kinds = {b["name"]: b["source_kind"] for b in ir["blocks"]}
    assert kinds["chat_history"] == "ident", kinds
    assert kinds["allergy_notes"] == "string", kinds
    assert ir["blocks"][4]["keep_recent"] is None, "未声明 keep_recent 应为 None"
    assert ir["rules"][0]["metric"] == "total_reserved" and ir["rules"][0]["op"] == "<="


def case_must_keep_default_overflow():
    # must_keep 块不写 overflow 时缺省为 error；普通块仍缺省 truncate_tail
    ir, diags = _compile_text('window 8000 ;\n'
                              'block a { source: "a.txt" ; cap: 100 ; priority: must_keep ; }\n'
                              'block b { source: "b.txt" ; cap: 100 ; }\n')
    assert ir is not None, diags
    assert [b["overflow"] for b in ir["blocks"]] == ["error", "truncate_tail"], ir["blocks"]


def case_non_ascii_ident():
    # ident = [A-Za-z_][A-Za-z0-9_]*，汉字不能作标识符
    try:
        _compile_text('window 8000 ;\nblock 历史 { source: "a.txt" ; cap: 100 ; }')
        raise AssertionError("汉字标识符应报词法错误")
    except LexError:
        pass


def case_diag_format():
    _, diags = _compile_text('window 8000 ;\nblock a { source: chat_log ; cap: 100 ; }\n')
    assert repr(diags[0]).startswith("[错误] 行2 E601: "), repr(diags[0])


# ---------- 错误目录正例/反例（表驱动，与 semantic.CATALOG 一一对应） ----------
# 每行：(编号, 正例, 反例)。正例应编译通过且不含该编号；反例必须报出该编号。
# 源码用字符串；③ 的非法枚举过不了 parser，用直接构造的 AST 代替（复核场景）。

def _blk(body, name="a"):
    return f'block {name} {{ source: "a.txt" ; {body} }}\n'


def _rule(expr, level="error", name="r"):
    return f"rule {name} {{ assert: {expr} ; on_violation: {level} ; }}\n"


W = "window 8000 ;\n"


def _ast(priority="high", overflow="truncate_tail", on_violation="warn"):
    blk = BlockDecl("a", 2, source="a.txt", source_kind="string", cap=100,
                    priority=priority, overflow=overflow)
    rule = RuleDecl("r", 3, "total_reserved", "<=", Operand("int", 7000), on_violation)
    return Program(window=WindowDecl(8000, 1), blocks=[blk], rules=[rule])


PAIRS = [
    ("E101", "window 1000 ;\n" + _blk("cap: 900 ;"),
             "window 1000 ;\n" + _blk("cap: 901 ;")),
    ("E102", "window 8000 margin 1 ;\n" + _blk("cap: 100 ;"),
             "window 8000 margin 1.5 ;\n" + _blk("cap: 100 ;")),
    ("E201", "window 1000 ;\n" + _blk("cap: 400 ; priority: must_keep ;")
                               + _blk("cap: 500 ; priority: must_keep ;", "b"),
             "window 1000 ;\n" + _blk("cap: 600 ; priority: must_keep ;")
                               + _blk("cap: 500 ; priority: must_keep ;", "b")),
    ("E301", lambda: _ast(priority="high"), lambda: _ast(priority="urgent")),
    ("E302", lambda: _ast(overflow="summarize"), lambda: _ast(overflow="drop_all")),
    ("E303", lambda: _ast(on_violation="warn"), lambda: _ast(on_violation="fatal")),
    ("E401", W + _blk("cap: 100 ;") + _rule("total_reserved <= 7000", name="b"),
             W + _blk("cap: 100 ;") + _rule("total_reserved <= 7000", name="a")),
    ("W501", W + _blk("cap: 100 ; overflow: sliding_window ; keep_recent: 6 ;"),
             W + _blk("cap: 100 ; overflow: truncate_tail ; keep_recent: 6 ;")),
    ("E502", W + _blk("cap: 100 ; overflow: summarize ; keep_recent: 1 ;"),
             W + _blk("cap: 100 ; overflow: summarize ; keep_recent: 0 ;")),
    ("E601", W + "block a { source: session_history ; cap: 100 ; }\n",
             W + "block a { source: chat_log ; cap: 100 ; }\n"),
    ("E701", W + _blk("cap: 100 ;") + _rule("total_reserved <= 7000"),
             W + _blk("cap: 100 ;") + _rule("total_tokens <= 7000")),
    ("R702", W + _blk("cap: 4000 ;") + _rule("total_reserved <= window * 0.5"),
             W + _blk("cap: 4001 ;") + _rule("total_reserved <= window * 0.5")),
    ("E801", W + _blk("cap: 100 ;"), W + "block a { cap: 100 ; }\n"),
    ("E802", W + _blk("cap: 1 ;"), W + _blk("cap: 0 ;")),
    ("E803", "window 1 margin 1 ;\n" + _blk("cap: 1 ;"),
             "window 0 ;\n" + _blk("cap: 1 ;")),
    ("E901", W + _blk("cap: 100 ; priority: must_keep ; overflow: error ;"),
             W + _blk("cap: 100 ; priority: must_keep ; overflow: truncate_tail ;")),
]


def _diags_of(src):
    if callable(src):
        return check(src())
    return _compile_text(src)[1]


def _pair_case(code, pos, neg):
    def fn():
        d_pos = _diags_of(pos)
        assert not has_error(d_pos), f"正例不应有错误：{d_pos}"
        assert all(d.code != code for d in d_pos), f"正例不应报 {code}：{d_pos}"
        d_neg = _diags_of(neg)
        assert any(d.code == code for d in d_neg), f"反例应报 {code}：{d_neg}"
    return fn


def case_catalog_covered():
    # 错误目录里的每一项都必须有正反例，防止新增检查漏写测试
    missing = set(CATALOG) - {code for code, _, _ in PAIRS}
    assert not missing, f"以下编号缺少正反例：{sorted(missing)}"


def case_static_assert_warn_level():
    # on_violation: warn 时静态断言失败只给警告，不阻断编译
    ir, diags = _compile_text(W + _blk("cap: 5000 ;") + _rule("total_reserved <= 50%", "warn"))
    assert ir is not None, diags
    assert any(d.code == "R702" and d.level == "警告" for d in diags), diags


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("case_"):
            run_case(name, fn)
    for code, pos, neg in PAIRS:
        run_case(f"pair_{code}", _pair_case(code, pos, neg))
    passed = sum(1 for _, ok, _ in results if ok)
    for name, ok, msg in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}  {msg}")
    print(f"\n{passed}/{len(results)} 通过")
    sys.exit(0 if passed == len(results) else 1)
