# CBL — 上下文预算语言（Context Budget Language）

> 编译原理 DSL 实验项目：用一门声明式小语言描述"AI 上下文窗口里，
> 各类信息各占多少额度、优先级如何、超额后如何处理"。

## 这是什么

大模型的上下文窗口是有限的token资源池。CBL 把"预算分配"从散落在代码里的
魔法数字，变成一份可以被编译器检查、被版本管理、被审计的 `.cbl` 声明文件：

```
源文件 → 词法分析 → 语法分析 → 语义检查 → JSON 组装计划 → 预算执行引擎 → 最终 Prompt + 审计报告
        （lexer）   （parser）  （semantic）   （ir）            （engine）       （report）
```

## 目录结构

```
cbl/
├── cbl/                 # 编译器包
│   ├── tokens.py        #   Token 类型 + 21 个关键字表
│   ├── lexer.py         #   词法分析器（逐字符有限自动机）      —— 徐同帅
│   ├── parser.py        #   语法分析器（手写递归下降）          —— 徐同帅
│   ├── ast_nodes.py     #   AST 节点定义
│   ├── semantic.py      #   语义检查器（九条约束，错误目录+表驱动）—— 舒若凡
│   ├── ir.py            #   AST → JSON 组装计划（中间表示）
│   ├── engine.py        #   预算执行引擎（优先级压缩 + 五种超限策略）—— 杨晨
│   ├── report.py        #   审计报告（JSON / 文本；HTML 待做）  —— 祝梦倩
│   └── cli.py           #   命令行入口（check / run）
├── examples/
│   ├── medical_assistant.cbl   # 医疗助手完整示例
│   └── materials/              # 示例上下文材料（见其中 README）
└── tests/
    ├── run_tests.py            # 自检脚本（统一入口）
    ├── engine_cases.py         # 引擎与报告用例
    └── snapshots/              # 审计报告快照
```

## 怎么跑

环境：Python 3.7+，纯标准库，零第三方依赖。

```bash
cd cbl
python -m cbl check examples/medical_assistant.cbl   # 编译检查，输出 JSON 计划
python -m cbl run   examples/medical_assistant.cbl   # 编译 + 组装，打印审计报告
python -m cbl run   examples/medical_assistant.cbl --budget 6000 --out prompt.txt --json audit.json
python tests/run_tests.py                            # 跑自检（45 个用例）
```

`run` 的输出示例（缺省可用额度 7200）：

```
=== CBL 组装审计报告 ===  window=8000  可用=7200  占用=6542 (81.8%)
[must_keep] system_prompt   cap=1500 used=1238 完整保留
[must_keep] allergy_notes   cap=300  used=92   完整保留
[high]      retrieved_docs  cap=3200 used=3145 原始 4774
            -> rerank_drop 丢弃相关度最低的 9 段
[medium]    chat_history    cap=1600 used=1590 原始 2270
            -> summarize 保留最近 4 轮原文，早期 4 轮压缩为摘要（404 token）
[low]       tool_output     cap=500  used=477  原始 658
            -> truncate_tail 截断尾部 181 token
规则检查：budget_margin  通过 (7100 <= 7200)
          no_starvation  通过 (最小有效额度 300 >= 100)
```

`--budget 6000` 时 low 级的 tool_output 被压缩到 0 整块舍弃、medium 级的 chat_history
压缩到 1000，动态断言 no_starvation 报警告——与计划书第 5 节的压缩示例一致。

## 当前进度

- [x] 词法分析器、语法分析器（第一版，可用）
- [x] 语义检查 ①~⑨ 全部完成（错误目录 `semantic.CATALOG` 共 16 项，每项配正例/反例测试）
- [x] 静态断言（total_reserved）编译期求值；动态断言（every_block_min_tokens）留给引擎
- [x] 预算执行引擎：可用额度与优先级压缩（low → medium → high）、五种超限策略、运行期断言
- [x] 审计报告：JSON 主格式 + 文本视图；快照测试防止裁剪行为被悄悄改变
- [ ] 审计报告 HTML 视图
- [ ] 加分项：网页演示（拖动可用额度滑块，实时观察压缩与裁剪）

语言的完整定义（EBNF 文法、九条语义约束、运行期语义）与分工详情见课程开发计划书（未随仓库公开）。
