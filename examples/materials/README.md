# 示例材料（医疗咨询助手）

`python -m cbl run examples/medical_assistant.cbl` 缺省读取本目录。

> 演示用合成材料：医学内容为通用科普常识，**不构成医疗建议**；工具输出为虚构数据。

| 文件 | 对应 block / 用途 | 估算用量（cap） | 演示的行为 |
|---|---|---|---|
| `prompts/medical.system.md` | system_prompt | 1238（1500） | must_keep，完整保留 |
| `profile/allergy.md` | allergy_notes | 92（300） | must_keep，完整保留 |
| `kb/medical_kb.txt` | retrieved_docs | 4774（3200） | rerank_drop：24 段中混有 9 段与提问无关 |
| `session_history.json` | chat_history（内置来源 session_history） | 2270（1600） | summarize：8 轮，保留最近 4 轮原文 |
| `last_tool_result.txt` | tool_output（内置来源 last_tool_result） | 658（500） | truncate_tail |
| `query.txt` | 本轮用户提问 | — | rerank_drop 与摘要的相关度依据 |

字符串来源（带引号的路径）相对本目录解析；内置来源按文件名加载
（`system_prompt.txt` / `session_history.json` / `last_tool_result.txt`）。

**已知局限**：rerank_drop 用 BM25 + 中文二字组合做字面匹配，识别不了同义表达。
例如提问说"嗓子痛""发烧"，资料写"咽痛""发热"，相关段落可能得分偏低（本例中
"咽拭子检测"一段就被误丢）。改进方向：同义词表、或接入向量检索（可插拔，见 engine.py）。
