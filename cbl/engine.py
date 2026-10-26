# -*- coding: utf-8 -*-
"""CBL 预算执行引擎（骨架 / TODO）。

职责：读入 JSON 组装计划（IR）+ 真实上下文材料，输出最终 Prompt。
执行三步走（计划书 3 节④、4.1 节运行期语义 ⓐ~ⓔ）：
    1. 硬性放入所有 must_keep 块（其 overflow 恒为 error，超额即拒绝组装）；
    2. 确定其余块的有效额度：可用额度 B 缺省为 window×margin，调用方可调小；
       Σcap 超出 B 时按 low → medium → high 次序压缩（同级按 cap 等比例），
       压缩到 0 即整块舍弃；未用满的额度不回流；
    3. 实际用量超出有效额度的块执行声明的 overflow 策略；
最终 Prompt 按块的声明顺序拼接；token 估算宁多勿少。

负责人：杨晨
"""


def estimate_tokens(text: str) -> int:
    """极简 token 估算：约 4 字符 ≈ 1 token（英文）。
    TODO(杨晨)：中文场景可按字符数加权；如需精确可接 tiktoken。"""
    return max(1, len(text) // 4)


def apply_overflow(text: str, cap: int, strategy: str, keep_recent: int = 0) -> str:
    """超限策略接口。五种策略逐个实现：
    - truncate_tail：从尾部截断到 cap（最简单，先做）
    - sliding_window：保留开头 + 最近 keep_recent 段
    - rerank_drop：以本轮用户提问为查询，按关键词重叠度/BM25 给段落打分，丢弃最低分段落
    - summarize：可插拔摘要接口，默认规则式（首句+关键词句）
    - error：不裁剪，直接抛异常让上层发现预算被击穿
    TODO(杨晨)
    """
    raise NotImplementedError("待实现：" + strategy)


def assemble(plan: dict, materials: dict) -> str:
    """plan = IR；materials = {块名: 原始文本}。返回最终 Prompt。
    TODO(杨晨)：实现三步走，并把每块的裁剪动作记录下来交给 report 模块。"""
    raise NotImplementedError("预算执行引擎待实现")
