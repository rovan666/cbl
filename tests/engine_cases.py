# -*- coding: utf-8 -*-
"""执行引擎与审计报告的测试用例（由 run_tests.py 统一收集运行）。

分三类：
  1. 单元：token 估算、有效额度分配（ⓑ）、五种超限策略；
  2. 端到端：医疗助手示例 + examples/materials，缺省额度与调低额度两种场景；
  3. 快照（计划书问题五 ③）：审计报告文本与 tests/snapshots/ 逐字比对，
     引擎改动若改变了裁剪行为会立即暴露。确认是预期变化后，
     设环境变量 CBL_UPDATE_SNAPSHOTS=1 重跑即可更新快照。
"""
import os

from cbl.cli import compile_file
from cbl.engine import (AssemblyError, Context, allocate, assemble, estimate_tokens,
                        rerank_drop, rule_summary, sliding_window, summarize, truncate_tail)
from cbl.report import render_text

ROOT = os.path.join(os.path.dirname(__file__), "..")
EXAMPLE = os.path.join(ROOT, "examples", "medical_assistant.cbl")
MATERIALS = os.path.join(ROOT, "examples", "materials")
SNAPSHOTS = os.path.join(os.path.dirname(__file__), "snapshots")


def _plan():
    ir, diags = compile_file(EXAMPLE)
    assert ir is not None, diags
    return ir


def _run(budget=None):
    return assemble(_plan(), Context.from_dir(MATERIALS, budget=budget))


def _strategy(fn, units, limit, sep="\n\n", keep_recent=None, query=""):
    block = {"name": "t", "keep_recent": keep_recent}
    return fn(units, sep, limit, block, Context(query=query), estimate_tokens, rule_summary)


# ---------- 1. 单元 ----------

def case_estimate_tokens():
    e = estimate_tokens
    assert e("") == 0
    assert (e("abc"), e("abcd")) == (1, 2), "英文按每 3 字符 1 个向上取整"
    assert e("中文") == 3, "中文每字 1.5，向上取整"
    assert e("a b") == 2 and e("a\nb") == 3, "空格不计、换行计 1"
    s = "上下文 budget 预算，window=8000。\n第二行"
    counts = [e(s[:k]) for k in range(len(s) + 1)]
    assert counts == sorted(counts), "前缀计数必须单调不减（truncate 二分查找依赖）"


def case_allocate_enough_budget():
    blocks = _plan()["blocks"]
    eff = allocate(blocks, 7200)
    assert eff == {b["name"]: b["cap"] for b in blocks}, "额度充足时每块即得其 cap"


def case_allocate_squeeze_matches_plan():
    # 计划书第 5 节压缩示例：B=6000 → tool_output 压到 0，chat_history 1600→1000
    eff = allocate(_plan()["blocks"], 6000)
    assert eff["tool_output"] == 0 and eff["chat_history"] == 1000, eff
    assert eff["retrieved_docs"] == 3200 and eff["system_prompt"] == 1500, "high 与 must_keep 不受影响"


def case_allocate_proportional():
    blk = lambda n, cap: {"name": n, "cap": cap, "priority": "low"}   # noqa: E731
    eff = allocate([blk("a", 300), blk("b", 100)], 200)
    assert eff == {"a": 150, "b": 50}, f"同级按 cap 等比例压缩：{eff}"
    eff = allocate([blk("a", 100), blk("b", 100), blk("c", 100)], 200)
    assert sum(eff.values()) == 200 and sorted(eff.values()) == [66, 67, 67], eff


def case_allocate_must_keep_over_budget():
    try:
        allocate(_plan()["blocks"], 1700)          # must_keep 合计 1800
        raise AssertionError("must_keep 总额超过可用额度应拒绝")
    except ValueError as e:
        assert "1800" in str(e) and "1700" in str(e), e


def case_truncate_tail():
    text = "第一句话在这里。第二句话也在这里。第三句话还在这里。"
    out, detail = _strategy(truncate_tail, [text], 30)
    assert estimate_tokens(out) <= 30 and text.startswith(out), out
    assert out.endswith("。"), f"应尽量停在句末：{out}"
    assert "截断尾部" in detail


def case_sliding_window():
    turns = [f"用户：第{i}个问题\n助手：第{i}个回答" for i in range(1, 6)]
    out, detail = _strategy(sliding_window, turns, 1000, sep="\n", keep_recent=2)
    assert out == "\n".join(turns[-2:]), out
    assert "保留最近 2 轮" in detail and "丢弃较早的 3 轮" in detail, detail


def case_rerank_drops_irrelevant():
    paras = ["青霉素过敏患者应避免青霉素类抗生素。", "高血压患者每日食盐不超过五克。",
             "阿奇霉素可作为青霉素过敏者的替代抗生素。"]
    limit = estimate_tokens("\n\n".join([paras[0], paras[2]]))
    out, detail = _strategy(rerank_drop, paras, limit, query="青霉素过敏能用什么抗生素")
    assert out == "\n\n".join([paras[0], paras[2]]), f"应丢掉无关段且保持原顺序：{out}"
    assert "丢弃相关度最低的 1 段" in detail, detail


def case_rerank_without_query_drops_tail():
    paras = ["第一段内容。", "第二段内容。", "第三段内容。"]
    limit = estimate_tokens("\n\n".join(paras[:2]))
    out, detail = _strategy(rerank_drop, paras, limit)
    assert out == "\n\n".join(paras[:2]) and "无查询" in detail, (out, detail)


def case_summarize():
    turns = [f"用户：这是第{i}轮比较长的一个问题，描述了一些症状。\n助手：这是第{i}轮的回答，给出了建议。"
             for i in range(1, 7)]
    limit = estimate_tokens("\n".join(turns[-2:])) + 60
    out, detail = _strategy(summarize, turns, limit, sep="\n", keep_recent=2)
    assert out.startswith("【早期对话摘要】") and out.endswith("\n".join(turns[-2:])), out
    assert estimate_tokens(out) <= limit, "摘要 + 原文不得超过额度"
    assert "保留最近 2 轮原文" in detail, detail


# ---------- 2. 端到端 ----------

def case_e2e_default_budget():
    prompt, audit = _run()
    assert audit["status"] == "ok" and audit["budget"] == 7200
    for b in audit["blocks"]:
        assert b["used"] <= b["effective"], f"{b['name']} 用量超出有效额度：{b}"
    assert audit["total_used"] <= audit["budget"]
    acts = {b["name"]: b["action"] for b in audit["blocks"]}
    assert acts == {"system_prompt": "完整保留", "allergy_notes": "完整保留",
                    "retrieved_docs": "rerank_drop", "chat_history": "summarize",
                    "tool_output": "truncate_tail"}, acts
    # ⓓ 按声明顺序拼接：系统提示 → 过敏史 → 检索资料 → 对话 → 工具输出
    marks = ["安心问诊", "用户过敏史", "【急性咽炎概述】", "【早期对话摘要】", "drug_safety_lookup"]
    pos = [prompt.index(m) for m in marks]
    assert pos == sorted(pos), f"拼接顺序应与声明顺序一致：{pos}"
    assert "【高血压患者的饮食】" not in prompt, "无关段落应被 rerank_drop 丢弃"


def case_e2e_squeezed_budget():
    prompt, audit = _run(budget=6000)
    by = {b["name"]: b for b in audit["blocks"]}
    assert by["tool_output"]["action"] == "整块舍弃" and "drug_safety_lookup" not in prompt
    assert by["chat_history"]["effective"] == 1000 and by["chat_history"]["used"] <= 1000
    starve = [r for r in audit["rules"] if r["name"] == "no_starvation"][0]
    assert not starve["passed"] and starve["where"] == "tool_output", starve
    assert audit["status"] == "ok", "warn 级违例不阻断组装"


def case_e2e_rejections():
    try:
        _run(budget=1700)
        raise AssertionError("可用额度低于 must_keep 总额应拒绝组装")
    except AssemblyError as e:
        assert e.audit["status"] == "rejected" and "1800" in e.audit["error"]
    # must_keep 来源缺失：死保信息无法保证 → 拒绝
    ctx = Context.from_dir(MATERIALS)
    ctx.root = os.path.join(MATERIALS, "不存在的目录")
    try:
        assemble(_plan(), ctx)
        raise AssertionError("must_keep 来源缺失应拒绝组装")
    except AssemblyError as e:
        assert "来源" in str(e) and "缺失" in str(e), e


def case_e2e_error_rule_rejects():
    plan = _plan()
    plan["rules"][1].update(on_violation="error", operand=400)    # 最小有效额度 300 < 400
    try:
        assemble(plan, Context.from_dir(MATERIALS))
        raise AssertionError("error 级动态断言不成立应拒绝组装")
    except AssemblyError as e:
        assert "no_starvation" in str(e), e


# ---------- 3. 快照 ----------

def _snapshot(name, text):
    path = os.path.join(SNAPSHOTS, name)
    if os.environ.get("CBL_UPDATE_SNAPSHOTS") == "1" or not os.path.exists(path):
        os.makedirs(SNAPSHOTS, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
        return
    want = open(path, encoding="utf-8").read().rstrip("\n")
    assert text == want, (f"审计报告与快照 {name} 不一致——若是预期变化，"
                          f"设 CBL_UPDATE_SNAPSHOTS=1 重跑以更新。\n实际：\n{text}")


def case_snapshot_reports():
    _snapshot("medical_default.txt", render_text(_run()[1]))
    _snapshot("medical_budget6000.txt", render_text(_run(budget=6000)[1]))
    try:
        _run(budget=1700)
    except AssemblyError as e:
        _snapshot("medical_budget1700.txt", render_text(e.audit))
