# -*- coding: utf-8 -*-
"""CBL 预算执行引擎：JSON 组装计划（IR）+ 上下文材料 → 最终 Prompt + 审计记录。

对应计划书 3 节④与 4.1 节运行期语义 ⓐ~ⓔ，三步走：
    1. 确定可用额度 B（缺省 window×margin，调用方可调小）；must_keep 总额超过 B 即拒绝组装；
    2. 按优先级确定各块有效额度（ⓑ）：Σcap 超过 B 时按 low → medium → high 逐级压缩，
       同级按 cap 等比例，压到 0 即整块舍弃；must_keep 不参与压缩；未用满的额度不回流；
    3. 读取材料、估算用量，超出有效额度的块执行声明的 overflow 策略并记录动作；
       must_keep 块的 overflow 恒为 error（约束⑨），超额即拒绝组装（ⓐ）。
最后按声明顺序拼接（ⓓ），求值运行期断言。token 计数宁多勿少（ⓔ）。

负责人：杨晨
"""
import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass, field

SQUEEZE_ORDER = ("low", "medium", "high")      # 额度不足时的压缩次序（ⓑ）
BUILTIN_FILES = {                               # 从材料目录加载内置来源时的文件名
    "system_prompt": "system_prompt.txt",
    "session_history": "session_history.json",
    "last_tool_result": "last_tool_result.txt",
}
ROLE_LABELS = {"user": "用户", "assistant": "助手"}
BLOCK_SEP = "\n\n"        # 块与块之间的分隔；开销极小，由 margin 预留覆盖
SENTENCE_END = "。！？!?\n"


class AssemblyError(Exception):
    """拒绝组装：must_keep 超额、overflow 为 error 的块超额、error 级断言不成立等。
    audit 为截至出错时的审计记录（status = "rejected"），便于报告说明原因。"""

    def __init__(self, msg, audit):
        super().__init__(msg)
        self.audit = audit


# ---------- token 计数（ⓔ 保守估算，可插拔） ----------

_WORD = re.compile(r"[A-Za-z0-9_]+")


def estimate_tokens(text: str) -> int:
    """保守 token 估算，宁多勿少：
    - 中日韩等全角字符：每字 1.5（主流分词器约 0.7~1.5，取上沿）
    - 连续英文/数字：每 3 字符 1 个（英文平均约 4 字符/token，取偏多）
    - 其他符号与换行各 1 个；空格不计（通常并入相邻词）
    对任意前缀单调不减，truncate 系列策略依赖这一点做二分查找。
    需要精确计数时，可给 assemble(counter=...) 传入真实分词器（如 tiktoken）。"""
    total, wide, i, n = 0, 0, 0, len(text)
    while i < n:
        m = _WORD.match(text, i)
        if m:
            total += math.ceil(len(m.group()) / 3)
            i = m.end()
            continue
        ch = text[i]
        if unicodedata.east_asian_width(ch) in "WF":
            wide += 1
        elif ch == "\n" or not ch.isspace():
            total += 1
        i += 1
    return total + math.ceil(wide * 1.5)


def _fit_prefix(text, limit, counter):
    """不超过 limit 的最长前缀长度（二分查找）。"""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if counter(text[:mid]) <= limit:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _fit_suffix(text, limit, counter):
    """不超过 limit 的最长后缀的起点。"""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi) // 2
        if counter(text[mid:]) <= limit:
            hi = mid
        else:
            lo = mid + 1
    return lo


def _soft_cut(text, k):
    """截断点尽量落在句末：在前缀后 20% 范围内找最后一个句末标点。"""
    for j in range(k, int(k * 0.8), -1):
        if text[j - 1] in SENTENCE_END:
            return j
    return k


# ---------- 运行期输入与材料 ----------

@dataclass
class Context:
    """运行期输入。
    root：字符串来源（文件路径）的根目录；builtins：内置来源名 → 文本，
    其中 session_history 为消息列表 [{"role": "user"/"assistant", "content": ...}]；
    query：本轮用户提问（rerank_drop 与摘要据此判断相关度）；
    budget：本次可用额度 B，None 表示缺省 window×margin。"""
    root: str = "."
    builtins: dict = field(default_factory=dict)
    query: str = ""
    budget: int = None

    @classmethod
    def from_dir(cls, path, query=None, budget=None):
        """从材料目录加载：内置来源按 BUILTIN_FILES 取文件，提问缺省读 query.txt。"""
        builtins = {}
        for name, fname in BUILTIN_FILES.items():
            fp = os.path.join(path, fname)
            if os.path.exists(fp):
                with open(fp, encoding="utf-8") as f:
                    builtins[name] = json.load(f) if fname.endswith(".json") else f.read()
        if query is None:
            qp = os.path.join(path, "query.txt")
            query = open(qp, encoding="utf-8").read().strip() if os.path.exists(qp) else ""
        return cls(root=path, builtins=builtins, query=query, budget=budget)


def _render_turns(messages):
    """消息列表 → 轮次列表；一轮 = 一条用户消息 + 其后的助手回复（ⓒ）。"""
    turns, cur = [], []
    for m in messages:
        if m["role"] == "user" and cur:
            turns.append("\n".join(cur))
            cur = []
        cur.append(f"{ROLE_LABELS.get(m['role'], m['role'])}：{m['content']}")
    if cur:
        turns.append("\n".join(cur))
    return turns


def load_material(block, ctx):
    """返回 (units, sep, unit_name)；来源缺失返回 None。
    会话历史按轮切分，其余文本按空行分段——它们是裁剪策略的最小单位。"""
    src = block["source"]
    if block["source_kind"] == "string":
        fp = os.path.join(ctx.root, src)
        if not os.path.exists(fp):
            return None
        with open(fp, encoding="utf-8") as f:
            raw = f.read()
    else:
        if src not in ctx.builtins:
            return None
        raw = ctx.builtins[src]
    if isinstance(raw, list):
        return _render_turns(raw), "\n", "轮"
    paras = [p.strip() for p in re.split(r"\n\s*\n", raw.strip()) if p.strip()]
    return paras, "\n\n", "段"


# ---------- 第 2 步：有效额度（ⓑ） ----------

def allocate(blocks, budget):
    """返回 {块名: 有效额度}；must_keep 总额超过 budget 时抛 ValueError。"""
    eff = {b["name"]: b["cap"] for b in blocks}
    must = sum(b["cap"] for b in blocks if b["priority"] == "must_keep")
    if must > budget:
        raise ValueError(f"must_keep 块额度之和 {must} 超过本次可用额度 {budget}")
    excess = sum(eff.values()) - budget
    for level in SQUEEZE_ORDER:
        if excess <= 0:
            break
        group = [b for b in blocks if b["priority"] == level]
        total = sum(b["cap"] for b in group)
        if total == 0:
            continue
        cut = min(excess, total)
        _proportional(group, total - cut, eff)
        excess -= cut
    return eff


def _proportional(group, keep, eff):
    """同级按 cap 等比例分配 keep；最大余数法取整，保证总和恰为 keep（同余数按声明顺序）。"""
    total = sum(b["cap"] for b in group)
    exact = [b["cap"] * keep / total for b in group]
    floors = [math.floor(x) for x in exact]
    rest = keep - sum(floors)
    order = sorted(range(len(group)), key=lambda i: -(exact[i] - floors[i]))
    for i in order[:rest]:
        floors[i] += 1
    for b, v in zip(group, floors):
        eff[b["name"]] = v


# ---------- 第 3 步：五种超限策略 ----------
# 统一签名：(units, sep, limit, block, ctx, counter, summarizer) → (最终文本, 动作说明)

def truncate_tail(units, sep, limit, block, ctx, counter, summarizer):
    text = sep.join(units)
    k = _soft_cut(text, _fit_prefix(text, limit, counter))
    out = text[:k].rstrip()
    return out, f"截断尾部 {counter(text) - counter(out)} token"


def sliding_window(units, sep, limit, block, ctx, counter, summarizer):
    """从最新往前整单位保留（最多 keep_recent 个）；一个都放不下时保留最新单位的末尾。"""
    unit_name = "轮" if sep == "\n" else "段"
    cap_n = block["keep_recent"] or len(units)
    kept = []
    for u in reversed(units):
        if len(kept) >= cap_n or counter(sep.join([u] + kept)) > limit:
            break
        kept.insert(0, u)
    if not kept:
        last = units[-1]
        out = last[_fit_suffix(last, limit, counter):]
        return out, f"最新一{unit_name}也超额，只保留其末尾 {counter(out)} token"
    return sep.join(kept), (f"保留最近 {len(kept)} {unit_name}，"
                            f"丢弃较早的 {len(units) - len(kept)} {unit_name}")


def summarize(units, sep, limit, block, ctx, counter, summarizer):
    """最近 keep_recent 个单位保留原文，更早的交给 summarizer 压缩成摘要放在前面。"""
    unit_name = "轮" if sep == "\n" else "段"
    n = min(block["keep_recent"] or 2, len(units))
    recent, earlier = units[len(units) - n:], units[:len(units) - n]
    if counter(sep.join(recent)) > limit:            # 原文都放不下：退化为滑动窗口
        out, detail = sliding_window(units, sep, limit, block, ctx, counter, summarizer)
        return out, "最近原文已超额，退化为滑动窗口：" + detail
    room = limit - counter(sep.join(recent) + sep)
    summary = "【早期对话摘要】" + summarizer(earlier, ctx.query) if earlier else ""
    if summary and counter(summary) > room:
        summary = summary[:_soft_cut(summary, _fit_prefix(summary, room, counter))].rstrip()
    if not summary or counter(summary) < 8:          # 剩余空间太小，摘要没有意义
        return sep.join(recent), f"保留最近 {n} {unit_name}原文，早期 {len(earlier)} {unit_name}舍弃"
    return summary + sep + sep.join(recent), (
        f"保留最近 {n} {unit_name}原文，早期 {len(earlier)} {unit_name}压缩为摘要（{counter(summary)} token）")


def rerank_drop(units, sep, limit, block, ctx, counter, summarizer):
    """以本轮提问为查询做 BM25 打分，按分数从低到高整段丢弃，剩余段落保持原顺序。"""
    if len(units) == 1:
        return truncate_tail(units, sep, limit, block, ctx, counter, summarizer)
    scores = bm25_scores(units, ctx.query)
    drop_order = sorted(range(len(units)), key=lambda i: (scores[i], -i))   # 同分先丢靠后的
    alive = set(range(len(units)))
    for i in drop_order:
        if counter(sep.join(units[j] for j in sorted(alive))) <= limit or len(alive) == 1:
            break
        alive.discard(i)
    kept = [units[j] for j in sorted(alive)]
    dropped = len(units) - len(kept)
    how = "相关度最低的" if ctx.query else "（无查询，按位置）末尾的"
    if counter(sep.join(kept)) > limit:              # 只剩一段仍超额：截断它
        out, detail = truncate_tail(kept, sep, limit, block, ctx, counter, summarizer)
        return out, f"丢弃{how} {dropped} 段，剩余一段再{detail}"
    return sep.join(kept), f"丢弃{how} {dropped} 段"


def error(units, sep, limit, block, ctx, counter, summarizer):
    raise _OverflowRejected(f"块 '{block['name']}' 实际用量 {counter(sep.join(units))} 超出"
                            f"有效额度 {limit}，其 overflow 为 error，拒绝组装")


class _OverflowRejected(Exception):
    pass


STRATEGIES = {"truncate_tail": truncate_tail, "sliding_window": sliding_window,
              "summarize": summarize, "rerank_drop": rerank_drop, "error": error}


# ---------- 相关度与摘要（可插拔的轻量实现） ----------

def terms(text):
    """检索词：英文/数字按词（小写），中文取相邻两字组合——零依赖，不需要分词器。"""
    out = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", text)]
    for run in re.findall(r"[一-鿿]+", text):
        out += [run[i:i + 2] for i in range(len(run) - 1)] or [run]
    return out


def bm25_scores(docs, query, k1=1.5, b=0.75):
    q = set(terms(query))
    if not q:
        return [0.0] * len(docs)
    toks = [terms(d) for d in docs]
    avg = sum(len(t) for t in toks) / len(toks) or 1
    df = {w: sum(1 for t in toks if w in t) for w in q}
    scores = []
    for t in toks:
        s = 0.0
        for w in q:
            f = t.count(w)
            if f:
                idf = math.log((len(docs) - df[w] + 0.5) / (df[w] + 0.5) + 1)
                s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(t) / avg))
        scores.append(s)
    return scores


MIN_SENTENCE = 8      # 短于此的句子（如"好的。"）不算有信息量
MIN_OVERLAP = 2       # 与提问至少共享这么多检索词，才算"相关句"


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[。！？!?])", text) if s.strip()]


def _key_sentence(text):
    """首个有信息量的句子；都很短时退回第一句。"""
    sents = _sentences(text)
    for s in sents:
        if len(s) >= MIN_SENTENCE:
            return s
    return sents[0] if sents else ""


def rule_summary(units, query):
    """规则式抽取摘要（计划书问题三：首句 + 关键词句）。
    对话轮次：用户与助手各取首个有信息量的句子；文本段落：取首个有信息量的句子。
    另补与本轮提问共享至少 MIN_OVERLAP 个检索词的句子。"""
    qt = set(terms(query))
    parts = []
    for u in units:
        lines = u.split("\n")
        picked = []
        for ln in lines:
            label, _, body = ln.partition("：") if ln[:3] in ("用户：", "助手：") else ("", "", ln)
            key = _key_sentence(body)
            if key:
                picked.append(f"{label}：{key}" if label else key)
            for s in _sentences(body):
                if s != key and len(qt & set(terms(s))) >= MIN_OVERLAP:
                    picked.append(s)
        parts.append(" ".join(picked))
    return " / ".join(p for p in parts if p)


# ---------- 运行期断言 ----------

def _bound(operand, window):
    if isinstance(operand, dict):
        if "percent" in operand:
            return window * operand["percent"] / 100
        return window * operand["window_scale"]
    return operand


def eval_rules(plan, eff):
    """total_reserved = Σcap（静态）；every_block_min_tokens = 有效额度最小值（动态）。"""
    results = []
    for r in plan["rules"]:
        if r["metric"] == "total_reserved":
            actual, where = sum(b["cap"] for b in plan["blocks"]), ""
        else:
            where = min(eff, key=eff.get)
            actual = eff[where]
        bound = _bound(r["operand"], plan["window"])
        ok = actual <= bound if r["op"] == "<=" else actual >= bound
        results.append({"name": r["name"], "metric": r["metric"], "actual": actual,
                        "op": r["op"], "bound": bound, "passed": ok,
                        "level": r["on_violation"], "where": where if not ok else ""})
    return results


# ---------- 组装 ----------

def assemble(plan: dict, ctx: Context, counter=estimate_tokens, summarizer=rule_summary):
    """返回 (最终 Prompt, 审计记录)；拒绝组装时抛 AssemblyError（带审计记录）。"""
    window = plan["window"]
    budget = ctx.budget if ctx.budget is not None else int(window * plan["margin"])
    audit = {"window": window, "budget": budget, "query": ctx.query, "status": "ok",
             "error": None, "total_used": 0, "blocks": [], "rules": []}

    def reject(msg):
        audit["status"], audit["error"] = "rejected", msg
        audit["total_used"] = sum(e["used"] for e in audit["blocks"])
        raise AssemblyError(msg, audit)

    try:
        eff = allocate(plan["blocks"], budget)                       # 第 2 步
    except ValueError as e:
        reject(str(e))

    texts = []
    for b in plan["blocks"]:                                         # 第 3 步
        entry = {"name": b["name"], "priority": b["priority"], "cap": b["cap"],
                 "effective": eff[b["name"]], "original": 0, "used": 0,
                 "action": "完整保留", "detail": ""}
        audit["blocks"].append(entry)
        mat = load_material(b, ctx)
        if mat is None:
            if b["priority"] == "must_keep":
                reject(f"must_keep 块 '{b['name']}' 的来源 '{b['source']}' 缺失，无法保证死保信息")
            entry.update(action="来源缺失", detail=f"来源 '{b['source']}' 不存在，按空内容处理")
            continue
        units, sep, _ = mat
        text = sep.join(units)
        entry["original"] = counter(text)
        limit = eff[b["name"]]
        if limit == 0:
            entry["action"] = "整块舍弃"
            entry["detail"] = "有效额度被压缩为 0"
            continue
        if entry["original"] > limit:
            try:
                text, detail = STRATEGIES[b["overflow"]](units, sep, limit, b, ctx,
                                                         counter, summarizer)
            except _OverflowRejected as e:
                entry.update(action="error", detail="超额，拒绝组装")
                reject(str(e))
            entry.update(action=b["overflow"], detail=detail)
        entry["used"] = counter(text)
        if text:
            texts.append(text)

    audit["total_used"] = sum(e["used"] for e in audit["blocks"])
    audit["rules"] = eval_rules(plan, eff)
    for r in audit["rules"]:
        if not r["passed"] and r["level"] == "error":
            reject(f"规则 '{r['name']}' 不成立（{r['metric']}={r['actual']} {r['op']} "
                   f"{r['bound']:g} 为假），on_violation 为 error，拒绝组装")
    return BLOCK_SEP.join(texts), audit                              # 按声明顺序拼接（ⓓ）
