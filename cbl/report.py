# -*- coding: utf-8 -*-
"""CBL 审计报告生成（骨架 / TODO）。

职责：把引擎记录的逐块分配/裁剪动作渲染成可存档的报告。
输出双格式：纯文本（课堂演示用）+ HTML（正式报告用）。

负责人：祝梦倩
"""


def render_text(audit: dict) -> str:
    """渲染纯文本审计报告。
    参考格式（计划书 5.x）：
        === CBL 组装审计报告 ===  window=8000  实际占用=7840 (98.0%)
        [must_keep] system_prompt  cap=1500  used=1432  完整保留
    TODO(祝梦倩)
    """
    raise NotImplementedError("文本报告待实现")


def render_html(audit: dict, out_path: str) -> None:
    """渲染 HTML 审计报告并写盘。TODO(祝梦倩)"""
    raise NotImplementedError("HTML 报告待实现")
