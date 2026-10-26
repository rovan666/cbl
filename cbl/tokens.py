# -*- coding: utf-8 -*-
"""CBL 词法定义：Token 类型与关键字表。

对应计划书"语言定义"一节的词法正规式：
    keyword / ident / int / string / comment / 界符
词法分析器（lexer.py）输出的是一个 Token 序列，每个 Token 记录
类型、字面值、行号、列号，供语法分析器消费。
"""
from dataclasses import dataclass

# 21 个关键字（计划书 V0.03 词法定义）
KEYWORDS = {
    # 三类顶层声明
    "window", "block", "rule",
    # 块内条目
    "cap", "priority", "overflow", "source", "keep_recent",
    # 规则条目
    "assert", "on_violation",
    # 优先级枚举
    "must_keep", "high", "medium", "low",
    # 超限策略枚举
    "truncate_tail", "rerank_drop", "summarize", "sliding_window", "error",
    # 违例级别枚举
    "warn",
    # 窗口参数
    "margin",
}

# 单字符界符
SINGLE_SYMBOLS = {"{", "}", ":", ";", "*", "%"}
# 双字符运算符（assert 表达式用）
DOUBLE_SYMBOLS = {"<=", ">="}


@dataclass
class Token:
    kind: str    # "KEYWORD" / "IDENT" / "INT" / "STRING" / "SYMBOL" / "EOF"
    value: str   # 字面值，如 "window"、"system_prompt"、8000（INT 存原文）
    line: int    # 行号，从 1 开始
    col: int     # 列号，从 1 开始

    def __repr__(self):
        return f"Token({self.kind}, {self.value!r}, 行{self.line})"
