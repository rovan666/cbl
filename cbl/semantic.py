# -*- coding: utf-8 -*-
"""CBL 语义检查器。

语法分析只保证"句子结构对"，语义检查保证"意思说得通"。
对应计划书九条语义约束 ①~⑨，实现方式对应计划书"关键问题四"：
    1. 错误目录（CATALOG）：枚举全部可静态发现的错误，每项一个编号；
    2. 表驱动（CHECKS）：每个检查函数负责一条约束，产出目录中的诊断；
    3. 测试侧同样表驱动：每个编号配一对正例（应通过）/ 反例（应报错）。
新增检查 = 目录里加一行 + 写一个函数挂进 CHECKS，不用改主流程。

负责人：舒若凡
"""
from .ast_nodes import Program
from .parser import PRIORITIES, OVERFLOWS, VIOLATION_LEVELS
from .ir import _fmt_operand

# 内置来源标识符（约束⑥用）
BUILTIN_SOURCES = {"session_history", "last_tool_result", "system_prompt"}
# 断言可用度量（约束⑦用）
BUILTIN_METRICS = {"total_reserved", "every_block_min_tokens"}
# 静态度量：只依赖 cap 与 window，编译期即可求值；其余度量留给运行期引擎
STATIC_METRICS = {"total_reserved"}
# keep_recent 有意义的超限策略（约束⑤用）
KEEP_RECENT_STRATEGIES = ("summarize", "sliding_window")

# ---------- 错误目录 ----------
# 编号: (所属约束, 级别, 说明模板)。级别为 None 表示由规则的 on_violation 决定。
CATALOG = {
    "E101": ("①", "错误", "各块额度之和 {total} 超过上限 window×{margin}={limit}"),
    "E102": ("①", "错误", "margin {margin} 应在 (0, 1] 区间内"),
    "E201": ("②", "错误", "must_keep 块额度之和 {mk} 超过窗口 {win}，预算无解"),
    "E301": ("③", "错误", "块 '{name}' 的 priority 取值 '{value}' 不合法，应为 {options} 之一"),
    "E302": ("③", "错误", "块 '{name}' 的 overflow 取值 '{value}' 不合法，应为 {options} 之一"),
    "E303": ("③", "错误", "规则 '{name}' 的 on_violation 取值 '{value}' 不合法，应为 {options} 之一"),
    "E401": ("④", "错误", "名字 '{name}' 重复定义（首次出现于 行{first}）"),
    "W501": ("⑤", "警告", "块 '{name}' 声明了 keep_recent，但 overflow 为 {overflow}；"
                          "keep_recent 只对 summarize / sliding_window 有意义，将被忽略"),
    "E502": ("⑤", "错误", "块 '{name}' 的 keep_recent 必须为正整数（实际为 {value}）"),
    "E601": ("⑥", "错误", "块 '{name}' 的来源 '{source}' 不是内置来源标识符"
                          "（可用：{options}）；文件路径请用双引号括起"),
    "E701": ("⑦", "错误", "规则 '{name}' 的度量 '{metric}' 未定义（可用：{options}）"),
    "R702": ("⑦", None, "规则 '{name}' 断言不成立：{metric}={actual}，要求 {op} {bound}（{expr}）"),
    "E801": ("⑧", "错误", "块 '{name}' 缺少必填项 source"),
    "E802": ("⑧", "错误", "块 '{name}' 缺少必填项 cap（或 cap 不是正整数）"),
    "E803": ("⑧", "错误", "window 容量必须为正整数（实际为 {win}）"),
    "E901": ("⑨", "错误", "块 '{name}' 为 must_keep，overflow 只能是 error（实际为 {overflow}），"
                          "死保信息不允许被任何策略裁剪"),
}


class Diagnostic:
    def __init__(self, level, line, msg, code=""):
        self.level, self.line, self.msg, self.code = level, line, msg, code

    def __repr__(self):
        # 计划书约定格式：[级别] 行号 编号: 说明
        code = f" {self.code}" if self.code else ""
        return f"[{self.level}] 行{self.line}{code}: {self.msg}"


def _diag(code, line, level=None, **kw):
    """按错误目录编号造一条诊断。"""
    _, default_level, template = CATALOG[code]
    return Diagnostic(level or default_level, line, template.format(**kw), code)


def _options(items):
    return " / ".join(sorted(items) if isinstance(items, set) else items)


# ---------- 检查表：每个函数对应一条约束 ----------

def check_total(prog):
    """① 预算总量约束：Σcap ≤ window × margin（margin 可在 window 声明中覆盖）"""
    w = prog.window
    if not 0 < w.margin <= 1:
        yield _diag("E102", w.line, margin=w.margin)
        return
    total = sum(b.cap for b in prog.blocks)
    if total > w.tokens * w.margin:
        yield _diag("E101", w.line, total=total, margin=w.margin,
                    limit=int(w.tokens * w.margin))


def check_unsolvable(prog):
    """② 无解判定：Σcap(must_keep) ≤ window"""
    mk = sum(b.cap for b in prog.blocks if b.priority == "must_keep")
    if mk > prog.window.tokens:
        yield _diag("E201", prog.window.line, mk=mk, win=prog.window.tokens)


def check_enums(prog):
    """③ 枚举合法性：parser 已在语法层挡掉非法取值；这里复核 AST，
    防止绕过 parser 直接构造 AST（如网页演示、程序化生成）带进非法值。"""
    for b in prog.blocks:
        if b.priority not in PRIORITIES:
            yield _diag("E301", b.line, name=b.name, value=b.priority,
                        options=_options(PRIORITIES))
        if b.overflow not in OVERFLOWS:
            yield _diag("E302", b.line, name=b.name, value=b.overflow,
                        options=_options(OVERFLOWS))
    for r in prog.rules:
        if r.on_violation not in VIOLATION_LEVELS:
            yield _diag("E303", r.line, name=r.name, value=r.on_violation,
                        options=_options(VIOLATION_LEVELS))


def check_unique(prog):
    """④ 命名唯一性：block 与 rule 共用一张符号表"""
    seen = {}
    for node in prog.blocks + prog.rules:
        if node.name in seen:
            yield _diag("E401", node.line, name=node.name, first=seen[node.name])
        else:
            seen[node.name] = node.line


def check_keep_recent(prog):
    """⑤ 参数适配性：keep_recent 须为正整数，且只配 summarize / sliding_window"""
    for b in prog.blocks:
        if b.keep_recent is None:
            continue
        if b.keep_recent <= 0:
            yield _diag("E502", b.line, name=b.name, value=b.keep_recent)
        elif b.overflow not in KEEP_RECENT_STRATEGIES:
            yield _diag("W501", b.line, name=b.name, overflow=b.overflow)


def check_source(prog):
    """⑥ 来源合法性：字符串字面量一律放行（运行期再读）；标识符必须是内置来源"""
    for b in prog.blocks:
        if b.source_kind == "ident" and b.source not in BUILTIN_SOURCES:
            yield _diag("E601", b.line, name=b.name, source=b.source,
                        options=_options(BUILTIN_SOURCES))


def _operand_value(op, win):
    if op.kind == "percent":
        return win * op.value / 100
    if op.kind == "window_scale":
        return win * op.value
    return op.value


def check_assert(prog):
    """⑦ 断言合法性：度量必须预定义；静态断言（只涉及 cap 与 window）在编译期求值，
    失败按 on_violation 报错误或警告；动态断言留给运行期引擎求值。"""
    win = prog.window.tokens
    total = sum(b.cap for b in prog.blocks)
    for r in prog.rules:
        if r.metric not in BUILTIN_METRICS:
            yield _diag("E701", r.line, name=r.name, metric=r.metric,
                        options=_options(BUILTIN_METRICS))
            continue
        if r.metric not in STATIC_METRICS:
            continue
        bound = _operand_value(r.operand, win)
        ok = total <= bound if r.op == "<=" else total >= bound
        if not ok:
            level = "错误" if r.on_violation == "error" else "警告"
            yield _diag("R702", r.line, level=level, name=r.name, metric=r.metric,
                        actual=total, op=r.op, bound=f"{bound:g}",
                        expr=_fmt_operand(r.operand))


def check_required(prog):
    """⑧ 必填项完整性（V0.02 新增）：source 与 cap 必须显式声明，window 为正整数"""
    if prog.window.tokens <= 0:
        yield _diag("E803", prog.window.line, win=prog.window.tokens)
    for b in prog.blocks:
        if not b.source:
            yield _diag("E801", b.line, name=b.name)
        if b.cap <= 0:
            yield _diag("E802", b.line, name=b.name)


def check_protection(prog):
    """⑨ 保护一致性：must_keep 块的 overflow 只能是 error（parser 已把缺省值填成 error）"""
    for b in prog.blocks:
        if b.priority == "must_keep" and b.overflow != "error":
            yield _diag("E901", b.line, name=b.name, overflow=b.overflow)


CHECKS = [check_total, check_unsolvable, check_enums, check_unique,
          check_keep_recent, check_source, check_assert, check_required,
          check_protection]


def check(prog: Program) -> list:
    """返回诊断列表（按行号排序）；含 '错误' 级诊断则视为编译失败。"""
    diags = [d for fn in CHECKS for d in fn(prog)]
    return sorted(diags, key=lambda d: d.line)


def has_error(diags: list) -> bool:
    return any(d.level == "错误" for d in diags)
