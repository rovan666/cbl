# -*- coding: utf-8 -*-
"""扩展点示例：给 CBL 引擎换上真实的 tokenizer 和 smarter 的摘要器。

引擎的两个可插拔参数（见 cbl/engine.py assemble/assemble_parts 签名）：
    counter=text -> int              token 计数器，缺省为保守估算 estimate_tokens
    summarizer=(units, query) -> str 摘要器，缺省为规则式抽取 rule_summary

本脚本演示：
  1. 若装了 tiktoken 就用它精确计数（没装则退回内置估算，保持零依赖可运行）；
  2. 一个调用本地 LLM 的 summarizer 骨架（此处用伪实现代替，真实场景换成你的
     API 调用即可——摘要器只需保证返回的文本尽量短于输入）。

运行（项目根目录）：python examples/plugin_demo.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cbl.cli import compile_file
from cbl.engine import Context, assemble, estimate_tokens
from cbl.report import render_text

ROOT = os.path.dirname(__file__)


def tiktoken_counter():
    """装了 tiktoken 就用真实分词器计数；没装就退回内置保守估算。"""
    try:
        import tiktoken
    except ImportError:
        print("（未安装 tiktoken，使用内置保守估算；pip install tiktoken 可换精确计数）\n")
        return estimate_tokens
    enc = tiktoken.get_encoding("cl100k_base")
    return lambda text: len(enc.encode(text))


def llm_summarizer(units, query):
    """LLM 摘要器骨架：真实场景在这里调用你的模型 API。
    契约：units 是被压缩的单位列表（对话轮次或文本段落），query 是本轮提问；
    返回一段尽量短于输入的摘要文本。引擎会再按剩余额度裁剪，超长也不怕。"""
    # response = your_llm.chat(f"围绕「{query}」摘要以下对话：\n" + "\n".join(units))
    # return response.text
    return f"（这里应是由 LLM 围绕「{query}」生成的 {len(units)} 个单位的摘要）"


def main():
    ir, diags = compile_file(os.path.join(ROOT, "medical_assistant.cbl"))
    if ir is None:
        sys.exit("\n".join(map(str, diags)))
    ctx = Context.from_dir(os.path.join(ROOT, "materials"))
    prompt, audit = assemble(ir, ctx, counter=tiktoken_counter(),
                             summarizer=llm_summarizer)
    print(render_text(audit))
    print("\n最终 Prompt 前 200 字符：\n" + prompt[:200])


if __name__ == "__main__":
    main()
