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
│   ├── engine.py        #   预算执行引擎（五种超限策略）TODO    —— 杨晨
│   ├── report.py        #   审计报告（文本/HTML）TODO           —— 祝梦倩
│   └── cli.py           #   命令行入口
├── examples/
│   └── medical_assistant.cbl   # 医疗助手完整示例
└── tests/
    └── run_tests.py            # 自检脚本
```

## 怎么跑

环境：Python 3.7+，纯标准库，零第三方依赖。

```bash
cd cbl
python -m cbl check examples/medical_assistant.cbl   # 编译检查，输出 JSON 计划
python tests/run_tests.py                            # 跑自检
```

## 当前进度

- [x] 词法分析器、语法分析器（第一版，可用）
- [x] 语义检查 ①~⑨ 全部完成（错误目录 `semantic.CATALOG` 共 16 项，每项配正例/反例测试）
- [x] 静态断言（total_reserved）编译期求值；动态断言（every_block_min_tokens）留给引擎
- [ ] 预算执行引擎（TODO，engine.py）
- [ ] 审计报告（TODO，report.py）

语言的完整定义（EBNF 文法、九条语义约束、运行期语义）与分工详情见课程开发计划书（未随仓库公开）。
