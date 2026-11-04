// 本文件由 docs/tutorial/build_data.py 用真实编译器生成，请勿手改；改了编译器行为后重跑该脚本即可。
window.TUTORIAL_DATA = {
 "tokens_demo": [
  {
   "src": "window 8000 ;",
   "tokens": [
    {
     "kind": "KEYWORD",
     "value": "window",
     "line": 1,
     "col": 1
    },
    {
     "kind": "INT",
     "value": "8000",
     "line": 1,
     "col": 8
    },
    {
     "kind": "SYMBOL",
     "value": ";",
     "line": 1,
     "col": 13
    },
    {
     "kind": "EOF",
     "value": "",
     "line": 1,
     "col": 14
    }
   ]
  },
  {
   "src": "block allergy_notes {\n    source: \"profile/allergy.md\" ;\n    cap: 300 ;\n}",
   "tokens": [
    {
     "kind": "KEYWORD",
     "value": "block",
     "line": 1,
     "col": 1
    },
    {
     "kind": "IDENT",
     "value": "allergy_notes",
     "line": 1,
     "col": 7
    },
    {
     "kind": "SYMBOL",
     "value": "{",
     "line": 1,
     "col": 21
    },
    {
     "kind": "KEYWORD",
     "value": "source",
     "line": 2,
     "col": 5
    },
    {
     "kind": "SYMBOL",
     "value": ":",
     "line": 2,
     "col": 11
    },
    {
     "kind": "STRING",
     "value": "profile/allergy.md",
     "line": 2,
     "col": 13
    },
    {
     "kind": "SYMBOL",
     "value": ";",
     "line": 2,
     "col": 34
    },
    {
     "kind": "KEYWORD",
     "value": "cap",
     "line": 3,
     "col": 5
    },
    {
     "kind": "SYMBOL",
     "value": ":",
     "line": 3,
     "col": 8
    },
    {
     "kind": "INT",
     "value": "300",
     "line": 3,
     "col": 10
    },
    {
     "kind": "SYMBOL",
     "value": ";",
     "line": 3,
     "col": 14
    },
    {
     "kind": "SYMBOL",
     "value": "}",
     "line": 4,
     "col": 1
    },
    {
     "kind": "EOF",
     "value": "",
     "line": 4,
     "col": 2
    }
   ]
  }
 ],
 "ast_demo": {
  "src": "window 8000 ;\nblock notes {\n    source: \"profile/allergy.md\" ;\n    cap: 300 ;\n    priority: must_keep ;\n}\nrule keep_enough {\n    assert: every_block_min_tokens >= 100 ;\n    on_violation: warn ;\n}\n",
  "tree": {
   "label": "Program",
   "children": [
    [
     "window",
     {
      "label": "WindowDecl",
      "line": 1,
      "detail": "tokens=8000 margin=0.9"
     }
    ],
    [
     "block",
     {
      "label": "BlockDecl «notes»",
      "line": 2,
      "detail": "source='profile/allergy.md' cap=300 priority=must_keep overflow=error"
     }
    ],
    [
     "rule",
     {
      "label": "RuleDecl «keep_enough»",
      "line": 7,
      "detail": "every_block_min_tokens >= 100 → warn"
     }
    ]
   ]
  }
 },
 "diag_demo": {
  "src": "window 8000 ;\nblock allergy_notes {\n    source: \"profile/allergy.md\" ;\n    cap: 300 ;\n    priority: must_keep ;\n    overflow: truncate_tail ;\n}\nblock chat_history {\n    source: chat_log ;\n    cap: 3000 ;\n    overflow: truncate_tail ;\n    keep_recent: 4 ;\n}\n",
  "diags": [
   {
    "level": "错误",
    "line": 2,
    "code": "E901",
    "text": "[错误] 行2 E901: 块 'allergy_notes' 为 must_keep，overflow 只能是 error（实际为 truncate_tail），死保信息不允许被任何策略裁剪"
   },
   {
    "level": "警告",
    "line": 8,
    "code": "W501",
    "text": "[警告] 行8 W501: 块 'chat_history' 声明了 keep_recent，但 overflow 为 truncate_tail；keep_recent 只对 summarize / sliding_window 有意义，将被忽略"
   },
   {
    "level": "错误",
    "line": 8,
    "code": "E601",
    "text": "[错误] 行8 E601: 块 'chat_history' 的来源 'chat_log' 不是内置来源标识符（可用：last_tool_result / session_history / system_prompt）；文件路径请用双引号括起"
   }
  ]
 },
 "syntax_recovery": {
  "src": "window 8000 ;\nblock a { source: \"a.txt\" ; cap: 100 }\nblock b { source: \"b.txt\" ; cap: ; }\n",
  "errors": [
   {
    "line": 2,
    "col": 37,
    "text": "语法错误 行2 列37: 期望 ';'（cap 条目结尾），实际读到 '}'（实际位于 行2 列38）"
   },
   {
    "line": 3,
    "col": 34,
    "text": "语法错误 行3 列34: cap 额度只接受 整数 / 整数% / window*数字，实际读到 ';'"
   }
  ]
 },
 "engine_scenes": {
  "7200": {
   "window": 8000,
   "budget": 7200,
   "query": "这两天嗓子特别痛，咽口水都疼，今天还发烧到 38.5 度。我对青霉素过敏，能吃什么抗生素吗？",
   "status": "ok",
   "error": null,
   "total_used": 6542,
   "blocks": [
    {
     "name": "system_prompt",
     "priority": "must_keep",
     "cap": 1500,
     "effective": 1500,
     "original": 1238,
     "used": 1238,
     "action": "完整保留",
     "detail": ""
    },
    {
     "name": "allergy_notes",
     "priority": "must_keep",
     "cap": 300,
     "effective": 300,
     "original": 92,
     "used": 92,
     "action": "完整保留",
     "detail": ""
    },
    {
     "name": "retrieved_docs",
     "priority": "high",
     "cap": 3200,
     "effective": 3200,
     "original": 4774,
     "used": 3145,
     "action": "rerank_drop",
     "detail": "丢弃相关度最低的 9 段"
    },
    {
     "name": "chat_history",
     "priority": "medium",
     "cap": 1600,
     "effective": 1600,
     "original": 2270,
     "used": 1590,
     "action": "summarize",
     "detail": "保留最近 4 轮原文，早期 4 轮压缩为摘要（404 token）"
    },
    {
     "name": "tool_output",
     "priority": "low",
     "cap": 500,
     "effective": 500,
     "original": 658,
     "used": 477,
     "action": "truncate_tail",
     "detail": "截断尾部 181 token"
    }
   ],
   "rules": [
    {
     "name": "budget_margin",
     "metric": "total_reserved",
     "actual": 7100,
     "op": "<=",
     "bound": 7200.0,
     "passed": true,
     "level": "error",
     "where": ""
    },
    {
     "name": "no_starvation",
     "metric": "every_block_min_tokens",
     "actual": 300,
     "op": ">=",
     "bound": 100,
     "passed": true,
     "level": "warn",
     "where": ""
    }
   ]
  },
  "6000": {
   "window": 8000,
   "budget": 6000,
   "query": "这两天嗓子特别痛，咽口水都疼，今天还发烧到 38.5 度。我对青霉素过敏，能吃什么抗生素吗？",
   "status": "ok",
   "error": null,
   "total_used": 5372,
   "blocks": [
    {
     "name": "system_prompt",
     "priority": "must_keep",
     "cap": 1500,
     "effective": 1500,
     "original": 1238,
     "used": 1238,
     "action": "完整保留",
     "detail": ""
    },
    {
     "name": "allergy_notes",
     "priority": "must_keep",
     "cap": 300,
     "effective": 300,
     "original": 92,
     "used": 92,
     "action": "完整保留",
     "detail": ""
    },
    {
     "name": "retrieved_docs",
     "priority": "high",
     "cap": 3200,
     "effective": 3200,
     "original": 4774,
     "used": 3145,
     "action": "rerank_drop",
     "detail": "丢弃相关度最低的 9 段"
    },
    {
     "name": "chat_history",
     "priority": "medium",
     "cap": 1600,
     "effective": 1000,
     "original": 2270,
     "used": 897,
     "action": "summarize",
     "detail": "最近原文已超额，退化为滑动窗口：保留最近 3 轮，丢弃较早的 5 轮"
    },
    {
     "name": "tool_output",
     "priority": "low",
     "cap": 500,
     "effective": 0,
     "original": 658,
     "used": 0,
     "action": "整块舍弃",
     "detail": "有效额度被压缩为 0"
    }
   ],
   "rules": [
    {
     "name": "budget_margin",
     "metric": "total_reserved",
     "actual": 7100,
     "op": "<=",
     "bound": 7200.0,
     "passed": true,
     "level": "error",
     "where": ""
    },
    {
     "name": "no_starvation",
     "metric": "every_block_min_tokens",
     "actual": 0,
     "op": ">=",
     "bound": 100,
     "passed": false,
     "level": "warn",
     "where": "tool_output"
    }
   ]
  },
  "1700": {
   "window": 8000,
   "budget": 1700,
   "query": "这两天嗓子特别痛，咽口水都疼，今天还发烧到 38.5 度。我对青霉素过敏，能吃什么抗生素吗？",
   "status": "rejected",
   "error": "must_keep 块额度之和 1800 超过本次可用额度 1700",
   "total_used": 0,
   "blocks": [],
   "rules": []
  }
 },
 "strategy_demos": {
  "units": [
   "用户：第1个问题，关于最近症状的描述。\n助手：第1个回答，给出了具体建议。",
   "用户：第2个问题，关于最近症状的描述。\n助手：第2个回答，给出了具体建议。",
   "用户：第3个问题，关于最近症状的描述。\n助手：第3个回答，给出了具体建议。",
   "用户：第4个问题，关于最近症状的描述。\n助手：第4个回答，给出了具体建议。",
   "用户：第5个问题，关于最近症状的描述。\n助手：第5个回答，给出了具体建议。",
   "用户：第6个问题，关于最近症状的描述。\n助手：第6个回答，给出了具体建议。"
  ],
  "limit": 120,
  "results": {
   "truncate_tail": {
    "detail": "截断尾部 220 token",
    "text": "用户：第1个问题，关于最近症状的描述。\n助手：第1个回答，给出了具体建议。\n用户：第2个问题，关于最近症状的描述。\n助手：第2个回答，给出了具体建议。",
    "tokens": 109
   },
   "sliding_window": {
    "detail": "保留最近 2 轮，丢弃较早的 4 轮",
    "text": "用户：第5个问题，关于最近症状的描述。\n助手：第5个回答，给出了具体建议。\n用户：第6个问题，关于最近症状的描述。\n助手：第6个回答，给出了具体建议。",
    "tokens": 109
   },
   "summarize": {
    "detail": "保留最近 2 轮原文，早期 4 轮压缩为摘要（9 token）",
    "text": "【早期对话摘\n用户：第5个问题，关于最近症状的描述。\n助手：第5个回答，给出了具体建议。\n用户：第6个问题，关于最近症状的描述。\n助手：第6个回答，给出了具体建议。",
    "tokens": 119
   },
   "rerank_drop": {
    "detail": "丢弃相关度最低的 4 段",
    "text": "用户：第1个问题，关于最近症状的描述。\n助手：第1个回答，给出了具体建议。\n用户：第5个问题，关于最近症状的描述。\n助手：第5个回答，给出了具体建议。",
    "tokens": 109
   }
  }
 },
 "relative_cap": {
  "percent": {
   "src": "window 8000 ;\nblock a { source: \"a.txt\" ; cap: 40% ; }",
   "cap": 3200
  },
  "scale": {
   "src": "window 8000 ;\nblock a { source: \"a.txt\" ; cap: window * 0.4 ; }",
   "cap": 3200
  }
 }
};
