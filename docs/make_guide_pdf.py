# -*- coding: utf-8 -*-
"""把 docs/审阅指南.md 排版成 PDF（docs/审阅指南.pdf）。

内容以 Markdown 版为唯一来源；PDF 额外加入离线阅读需要的东西：
封面、带页码的目录、PDF 书签、每章"一页速览"、核心代码摘录（取自固定提交，带行号与高亮）、
压缩示意图、实验台截图、附录（术语表 / 命令速查 / 五分钟演示脚本）。

排版：HTML + CSS → Edge 无头打印（中文字体、表格、分页都由浏览器处理）。
目录页码两遍渲染：先排一遍，查出各标题所在页，填回目录再排一遍。

依赖（仅文档工具需要，CBL 本身仍是零依赖）：markdown、pygments、pymupdf、Microsoft Edge。
用法（cbl 目录下）：python docs/make_guide_pdf.py
"""
import datetime
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile

import markdown
import pymupdf
from bs4 import BeautifulSoup
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name

COMMIT = "50b4276"
REPO = "https://github.com/rovan666/cbl"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MD = os.path.join(HERE, "审阅指南.md")
OUT = os.path.join(HERE, "审阅指南.pdf")
ARCH = os.path.join(HERE, "arch.png")
DEMO = os.path.join(HERE, "demo.png")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

CHAPTERS = [  # (章号, 标题关键字, 主题色, 浅色)
    (0, "所有人先看", "#1d2433", "#eef0f4"),
    (1, "徐同帅", "#175cd3", "#e6effd"),
    (2, "舒若凡", "#6941c6", "#efeafd"),
    (3, "杨晨", "#b54708", "#fdf0e1"),
    (4, "祝梦倩", "#067647", "#e3f6ec"),
    (5, "任何人都可能被问", "#1d2433", "#eef0f4"),
    (6, "在 GitHub 上审阅", "#1d2433", "#eef0f4"),
]


# ---------- 代码摘录 ----------

_cache = {}


def git_file(path):
    if path not in _cache:
        out = subprocess.run(["git", "-C", ROOT, "show", f"{COMMIT}:{path}"],
                             capture_output=True, text=True, encoding="utf-8", check=True)
        _cache[path] = out.stdout.split("\n")
    return _cache[path]


def find_line(path, needle, after=1):
    for i, ln in enumerate(git_file(path), 1):
        if i >= after and needle in ln:
            return i
    raise SystemExit(f"摘录定位失败：{path} 里找不到 {needle!r}")


def py_block(path, start):
    """Python：从 start 行取到缩进回退为止（函数/类/赋值块的结尾），去掉尾部空行。"""
    lines = git_file(path)
    first = lines[start - 1]
    indent = len(first) - len(first.lstrip())
    end = start
    for i in range(start, len(lines)):
        ln = lines[i]
        if ln.strip() and len(ln) - len(ln.lstrip()) <= indent and not ln.lstrip().startswith((")", "]", "}")):
            break
        end = i + 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return start, end


def brace_block(path, start):
    """JS：从 start 行起做花括号配对，取到配平的那一行。"""
    lines = git_file(path)
    depth, seen = 0, False
    for i in range(start - 1, len(lines)):
        for ch in lines[i]:
            if ch == "{":
                depth, seen = depth + 1, True
            elif ch == "}":
                depth -= 1
        if seen and depth <= 0:
            return start, i + 1
    return start, len(lines)


def excerpt(path, rng, note, lang="python"):
    start, end = rng
    code = "\n".join(git_file(path)[start - 1:end])
    fmt = HtmlFormatter(linenos="table", linenostart=start, cssclass="hl", wrapcode=True)
    body = highlight(code, get_lexer_by_name(lang), fmt)
    url = f"{REPO}/blob/{COMMIT}/{path}#L{start}-L{end}"
    cls = "code long" if end - start + 1 > 20 else "code"   # 超过 20 行允许跨页，避免整段挪页留下大片空白
    return (f'<figure class="{cls}"><figcaption><span class="path">{html.escape(path)}</span>'
            f'<span class="lines">第 {start}–{end} 行</span><a href="{url}">在 GitHub 打开</a></figcaption>'
            f'{body}<div class="note">{note}</div></figure>')


def excerpts_for(chap):
    """各章“核心代码导读”：每段配一句该看什么。"""
    E = []
    if chap == 1:
        E.append(excerpt("cbl/lexer.py", (find_line("cbl/lexer.py", "# 4) 数字"),
                                          find_line("cbl/lexer.py", "# 6) 双字符") - 2),
                         "<b>最长匹配</b>：读完整数后，只有“点后面还是数字”才继续读成 FLOAT。"
                         "<b>标识符只认 ASCII</b>（<code>isascii()</code>），读完整个单词再查关键字表，决定是 KEYWORD 还是 IDENT——"
                         "这就是“关键字是保留字”在代码里的样子。"))
        E.append(excerpt("cbl/parser.py", (find_line("cbl/parser.py", "@staticmethod"),
                                           py_block("cbl/parser.py", find_line("cbl/parser.py", "def expect(self"))[1]),
                         "所有产生式都靠 <code>expect</code> 消耗终结符。<code>_is</code> 要求 Token 的<b>类型</b>是关键字或界符——"
                         "字符串 <code>\";\"</code> 值相同也不能冒充分号（提交 50b4276 修复的漏洞）。"
                         "缺分号时把报错行改为上一个 Token 所在行。"))
        E.append(excerpt("cbl/parser.py", py_block("cbl/parser.py", find_line("cbl/parser.py", "def parse_block")),
                         "<b>一个产生式 = 一个函数</b>：块体 <code>{ blockItem }</code> 写成 while 循环，循环里看<b>一个</b>条目关键字决定走哪条分支（LL(1)）。"
                         "条目重复、类型不对都在这里报错；最后为 must_keep 块填入缺省 overflow = error。"))
    elif chap == 2:
        E.append(excerpt("cbl/semantic.py", py_block("cbl/semantic.py", find_line("cbl/semantic.py", "CATALOG = {")),
                         "<b>错误目录</b>：16 项，每项 = (所属约束, 级别, 说明模板)。级别为 None 的 R702 由规则自己的 on_violation 决定。"
                         "后面所有检查函数都只是在“按编号造诊断”。"))
        E.append(excerpt("cbl/semantic.py", py_block("cbl/semantic.py", find_line("cbl/semantic.py", "def check_assert")),
                         "<b>静态断言编译期求值</b>：度量先查是否预定义（E701）；只依赖 cap 与 window 的 total_reserved 当场算出 Σcap 与右值比较，"
                         "其余度量留给运行期。Σcap 正是 AST 上自底向上汇总的<b>综合属性</b>。"))
        E.append(excerpt("cbl/semantic.py", (find_line("cbl/semantic.py", "CHECKS = ["),
                                             py_block("cbl/semantic.py", find_line("cbl/semantic.py", "def check(prog"))[1]),
                         "<b>表驱动主流程</b>：九个检查函数排成一张表，全部跑完再按行号排序——一次报出所有语义错误。"))
        E.append(excerpt("tests/run_tests.py", (find_line("tests/run_tests.py", "def _pair_case"),
                                                py_block("tests/run_tests.py", find_line("tests/run_tests.py", "def case_catalog_covered"))[1]),
                         "<b>正反例 + 覆盖率自检</b>：正例必须编译通过且不含该编号，反例必须报出该编号；"
                         "<code>case_catalog_covered</code> 保证目录里每一项都配了测试。"))
    elif chap == 3:
        E.append(excerpt("cbl/engine.py", (find_line("cbl/engine.py", "def allocate"),
                                           py_block("cbl/engine.py", find_line("cbl/engine.py", "def _proportional"))[1]),
                         "<b>第 2 步 · 有效额度</b>：先确认 must_keep 放得下 B，再按 low → medium → high 逐级削减超出部分。"
                         "<code>_proportional</code> 用<b>最大余数法</b>取整：先发整数部分，剩余名额按小数部分从大到小补，总和恰好等于目标。"))
        E.append(excerpt("cbl/engine.py", (find_line("cbl/engine.py", "def estimate_tokens"),
                                           py_block("cbl/engine.py", find_line("cbl/engine.py", "def _fit_prefix"))[1]),
                         "<b>保守估算 + 二分</b>：中文每字 1.5、英文每 3 字符 1 个，宁多勿少。估算对任意前缀单调不减，"
                         "所以 <code>_fit_prefix</code> 能二分出“最长能放下的前缀”。"))
        E.append(excerpt("cbl/engine.py", py_block("cbl/engine.py", find_line("cbl/engine.py", "def rerank_drop")),
                         "<b>相关度丢弃</b>：以本轮提问为查询算 BM25，分数从低到高整段丢弃，剩余段落保持原顺序；"
                         "只剩一段仍超额时退化为截断。没有提问时按位置从末尾丢。"))
        E.append(excerpt("cbl/engine.py", py_block("cbl/engine.py", find_line("cbl/engine.py", "def assemble_parts")),
                         "<b>主流程（三步走）</b>：定 B → 分配有效额度 → 逐块读材料、超额执行策略；最后求值运行期断言。"
                         "任何一步要拒绝组装都走 <code>reject()</code>，把截至当时的审计记录一并带出。"))
    elif chap == 4:
        E.append(excerpt("cbl/webui.py", py_block("cbl/webui.py", find_line("cbl/webui.py", "def _unit_status")),
                         "<b>单位状态判定</b>：原文出现在最终文本里 = 保留；位于保留原文之前且有摘要 = 并入摘要；只出现首尾片段 = 部分保留。"
                         "注意“并入摘要”必须先于“部分保留”判断——摘要会引用这些轮次的首句（曾经的 bug）。"))
        E.append(excerpt("cbl/static/report.js", brace_block("cbl/static/report.js", find_line("cbl/static/report.js", "function h(tag, attrs)")),
                         "<b>防 XSS 第一道关</b>：渲染器只用 <code>createElement</code> 与 <code>textContent</code> 构建节点，"
                         "从不把材料内容拼进 HTML 字符串。", lang="javascript"))
        E.append(excerpt("cbl/report.py", py_block("cbl/report.py", find_line("cbl/report.py", "def _embed_json")),
                         "<b>防 XSS 第二道关</b>：HTML 报告内嵌的 JSON 把 &lt; &gt; &amp; 转成 \\u 形式，"
                         "材料里即使有 <code>&lt;/script&gt;</code> 也截断不了脚本；JSON 解析后原文不变。"))
        E.append(excerpt("cbl/static/demo.html", brace_block("cbl/static/demo.html", find_line("cbl/static/demo.html", "function analyze()")),
                         "<b>拖动不乱序</b>：每次请求序号 +1，只渲染序号仍是最新的响应；旧请求用 AbortController 取消。", lang="javascript"))
        E.append(excerpt("tests/engine_cases.py", py_block("tests/engine_cases.py", find_line("tests/engine_cases.py", "def _snapshot")),
                         "<b>快照测试</b>：首次运行生成快照，之后逐字比对；预期内的变化用 CBL_UPDATE_SNAPSHOTS=1 接受。"))
    return E


# ---------- 各章"一页速览" ----------

OVERVIEW = {
    1: dict(files="tokens.py · lexer.py · parser.py · ast_nodes.py",
            ideas=["手写确定有限自动机做词法：7 个分支、最长匹配",
                   "递归下降、LL(1)：一个产生式一个函数，看一个 Token 定分支",
                   "终结符匹配同时检查类型；报错精确到行号、期望符号、实际读到什么"],
            asks=["为什么手写，不用 ANTLR？", "文法为什么是 LL(1)？", "能一次报出多个语法错误吗？"]),
    2: dict(files="semantic.py · ir.py · tests/run_tests.py（PAIRS）",
            ideas=["错误目录 16 项 + 表驱动检查表，新增约束只需三步",
                   "属性文法：Σcap 是综合属性，window/margin 起继承属性作用",
                   "编译期断言与运行期断言的划分；IR 显式写出全部缺省值"],
            asks=["属性文法体现在哪？", "九条约束怎么保证实现正确？", "为什么要 JSON 中间表示？"]),
    3: dict(files="engine.py · examples/materials/ · tests/engine_cases.py",
            ideas=["三步走：定可用额度 B → 逐级压缩有效额度 → 执行五种策略",
                   "最大余数法、保守 token 估算 + 二分截断",
                   "BM25（中文二字组合）与规则式摘要；计数器、摘要器可插拔"],
            asks=["额度为什么不回流？", "为什么先把 low 压到 0？", "token 估算不准怎么办？"]),
    4: dict(files="report.py · webui.py · static/（report.js · report.css · demo.html）· tests/webui_cases.py",
            ideas=["审计记录 JSON 为主，文本 / HTML / 网页是它的视图",
                   "网页与 HTML 报告共用一个渲染器；两道关防 XSS",
                   "快照测试防止裁剪行为被悄悄改变；请求序号防止画面乱序"],
            asks=["怎么防止材料里的恶意内容注入页面？", "快照测试和单元测试有什么区别？", "局域网模式安全吗？"]),
}


def overview_box(chap, color, tint):
    o = OVERVIEW[chap]
    ideas = "".join(f"<li>{html.escape(x)}</li>" for x in o["ideas"])
    asks = "".join(f"<li>{html.escape(x)}</li>" for x in o["asks"])
    return (f'<div class="overview" style="--c:{color};--t:{tint}">'
            f'<div class="ov-files"><b>负责文件</b>{html.escape(o["files"])}</div>'
            f'<div class="ov-cols"><div><b>三个核心概念</b><ol>{ideas}</ol></div>'
            f'<div><b>必须能脱稿回答</b><ol>{asks}</ol></div></div></div>')


# ---------- 插图 ----------

def squeeze_figure():
    """B=7200 与 B=6000 两种场景下各块有效额度的对照条（数据与引擎、计划书一致）。"""
    blocks = [("system_prompt", "must", 1500, 1500), ("allergy_notes", "must", 300, 300),
              ("retrieved_docs", "high", 3200, 3200), ("chat_history", "medium", 1600, 1000),
              ("tool_output", "low", 500, 0)]

    def row(label, B, idx):
        segs = "".join(
            f'<div class="sq {p}" style="width:{v[idx] / 80}%"><span>{n if v[idx] >= 700 else ""}</span></div>'
            for n, p, *v in blocks if v[idx] > 0)
        rest = 8000 - sum(v[idx] for _, _, *v in blocks)
        slack = B - sum(v[idx] for _, _, *v in blocks)
        tail = (f'<div class="sq slack" style="width:{slack / 80}%"></div>' if slack > 0 else "") + \
               f'<div class="sq reserve" style="width:{(rest - max(slack, 0)) / 80}%"><span>输出预留</span></div>'
        return (f'<div class="sq-row"><div class="sq-lbl">{label}</div><div class="sq-bar">{segs}{tail}'
                f'<div class="sq-b" style="left:{B / 80}%">B={B}</div></div></div>')
    return ('<figure class="fig"><div class="sq-fig">' + row("缺省 B = 7200", 7200, 0) + row("调小到 B = 6000", 6000, 1) +
            '<div class="sq-key"><i class="must"></i>must_keep <i class="high"></i>high <i class="medium"></i>medium '
            '<i class="low"></i>low <i class="reserve"></i>输出预留</div></div>'
            '<figcaption>图 3-1　逐级压缩：B 从 7200 调到 6000，超出的 1100 先由 low 级的 tool_output 承担（500→0，整块舍弃），'
            '剩下 600 再由 medium 级的 chat_history 承担（1600→1000）；high 与 must_keep 不受影响。</figcaption></figure>')


def img_figure(path, caption):
    return f'<figure class="fig"><img src="file:///{path.replace(os.sep, "/")}"><figcaption>{caption}</figcaption></figure>'


# ---------- 附录 ----------

GLOSSARY = [
    ("Token", "词法分析的产物：(类型, 值, 行, 列)。类型有 KEYWORD / IDENT / INT / FLOAT / STRING / SYMBOL / EOF。"),
    ("AST", "抽象语法树：语法分析的产物，Program 下挂 WindowDecl、BlockDecl、RuleDecl，每个节点带行号。"),
    ("IR / JSON 组装计划", "AST 通过语义检查后翻译成的 JSON，引擎只读它；所有缺省值都已显式写出。"),
    ("cap", "块的额度上限（token），在源码里声明。"),
    ("可用额度 B", "本次组装能用的总额度，缺省 window × margin，调用方可以调小。"),
    ("有效额度", "压缩后某块本次实际可用的额度；B 充足时等于 cap，不足时按优先级削减。"),
    ("margin", "预留系数（缺省 0.9），window 的其余部分留给模型生成回答。"),
    ("must_keep", "死保优先级：不参与压缩；超出 cap 时拒绝组装，绝不静默裁剪。"),
    ("综合属性 / 继承属性", "属性文法概念：前者自底向上汇总（如 Σcap），后者自顶向下传递（如 window、margin）。"),
    ("LL(1)", "自顶向下分析时只看 1 个前瞻 Token 就能唯一确定用哪条产生式，无需回溯。"),
    ("最大余数法", "按比例分配整数名额：先发整数部分，剩余名额按小数部分从大到小补，总和精确。"),
    ("BM25", "经典的检索打分公式，综合词频、逆文档频率与文档长度。CBL 用它给检索段落排序。"),
    ("快照测试", "把完整输出存成文件，之后逐字比对，任何变化都需要人确认。"),
    ("变异检查", "故意改坏一处代码，确认测试会失败，用来证明测试真的在把关。"),
    ("XSS", "跨站脚本：不可信内容被当成 HTML/脚本执行。CBL 用 textContent 与 JSON 转义防范。"),
]

COMMANDS = [
    ("python tests/run_tests.py", "跑全部 54 个用例"),
    ("python -m cbl check examples/medical_assistant.cbl", "编译检查，输出 JSON 组装计划"),
    ("python -m cbl run examples/medical_assistant.cbl", "编译 + 组装，打印文本审计报告"),
    ("… run … --budget 6000", "指定可用额度 B"),
    ("… run … --query \"提问\"", "指定本轮用户提问（缺省读 materials/query.txt）"),
    ("… run … --out p.txt --json a.json --html a.html", "最终 Prompt / 审计 JSON / 独立 HTML 报告写盘"),
    ("python -m cbl serve", "预算实验台（Windows 可双击 启动预算实验台.bat）"),
    ("python -m cbl serve --lan", "局域网模式，手机同一 Wi-Fi 访问"),
    ("http://127.0.0.1:8000/?budget=6000", "实验台直达某个额度场景"),
    ("CBL_UPDATE_SNAPSHOTS=1 python tests/run_tests.py", "接受预期内的审计报告变化（PowerShell：先 $env:CBL_UPDATE_SNAPSHOTS=1）"),
    ("git checkout .", "动手实验改完代码后还原"),
]

DEMO_SCRIPT = [
    ("0:00", "打开实验台（缺省 B = 7200）", "这是同一份 .cbl 声明：左边是源码，右边是这次组装的结果。四种裁剪策略都触发了。"),
    ("0:40", "展开 chat_history 的「AI 实际看到的内容」", "8 轮对话，最近 4 轮保留原文，早期 4 轮压成了上面这段摘要——这就是 summarize。"),
    ("1:20", "展开 retrieved_docs", "24 段检索资料按与提问的相关度排序，高血压、骨折这些无关段落被整段丢掉。"),
    ("2:00", "点预设「压缩场景 6000」", "可用额度少了 1100：先压 low 级的工具输出，压到 0 整块舍弃；不够再压 medium 级的对话历史。high 与死保块纹丝不动。"),
    ("2:40", "指向规则警告", "工具输出被饿死了，no_starvation 规则报警告——用户写的规则在运行期生效。"),
    ("3:10", "点预设「无解 1700」", "额度低于死保总额 1800：引擎拒绝组装，没有任何内容送进模型。宁可报错，也不静默丢失过敏史。"),
    ("3:50", "把 allergy_notes 的 overflow 改成 truncate_tail", "编译期当场报 E901：死保块不允许配置裁剪策略。错误在写下的那一刻就被发现。"),
    ("4:30", "点「导出 HTML 审计报告」", "每次组装都能导出一份可存档的审计报告——AI 看到了什么、丢了什么、为什么，都可追溯。"),
]


def appendix_html():
    g = "".join(f"<tr><td><b>{html.escape(a)}</b></td><td>{html.escape(b)}</td></tr>" for a, b in GLOSSARY)
    c = "".join(f"<tr><td><code>{html.escape(a)}</code></td><td>{html.escape(b)}</td></tr>" for a, b in COMMANDS)
    d = "".join(f"<tr><td class='t'>{t}</td><td><b>{html.escape(a)}</b></td><td>{html.escape(s)}</td></tr>"
                for t, a, s in DEMO_SCRIPT)
    return (f'<section class="appendix" id="app-a"><div class="app-kicker">附录 A</div><h2>术语表</h2>'
            f'<table class="gloss"><tbody>{g}</tbody></table></section>'
            f'<section class="appendix" id="app-b"><div class="app-kicker">附录 B</div><h2>命令速查</h2>'
            f'<p class="muted">均在 <code>cbl/</code> 目录下执行。</p><table class="cmds"><tbody>{c}</tbody></table></section>'
            f'<section class="appendix" id="app-c"><div class="app-kicker">附录 C</div><h2>五分钟演示脚本</h2>'
            f'<p class="muted">左列是建议的时间点，右列是可以直接照着讲的话。提前打开实验台，'
            f'把 <code>?budget=7200</code>、<code>?budget=6000</code>、<code>?budget=1700</code> 存成书签。</p>'
            f'<table class="demo"><thead><tr><th>时间</th><th>操作</th><th>讲解</th></tr></thead><tbody>{d}</tbody></table></section>')


# ---------- Markdown → 章节 HTML ----------

def convert_md():
    text = open(MD, encoding="utf-8").read()
    text = "\n".join(l for l in text.split("\n") if not l.startswith("[0. 所有人先看]"))
    text = text.replace("- [ ] ", "- ☐ ")
    head, *secs = re.split(r"\n## ", text)
    intro = re.sub(r"^> ?", "", head.split("\n", 1)[1], flags=re.M)   # 去掉一级标题与引用符号
    md = lambda s: markdown.markdown(s, extensions=["tables", "fenced_code", "codehilite"],  # noqa: E731
                                     extension_configs={"codehilite": {"css_class": "hl", "guess_lang": False}})
    out = []
    for raw in secs:
        title, body = raw.split("\n", 1)
        title = re.sub(r"^\d+\.\s*", "", title)        # 去掉 Markdown 标题自带的"0. "，章号统一由横幅给出
        body = re.sub(r"\n---\s*$", "", body.strip())
        out.append((title.strip(), md(body)))
    return md(intro), out


def chapter_html(idx, title, body_html, color, tint):
    soup = BeautifulSoup(body_html, "html.parser")

    def before_h3(word, fragment):
        h = next((h for h in soup.find_all("h3") if word in h.get_text()), None)
        if h is not None:
            h.insert_before(BeautifulSoup(fragment, "html.parser"))

    if idx in OVERVIEW:                      # "核心代码导读"作为一个小节，插在"动手验证"之前
        before_h3("动手验证", '<h3>核心代码导读</h3><p class="muted">以下代码取自提交 '
                  f'<code>{COMMIT}</code>，左侧是文件里的真实行号。先读每段下面的说明，再看代码。</p>'
                  + "".join(excerpts_for(idx)))
    if idx == 0:
        first_table = soup.find("table")
        if first_table:
            first_table.insert_before(BeautifulSoup(img_figure(ARCH, "图 0-1　CBL 系统总体框架：上半部分为编译期，下半部分为运行期"), "html.parser"))
    if idx == 3:
        before_h3("核心代码导读", squeeze_figure())
    if idx == 4:
        before_h3("设计决定", img_figure(DEMO, "图 4-1　预算实验台：可用额度调到 6000 时，tool_output 被整块舍弃、chat_history 被压缩"))
    # 所有插入完成后统一按文档顺序编号：编号既用于目录，也让"阅读顺序"等重名小节在全文唯一（定位页码靠它）
    toc = []
    for k, h3 in enumerate(soup.find_all("h3"), 1):
        h3.string = f"{idx}.{k}　{h3.get_text()}"
        h3["id"] = f"s{idx}-{k}"
        toc.append((h3.get_text(), h3["id"]))
    who, _, topic = title.partition("：")
    kicker = f"第 {idx} 章"
    heading = (f'<div class="banner" style="--c:{color};--t:{tint}"><div class="kicker">{kicker}</div>'
               f'<h2 id="c{idx}">{html.escape(who if topic else title)}</h2>'
               + (f'<div class="topic">{html.escape(topic)}</div>' if topic else "") + "</div>")
    ov = overview_box(idx, color, tint) if idx in OVERVIEW else ""
    return f'<section class="chapter" style="--c:{color};--t:{tint}">{heading}{ov}{soup}</section>', toc


# ---------- 页面 ----------

CSS = r"""
@page { size: A4; margin: 20mm 17mm 18mm 17mm;
  @top-left { content: "CBL 代码审阅指南"; font: 8.5pt "Noto Sans SC"; color: #9aa3b5; }
  @top-right { content: "提交 COMMIT · rovan666/cbl"; font: 8.5pt "Noto Sans SC"; color: #9aa3b5; }
  @bottom-center { content: counter(page) " / " counter(pages); font: 9pt "Noto Sans SC"; color: #7a8396; } }
@page cover { margin: 0; @top-left { content: none; } @top-right { content: none; } @bottom-center { content: none; } }
* { box-sizing: border-box; }
html { font-size: 10.4pt; }
body { margin: 0; font-family: "Noto Sans SC", "Microsoft YaHei", sans-serif; color: #1d2433; line-height: 1.75;
       -webkit-print-color-adjust: exact; print-color-adjust: exact; }
a { color: #175cd3; text-decoration: none; }
code { font-family: Consolas, "Cascadia Mono", monospace; font-size: .9em; background: #f1f3f7; padding: .05em .35em; border-radius: 3px; }
p { margin: .45em 0 .7em; text-align: justify; }
ul, ol { margin: .3em 0 .8em; padding-left: 1.5em; } li { margin: .22em 0; }
strong, b { font-weight: 700; }
h3 { font-size: 13.2pt; margin: 1.5em 0 .55em; padding-bottom: .25em; border-bottom: 2px solid var(--t, #eef0f4);
     color: var(--c, #1d2433); break-after: avoid; }
h3 + * { break-before: avoid; }
.muted { color: #6b7488; font-size: .95em; }

/* 封面 */
.cover { page: cover; height: 100vh; overflow: hidden; display: flex; flex-direction: column; padding: 34mm 22mm 20mm;
         background: linear-gradient(160deg, #0f1524 0%, #1b2847 62%, #24396b 100%); color: #fff; break-after: page; }
.cover .tag { font-size: 10.5pt; letter-spacing: .3em; color: #9db7ff; }
.cover h1 { font-size: 40pt; line-height: 1.2; margin: 10mm 0 4mm; font-weight: 800; letter-spacing: .02em; }
.cover .sub { font-size: 15pt; color: #c9d3ea; }
.cover .lead { margin-top: 12mm; font-size: 11pt; color: #dfe5f3; max-width: 150mm; line-height: 1.9; }
.cover .team { margin-top: auto; display: grid; grid-template-columns: repeat(4, 1fr); gap: 5mm; }
.cover .m { border-top: 3px solid var(--c); padding-top: 3mm; }
.cover .m .n { font-size: 14pt; font-weight: 700; }
.cover .m .r { font-size: 9.5pt; color: #b9c4dc; line-height: 1.6; margin-top: 1mm; }
.cover .meta { margin-top: 12mm; font-size: 9pt; color: #94a0bd; display: flex; justify-content: space-between; border-top: 1px solid #34446b; padding-top: 4mm; }

/* 目录 */
.toc { break-after: page; }
.toc h2 { font-size: 22pt; margin: 0 0 4mm; }
.toc .intro { background: #f5f7fb; border-left: 4px solid #2856d9; padding: 2.5mm 5mm; border-radius: 0 6px 6px 0; margin-bottom: 4mm; font-size: 9.4pt; line-height: 1.65; }
.toc .intro p { margin: .3em 0; }
.toc .l1 a, .toc .l2 a { display: flex; align-items: baseline; color: inherit; }   /* 只作用于目录条目，导语里的普通链接保持行内 */
.toc a .t { flex: 0 1 auto; } .toc a .dots { flex: 1; border-bottom: 1.5px dotted #c3c9d6; margin: 0 2mm; transform: translateY(-3px); }
.toc a .p { flex: 0 0 auto; font-variant-numeric: tabular-nums; color: #4a5468; min-width: 7mm; text-align: right; }
.toc .l1 { font-size: 11pt; font-weight: 700; margin-top: 2.2mm; }
.toc .l1 .c { display: inline-block; width: 9mm; height: 4.6mm; border-radius: 2px; margin-right: 3mm; background: var(--c); transform: translateY(1px); }
.toc .l2 { font-size: 9.4pt; color: #4a5468; margin-left: 12mm; line-height: 1.6; }

/* 章首 */
.chapter { break-before: page; }
.banner { background: var(--t); border-left: 7px solid var(--c); border-radius: 0 10px 10px 0; padding: 5mm 7mm 5mm; margin-bottom: 6mm; }
.banner .kicker { font-size: 9.5pt; letter-spacing: .25em; color: var(--c); font-weight: 700; }
.banner h2 { font-size: 24pt; margin: 1mm 0 0; line-height: 1.25; color: #121826; }
.banner .topic { font-size: 13pt; color: #3d465a; margin-top: 1mm; }
.overview { border: 1.5px solid var(--c); border-radius: 10px; padding: 4mm 6mm; margin: 0 0 6mm; break-inside: avoid; }
.overview b { color: var(--c); display: block; font-size: 10pt; margin-bottom: 1mm; }
.ov-files { font-family: Consolas, monospace; font-size: 9.5pt; padding-bottom: 3mm; margin-bottom: 3mm; border-bottom: 1px dashed #d5dae3; }
.ov-files b { font-family: "Noto Sans SC"; }
.ov-cols { display: grid; grid-template-columns: 1.35fr 1fr; gap: 7mm; }
.ov-cols ol { margin: 0; padding-left: 1.3em; font-size: 9.8pt; }

/* 引言块 */
blockquote { margin: 0 0 5mm; padding: 3mm 5mm; background: #f5f7fb; border-left: 4px solid #2856d9; border-radius: 0 6px 6px 0; }
blockquote p { margin: .3em 0; }

/* 表格 */
table { width: 100%; border-collapse: collapse; margin: 3mm 0 5mm; font-size: 9.6pt; line-height: 1.6; }
thead { display: table-header-group; }
th { background: var(--t, #eef0f4); color: #121826; text-align: left; padding: 2mm 3mm; border-bottom: 2px solid var(--c, #c3c9d6); }
td { padding: 2mm 3mm; border-bottom: 1px solid #e6e9ef; vertical-align: top; }
tr { break-inside: avoid; }
tbody tr:nth-child(even) td { background: #fafbfc; }
td:first-child { font-weight: 600; width: 32%; }

/* 代码块（Markdown 里的命令示例） */
div.hl, pre { break-inside: avoid; }
div.hl pre, pre { background: #f6f8fa; color: #1d2433; border: 1px solid #e3e6ec; padding: 3.5mm 4.5mm; border-radius: 7px; font: 8.8pt/1.6 Consolas, monospace;
                  white-space: pre-wrap; word-break: break-all; margin: 2mm 0 4mm; }
div.hl pre code, pre code { background: none; padding: 0; color: inherit; font-size: 1em; }

/* 代码摘录 */
figure.code { margin: 4mm 0 6mm; border: 1px solid #dfe3ea; border-radius: 8px; overflow: hidden; break-inside: avoid; }
figure.code.long { break-inside: auto; overflow: visible; }
/* 代码摘录是"行号列 + 代码列"的单行表格：必须解除下面通用的 tr 防断行，否则长段整体挪页 */
figure.code.long tr { break-inside: auto; }
figure.code pre { orphans: 5; widows: 5; }
figure.code figcaption { break-after: avoid; }
figure.code .note { break-before: avoid; }
figure.code figcaption { display: flex; gap: 4mm; align-items: baseline; background: #f4f6f9; padding: 1.8mm 4mm; font-size: 8.8pt; border-bottom: 1px solid #e3e6ec; }
figure.code .path { font-family: Consolas, monospace; font-weight: 700; color: #1d2433; }
figure.code .lines { color: #7a8396; } figure.code figcaption a { margin-left: auto; font-size: 8.5pt; }
figure.code table.hltable { margin: 0; font-size: 8.4pt; }
figure.code table.hltable td { padding: 0; border: 0; background: #fff !important; width: auto; font-weight: 400; }
figure.code td.linenos { background: #f7f8fa !important; border-right: 1px solid #e6e9ef; }
figure.code td.linenos pre, figure.code td.code pre { background: transparent; color: #1d2433; border-radius: 0; margin: 0; padding: 2.5mm 3mm;
                  font: 8.4pt/1.55 Consolas, monospace; white-space: pre; word-break: normal; }
figure.code td.linenos pre { color: #a0a8b8; text-align: right; }
figure.code td.code { width: 100%; }
figure.code .note { background: var(--t, #f5f7fb); border-top: 1px solid #e3e6ec; padding: 2.5mm 4mm; font-size: 9.4pt; line-height: 1.7; }
figure.code .note code { background: rgba(255,255,255,.7); }

/* 插图 */
figure.fig { margin: 4mm 0 6mm; text-align: center; break-inside: avoid; }
figure.fig img { max-width: 100%; max-height: 118mm; border: 1px solid #e3e6ec; border-radius: 6px; }
figure.fig figcaption { font-size: 9pt; color: #5d6678; margin-top: 2mm; text-align: center; line-height: 1.6; }
.sq-fig { border: 1px solid #e3e6ec; border-radius: 8px; padding: 4mm 5mm 3mm; text-align: left; }
.sq-row { display: grid; grid-template-columns: 30mm 1fr; align-items: center; margin: 2mm 0 5mm; }
.sq-lbl { font-size: 9.5pt; font-weight: 700; }
.sq-bar { position: relative; display: flex; height: 9mm; border-radius: 5px; overflow: visible; background: #f0f2f5; }
.sq { height: 100%; border-right: 2px solid #fff; display: flex; align-items: center; padding-left: 2mm; font-size: 8pt; font-weight: 700; color: #fff; overflow: hidden; white-space: nowrap; }
.sq.must { background: #b42318; } .sq.high { background: #b54708; } .sq.medium { background: #175cd3; } .sq.low { background: #6941c6; }
.sq.slack { background: #fff; } .sq.reserve { background: repeating-linear-gradient(135deg, #e3e7ee 0 5px, #f5f6f9 5px 10px); color: #7a8396; font-weight: 500; }
.sq-b { position: absolute; top: -4.5mm; bottom: -1.5mm; border-left: 2px dashed #1d2433; padding-left: 1.5mm; font-size: 8pt; font-weight: 700; line-height: 1; }
.sq-key { font-size: 8.5pt; color: #4a5468; } .sq-key i { display: inline-block; width: 3.2mm; height: 3.2mm; border-radius: 1px; margin: 0 1mm 0 3mm; vertical-align: -.4mm; }
.sq-key i.must { background: #b42318; } .sq-key i.high { background: #b54708; } .sq-key i.medium { background: #175cd3; } .sq-key i.low { background: #6941c6; }
.sq-key i.reserve { background: repeating-linear-gradient(135deg, #cfd5df 0 2px, #f5f6f9 2px 4px); }

/* 附录 */
.appendix { break-before: page; }
.app-kicker { font-size: 9.5pt; letter-spacing: .25em; color: #2856d9; font-weight: 700; }
.appendix h2 { font-size: 22pt; margin: 1mm 0 4mm; }
table.gloss td:first-child { width: 26%; }
table.cmds td:first-child { width: 50%; font-weight: 400; } table.cmds code { background: none; padding: 0; color: #121826; }
table.demo td:first-child { width: 12mm; } table.demo td:nth-child(2) { width: 36%; font-weight: 400; } td.t { font-variant-numeric: tabular-nums; color: #2856d9; }
"""


def build_html(toc_pages=None):
    intro, secs = convert_md()
    chapters, toc = [], []
    for (title, body), (idx, key, color, tint) in zip(secs, CHAPTERS):
        assert key in title, f"章节顺序与 CHAPTERS 不一致：{title}"
        h, sub = chapter_html(idx, title, body, color, tint)
        chapters.append(h)
        toc.append((1, f"{idx}　{title}", f"c{idx}", color, f"第 {idx} 章"))
        for label, anchor in (sub if idx in OVERVIEW else []):
            toc.append((2, label, anchor, color, label))
    for key, name in (("a", "术语表"), ("b", "命令速查"), ("c", "五分钟演示脚本")):
        toc.append((1, f"附录 {key.upper()}　{name}", f"app-{key}", "#2856d9", f"附录 {key.upper()}"))

    def p(i):
        return str(toc_pages[i]) if toc_pages else "00"
    toc_html = "".join(
        f'<div class="l{lv}"><a href="#{a}">' + (f'<span class="c" style="--c:{c}"></span>' if lv == 1 else "")
        + f'<span class="t">{html.escape(t)}</span><span class="dots"></span><span class="p">{p(i)}</span></a></div>'
        for i, (lv, t, a, c, _) in enumerate(toc))
    today = datetime.date.today().strftime("%Y 年 %m 月 %d 日")
    members = [("徐同帅", "词法分析 · 语法分析", "#4f8bff"), ("舒若凡", "语义检查 · 中间表示 · 负责人", "#a58bf0"),
               ("杨晨", "预算执行引擎", "#f0a35e"), ("祝梦倩", "审计报告 · 网页演示 · 测试", "#4cc38a")]
    team = "".join(f'<div class="m" style="--c:{c}"><div class="n">{n}</div><div class="r">{r}</div></div>' for n, r, c in members)
    cover = (f'<section class="cover"><div class="tag">CBL · CONTEXT BUDGET LANGUAGE</div>'
             f'<h1>代码审阅指南</h1><div class="sub">上下文预算语言 · 答辩前的模块阅读与问答准备</div>'
             f'<div class="lead">每人一章：先读什么、为什么这样设计、怎么亲手验证、可能被问什么、局限在哪。'
             f'代码摘录与链接全部固定在提交 {COMMIT}，与仓库逐行一致；文中每条命令都实际跑过。</div>'
             f'<div class="team">{team}</div>'
             f'<div class="meta"><span>仓库 github.com/rovan666/cbl · 提交 {COMMIT} · 测试 54/54 通过</span><span>{today}</span></div></section>')
    css = CSS.replace("COMMIT", COMMIT) + HtmlFormatter(style="xcode").get_style_defs(".hl")
    doc = (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>CBL 代码审阅指南</title>'
           f'<style>{css}</style></head><body>{cover}'
           f'<section class="toc"><h2>目录</h2><div class="intro">{intro}</div>{toc_html}</section>'
           + "".join(chapters) + appendix_html() + "</body></html>")
    return doc, toc


def print_pdf(doc, pdf_path):
    tmp = tempfile.mkdtemp(prefix="cbl_guide_")
    src = os.path.join(tmp, "guide.html")
    with open(src, "w", encoding="utf-8") as f:
        f.write(doc)
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--virtual-time-budget=4000", f"--print-to-pdf={pdf_path}", "file:///" + src.replace(os.sep, "/")],
                   check=True, capture_output=True)
    shutil.rmtree(tmp, ignore_errors=True)


def locate(pdf_path, toc):
    """目录各项所在页：章用"第 n 章"字样（只出现在章首横幅，不在目录里），小节用唯一编号标题，按文档顺序向后找。"""
    d = pymupdf.open(pdf_path)
    texts = [pg.get_text() for pg in d]
    d.close()
    pages, cur = [], 1                       # 跳过封面；首项是"第 0 章"，它只出现在章首，所以会越过目录页
    for lv, title, anchor, color, needle in toc:
        k = next((i for i in range(cur, len(texts)) if needle.replace("　", "") in texts[i].replace("　", "").replace(" ", "")
                  or needle in texts[i]), None)
        if k is None:
            raise SystemExit(f"定位失败：{needle}")
        pages.append(k + 1)
        cur = k
    return pages


def main():
    if not os.path.exists(EDGE):
        raise SystemExit("找不到 Microsoft Edge")
    tmp_pdf = os.path.join(tempfile.gettempdir(), "cbl_guide_pass.pdf")
    doc, toc = build_html()
    print_pdf(doc, tmp_pdf)
    pages = locate(tmp_pdf, toc)
    for _ in range(3):                       # 填入页码后再排，直到页码稳定
        doc, toc = build_html(pages)
        print_pdf(doc, tmp_pdf)
        again = locate(tmp_pdf, toc)
        if again == pages:
            break
        pages = again
    d = pymupdf.open(tmp_pdf)
    d.set_toc([[lv, re.sub(r"\s+", " ", t), pg] for (lv, t, *_), pg in zip(toc, pages)])
    d.set_metadata({"title": "CBL 代码审阅指南", "author": "CBL 项目组", "subject": "上下文预算语言 · 答辩前的模块阅读与问答准备",
                    "keywords": "CBL, 编译原理, DSL, 代码审阅", "creator": "docs/make_guide_pdf.py"})
    d.save(OUT, garbage=3, deflate=True)
    n = len(d)
    d.close()
    os.remove(tmp_pdf)
    print(f"已生成 {OUT}（{n} 页，{os.path.getsize(OUT) // 1024} KB）")


if __name__ == "__main__":
    sys.exit(main())
