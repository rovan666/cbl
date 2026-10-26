# -*- coding: utf-8 -*-
"""CBL 词法分析器（Scanner）。

职责：把源文件字符流切成 Token 序列。
实现方式：最朴素的逐字符有限自动机——每读一个字符，根据当前状态
决定"继续累积"还是"产出一个 Token"。不依赖任何第三方库。

负责人：徐同帅
"""
from .tokens import Token, KEYWORDS, SINGLE_SYMBOLS, DOUBLE_SYMBOLS


class LexError(Exception):
    """词法错误：带行号列号，方便用户定位。"""

    def __init__(self, msg, line, col):
        super().__init__(f"词法错误 行{line} 列{col}: {msg}")
        self.line, self.col = line, col


def tokenize(text: str) -> list:
    """把 CBL 源码文本扫描成 Token 列表（末尾追加 EOF 哨兵）。"""
    tokens = []
    i, line, col = 0, 1, 1
    n = len(text)

    def peek(offset=0):
        return text[i + offset] if i + offset < n else ""

    def advance():
        nonlocal i, line, col
        if text[i] == "\n":
            line, col = line + 1, 1
        else:
            col += 1
        i += 1

    while i < n:
        ch = text[i]

        # 1) 空白：跳过
        if ch in " \t\r\n":
            advance()
            continue

        # 2) 注释：# 到行尾，整体丢弃
        if ch == "#":
            while i < n and text[i] != "\n":
                advance()
            continue

        start_line, start_col = line, col

        # 3) 字符串："..."，不允许跨行、不处理转义（计划书正规式规定）
        if ch == '"':
            advance()
            buf = []
            while i < n and text[i] not in '"\n':
                buf.append(text[i])
                advance()
            if i >= n or text[i] == "\n":
                raise LexError("字符串没有收尾的双引号", start_line, start_col)
            advance()  # 吃掉收尾引号
            tokens.append(Token("STRING", "".join(buf), start_line, start_col))
            continue

        # 4) 数字：整数 INT；带小数点且点后有数字的是 FLOAT（如 0.9）
        if ch.isdigit():
            buf = []
            while i < n and text[i].isdigit():
                buf.append(text[i])
                advance()
            kind = "INT"
            if peek() == "." and peek(1).isdigit():
                buf.append(".")
                advance()
                while i < n and text[i].isdigit():
                    buf.append(text[i])
                    advance()
                kind = "FLOAT"
            tokens.append(Token(kind, "".join(buf), start_line, start_col))
            continue

        # 5) 标识符 / 关键字：ident = [A-Za-z_][A-Za-z0-9_]*
        #    只认 ASCII；str.isalpha() 会把汉字也当字母，与正规式不符
        if (ch.isascii() and ch.isalpha()) or ch == "_":
            buf = []
            while i < n and ((text[i].isascii() and text[i].isalnum()) or text[i] == "_"):
                buf.append(text[i])
                advance()
            word = "".join(buf)
            kind = "KEYWORD" if word in KEYWORDS else "IDENT"
            tokens.append(Token(kind, word, start_line, start_col))
            continue

        # 6) 双字符运算符（必须先于单字符判断）
        two = ch + peek(1)
        if two in DOUBLE_SYMBOLS:
            advance()
            advance()
            tokens.append(Token("SYMBOL", two, start_line, start_col))
            continue

        # 7) 单字符界符
        if ch in SINGLE_SYMBOLS:
            advance()
            tokens.append(Token("SYMBOL", ch, start_line, start_col))
            continue

        raise LexError(f"无法识别的字符 {ch!r}", line, col)

    tokens.append(Token("EOF", "", line, col))
    return tokens
