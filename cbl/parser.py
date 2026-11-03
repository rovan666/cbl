# -*- coding: utf-8 -*-
"""CBL 语法分析器：手写递归下降（Recursive Descent）。

每条 EBNF 产生式对应一个 parse_xxx 函数，函数之间按文法结构互相调用：
    program      = { windowDecl | blockDecl | ruleDecl } ;
    windowDecl   = "window" int [ "margin" number ] ";" ;
    blockDecl    = "block" ident "{" { blockItem } "}" ;
    blockItem    = sourceItem | capItem | priorityItem | overflowItem | keepItem ;
    capItem      = "cap" ":" operand ";" ;       （cap 与断言右值共用 operand：
                                                  整数 / 整数% / window*数字，
                                                  相对额度在解析完折算成绝对 token 数）
    ruleDecl     = "rule" ident "{" "assert" ":" assertExpr ";"
                   "on_violation" ":" ( "warn" | "error" ) ";" "}" ;
    assertExpr   = ident ( "<=" | ">=" ) operand ;
    operand      = int | int "%" | "window" "*" number ;

报错风格：指出"第几行第几列，期望什么，实际读到什么"。
错误恢复（panic mode）：一条声明/条目出错后，跳到下一个同步点（; 或 }）继续
分析，一次编译报出尽量多的语法错误（ParseErrors 收集），而不是只报第一个。

负责人：徐同帅
"""
from .tokens import Token
from .ast_nodes import WindowDecl, BlockDecl, RuleDecl, Operand, Program

PRIORITIES = ("must_keep", "high", "medium", "low")
OVERFLOWS = ("truncate_tail", "rerank_drop", "summarize", "sliding_window", "error")
VIOLATION_LEVELS = ("warn", "error")
TOP_KEYWORDS = ("window", "block", "rule")      # 顶层声明的开头，错误恢复的同步点
BLOCK_ITEMS = ("source", "cap", "priority", "overflow", "keep_recent")


def _describe(tok: Token) -> str:
    """报错里怎么称呼读到的 Token：字符串要说明是字符串，否则 "high" 和 high 看起来一样。"""
    if tok.kind == "EOF":
        return "文件结尾"
    if tok.kind == "STRING":
        return f'字符串 "{tok.value}"'
    return repr(tok.value)


class ParseError(Exception):
    def __init__(self, msg, token: Token, line: int = None, col: int = None):
        """line/col：报错位置，缺省为读到的 Token 所在处；缺分号时指向上一个
        Token 的结尾（人会去那一行找），并注明实际读到的 Token 在哪。"""
        self.line = token.line if line is None else line
        self.col = token.col if col is None else col
        where = ""
        if (token.line, token.col) != (self.line, self.col):
            where = f"（实际位于 行{token.line} 列{token.col}）"
        super().__init__(f"语法错误 行{self.line} 列{self.col}: "
                         f"{msg}，实际读到 {_describe(token)}{where}")


class ParseErrors(Exception):
    """一处以上语法错误的收集结果（错误恢复的产出）；errors 为 ParseError 列表。"""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("\n".join(str(e) for e in self.errors))


class Parser:
    def __init__(self, tokens: list):
        self.tokens = tokens
        self.pos = 0
        self.errors = []            # 错误恢复收集的语法错误
        self._relative_caps = []    # [(block, operand)]：待折算的相对 cap

    # ---------- 基础工具 ----------
    def peek(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        if tok.kind != "EOF":
            self.pos += 1
        return tok

    @staticmethod
    def _is(tok: Token, value: str) -> bool:
        """终结符匹配：值相同且必须是关键字或界符——字符串 ";"、"cap" 不能冒充终结符。"""
        return tok.value == value and tok.kind in ("KEYWORD", "SYMBOL")

    def expect(self, value: str, what: str = "") -> Token:
        """断言下一个 Token 是指定终结符，否则报错。what 用于拼错误信息。"""
        tok = self.peek()
        if not self._is(tok, value):
            line = col = None
            if value == ";" and self.pos > 0:   # 缺分号：指向上一个 Token 的结尾
                prev = self.tokens[self.pos - 1]
                line, col = prev.line, prev.col + len(prev.value)
            raise ParseError(f"期望 '{value}'（{what or '语法要求'}）", tok, line, col)
        return self.advance()

    def expect_kind(self, kind: str, what: str) -> Token:
        tok = self.peek()
        if tok.kind != kind:
            raise ParseError(f"期望{what}", tok)
        return self.advance()

    # ---------- 错误恢复同步点 ----------
    def _sync_top(self):
        """顶层：消费掉 ';' 或 '}' 后停；遇到下一条顶层声明的开头或 EOF 直接停。"""
        while self.peek().kind != "EOF":
            tok = self.peek()
            if self._is(tok, ";") or self._is(tok, "}"):
                self.advance()
                return
            if tok.kind == "KEYWORD" and tok.value in TOP_KEYWORDS:
                return
            self.advance()

    def _sync_item(self):
        """块内：消费掉 ';' 后停；遇到 '}'（块体结束，留给外层消费）或 EOF 直接停。"""
        while self.peek().kind != "EOF":
            if self._is(self.peek(), ";"):
                self.advance()
                return
            if self._is(self.peek(), "}"):
                return
            self.advance()

    # ---------- 产生式 ----------
    def parse_program(self) -> Program:
        prog = Program()
        while self.peek().kind != "EOF":
            tok = self.peek()
            try:
                if self._is(tok, "window"):
                    if prog.window is not None:
                        raise ParseError("window 声明整个程序只能有一条", tok)
                    prog.window = self.parse_window()
                elif self._is(tok, "block"):
                    prog.blocks.append(self.parse_block())
                elif self._is(tok, "rule"):
                    prog.rules.append(self.parse_rule())
                else:
                    raise ParseError("顶层只允许 window / block / rule 声明", tok)
            except ParseError as e:
                self.errors.append(e)
                self._sync_top()
        self._resolve_caps(prog)
        if not self.errors:
            # 完整性检查只在无语法错误时做——前面已经报错的话，"缺少 window"
            # 之类多半是连带伤害，报出来反而误导
            if prog.window is None:
                self.errors.append(ParseError("缺少 window 声明（程序必须恰有一条）",
                                              self.peek()))
            if not prog.blocks:
                self.errors.append(ParseError("至少需要一条 block 声明", self.peek()))
        return prog

    def _resolve_caps(self, prog: Program):
        """相对 cap（cap: 40% / cap: window * 0.4）在整条程序解析完、window 已知后
        折算成绝对 token 数（四舍五入）——AST 与下游（语义检查、IR、引擎）只看到整数。"""
        if prog.window is None:
            return
        win = prog.window.tokens
        for blk, op in self._relative_caps:
            if op.kind == "percent":
                blk.cap = int(win * op.value / 100 + 0.5)
            else:   # window_scale
                blk.cap = int(win * op.value + 0.5)

    def parse_window(self) -> WindowDecl:
        kw = self.expect("window", "窗口声明开头")
        cap = self.expect_kind("INT", "窗口容量（整数 token 数）")
        decl = WindowDecl(tokens=int(cap.value), line=kw.line)
        if self._is(self.peek(), "margin"):    # 可选：window 8000 margin 0.85 ;
            self.advance()
            m = self.peek()
            if m.kind not in ("INT", "FLOAT"):
                raise ParseError("margin 应是 0~1 之间的数字（如 0.85）", m)
            self.advance()
            decl.margin = float(m.value)
        self.expect(";", "window 声明结尾")
        return decl

    def parse_block(self) -> BlockDecl:
        kw = self.expect("block", "块声明开头")
        name = self.expect_kind("IDENT", "块名（标识符）")
        blk = BlockDecl(name=name.value, line=kw.line)
        self.expect("{", "块体开始")
        seen = set()
        while not self._is(self.peek(), "}") and self.peek().kind != "EOF":
            try:
                self._block_item(blk, seen)
            except ParseError as e:
                self.errors.append(e)
                self._sync_item()
        self.expect("}", "块体结束")
        # 缺省值约定：must_keep 块未声明 overflow 时缺省为 error（死保信息不裁剪）
        if "overflow" not in seen and blk.priority == "must_keep":
            blk.overflow = "error"
        return blk

    def _block_item(self, blk: BlockDecl, seen: set):
        item = self.peek()
        if item.kind != "KEYWORD" or item.value not in BLOCK_ITEMS:
            raise ParseError("块内只接受 source/cap/priority/overflow/keep_recent 条目", item)
        if item.value in seen:
            raise ParseError(f"条目 '{item.value}' 在同一个块里重复声明", item)
        seen.add(item.value)
        key = item.value
        self.advance()
        self.expect(":", f"{key} 条目")
        if key == "source":
            t = self.peek()
            if t.kind not in ("STRING", "IDENT"):
                raise ParseError("source 只接受字符串或内置来源标识符", t)
            blk.source_kind = "string" if t.kind == "STRING" else "ident"
            blk.source = self.advance().value
        elif key == "cap":
            op = self.parse_operand("cap 额度")
            if op.kind == "int":
                blk.cap = op.value
            else:   # 相对额度：等 window 已知后由 _resolve_caps 折算
                self._relative_caps.append((blk, op))
        elif key == "priority":
            blk.priority = self._choice(PRIORITIES, "优先级")
        elif key == "overflow":
            blk.overflow = self._choice(OVERFLOWS, "超限策略")
        elif key == "keep_recent":
            blk.keep_recent = int(self.expect_kind("INT", "保留条数整数").value)
        self.expect(";", f"{key} 条目结尾")

    def parse_rule(self) -> RuleDecl:
        kw = self.expect("rule", "规则声明开头")
        name = self.expect_kind("IDENT", "规则名")
        rule = RuleDecl(name=name.value, line=kw.line, metric="", op="",
                        operand=None, on_violation="warn")
        self.expect("{", "规则体开始")
        self.expect("assert", "规则断言语句")
        self.expect(":", "assert 条目")
        rule.metric = self.expect_kind("IDENT", "度量名").value
        op = self.peek()
        if op.kind != "SYMBOL" or op.value not in ("<=", ">="):
            raise ParseError("断言只支持 <= 或 >=", op)
        rule.op = self.advance().value
        rule.operand = self.parse_operand()
        self.expect(";", "assert 条目结尾")
        self.expect("on_violation", "违例级别语句")
        self.expect(":", "on_violation 条目")
        rule.on_violation = self._choice(VIOLATION_LEVELS, "违例级别")
        self.expect(";", "on_violation 条目结尾")
        self.expect("}", "规则体结束")
        return rule

    def parse_operand(self, what="断言右值") -> Operand:
        tok = self.peek()
        if tok.kind == "INT":
            value = int(self.advance().value)
            if self._is(self.peek(), "%"):          # int "%"
                self.advance()
                return Operand("percent", value)
            return Operand("int", value)            # int
        if self._is(tok, "window"):                 # "window" "*" number
            self.advance()
            self.expect("*", f"{what}的 window 倍数表达式")
            n = self.peek()
            if n.kind not in ("INT", "FLOAT"):
                raise ParseError(f"{what}的 window 倍数应是数字（如 window * 0.9）", n)
            self.advance()
            return Operand("window_scale", float(n.value))
        raise ParseError(f"{what}只接受 整数 / 整数% / window*数字", tok)

    def _choice(self, options, what):
        tok = self.peek()
        # 枚举值必须是关键字本身；字符串 "high" 字面值相同，但不能混过去
        if tok.kind != "KEYWORD" or tok.value not in options:
            raise ParseError(f"{what}必须是 {' / '.join(options)} 之一", tok)
        return self.advance().value


def parse(tokens: list) -> Program:
    """语法分析入口。有错不立即抛：尽量恢复并收集，最后抛 ParseErrors。"""
    parser = Parser(tokens)
    prog = parser.parse_program()
    if parser.errors:
        raise ParseErrors(parser.errors)
    return prog
