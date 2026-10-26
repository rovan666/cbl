# -*- coding: utf-8 -*-
"""CBL 抽象语法树（AST）节点定义。

语法分析器（parser.py）把 Token 序列组装成这里定义的树结构。
每个节点都带着行号，语义检查和报错时可以指回源码位置。
"""
from dataclasses import dataclass, field


@dataclass
class WindowDecl:
    tokens: int        # 窗口总容量
    line: int
    margin: float = 0.9  # 可选声明，缺省 0.9，取值 (0, 1]


@dataclass
class BlockDecl:
    name: str
    line: int
    source: str = ""          # 字符串字面量或内置来源标识符
    source_kind: str = ""     # "string" / "ident"，语义约束⑥据此区分
    cap: int = 0              # 额度（token 数）
    priority: str = "medium"  # must_keep / high / medium / low
    overflow: str = "truncate_tail"  # 五种超限策略之一
    keep_recent: int = None   # None 表示未声明（未启用）


@dataclass
class Operand:
    """assert 表达式右值：整数 / 百分比 / window 倍数，三种形态。"""
    kind: str   # "int" / "percent" / "window_scale"
    value: float


@dataclass
class RuleDecl:
    name: str
    line: int
    metric: str        # 左值度量，如 total_reserved
    op: str            # "<=" 或 ">="
    operand: Operand
    on_violation: str  # "warn" / "error"


@dataclass
class Program:
    window: WindowDecl = None
    blocks: list = field(default_factory=list)
    rules: list = field(default_factory=list)
