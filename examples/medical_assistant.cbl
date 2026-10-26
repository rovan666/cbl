# ========================================
# 医疗咨询助手 · 上下文预算声明（与计划书第 5 节示例逐字一致）
# 场景：系统提示与过敏史必须死保；检索文档、对话历史、工具输出竞争剩余额度。
# ========================================
window 8000 ;

block system_prompt {
    source: "prompts/medical.system.md" ;
    cap: 1500 ;
    priority: must_keep ;
    overflow: error ;
}

block allergy_notes {
    source: "profile/allergy.md" ;
    cap: 300 ;
    priority: must_keep ;
    overflow: error ;
}

block retrieved_docs {
    source: "kb/medical_kb.txt" ;
    cap: 3200 ;
    priority: high ;
    overflow: rerank_drop ;
}

block chat_history {
    source: session_history ;
    cap: 1600 ;
    priority: medium ;
    overflow: summarize ;
    keep_recent: 4 ;
}

block tool_output {
    source: last_tool_result ;
    cap: 500 ;
    priority: low ;
    overflow: truncate_tail ;
}

rule budget_margin {
    assert: total_reserved <= window * 0.9 ;
    on_violation: error ;
}

rule no_starvation {
    assert: every_block_min_tokens >= 100 ;
    on_violation: warn ;
}
