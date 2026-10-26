/* CBL 审计报告渲染器：网页演示（demo.html）与独立 HTML 报告（report.build_html）共用。
 * 输入 data = webui.analyze() 的结果：{stage, audit, ir, blocks, report_text, prompt, query, ...}
 * 只用 DOM API 构建节点、textContent 写文本——材料内容不可信，不拼接 HTML 字符串。 */
(function (global) {
  "use strict";

  var PRI = { must_keep: "死保", high: "高", medium: "中", low: "低" };
  var STRATEGY = { truncate_tail: "尾部截断", sliding_window: "滑动窗口", summarize: "摘要压缩",
                   rerank_drop: "相关度丢弃", error: "拒绝组装" };
  var UNIT_STATUS = { kept: "保留", partial: "部分保留", summarized: "并入摘要",
                      dropped: "丢弃", pending: "未组装" };

  function h(tag, attrs) {
    var el = document.createElement(tag);
    if (attrs) {
      for (var k in attrs) {
        if (!Object.prototype.hasOwnProperty.call(attrs, k) || attrs[k] == null) continue;
        if (k === "text") el.textContent = attrs[k];
        else if (k === "cls") el.className = attrs[k];
        else if (k === "style") el.setAttribute("style", attrs[k]);
        else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), attrs[k]);
        else el.setAttribute(k, attrs[k]);
      }
    }
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null || c === false) continue;
      if (Array.isArray(c)) c.forEach(function (x) { if (x != null) el.appendChild(typeof x === "string" ? document.createTextNode(x) : x); });
      else el.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return el;
  }
  function n(x) { return Number(x).toLocaleString("zh-CN"); }
  function pct(a, b) { return b ? Math.round(a / b * 1000) / 10 : 0; }
  function g(x) { return Number.isInteger(x) ? String(x) : String(Math.round(x * 100) / 100); }

  function actionKind(action) {
    if (!action) return "pending";
    if (action === "完整保留") return "keep";
    if (action === "整块舍弃" || action === "来源缺失") return "drop";
    if (action === "error") return "bad";
    return "trim";
  }
  function actionLabel(action) {
    if (!action) return "未组装";
    return STRATEGY[action] ? action + " · " + STRATEGY[action] : action;
  }

  /* 按 IR 的声明顺序，把审计条目与逐块视图对齐；拒绝组装时后面的块没有审计条目 */
  function rows(data) {
    var audit = data.audit || { blocks: [] };
    var byA = {}, byV = {};
    audit.blocks.forEach(function (b) { byA[b.name] = b; });
    (data.blocks || []).forEach(function (v) { byV[v.name] = v; });
    return (data.ir ? data.ir.blocks : audit.blocks).map(function (b) {
      return { ir: b, a: byA[b.name] || null, v: byV[b.name] || null };
    });
  }

  function mustSum(data) {
    return (data.ir ? data.ir.blocks : []).filter(function (b) { return b.priority === "must_keep"; })
      .reduce(function (s, b) { return s + b.cap; }, 0);
  }
  function capSum(data) {
    return (data.ir ? data.ir.blocks : []).reduce(function (s, b) { return s + b.cap; }, 0);
  }

  /* ---------- 横幅：拒绝组装 / 规则违例 ---------- */
  function renderBanner(data) {
    if (data.stage === "rejected") {
      return h("div", { cls: "banner bad", role: "alert" },
        h("strong", { text: "拒绝组装" }), data.audit.error,
        h("div", { cls: "muted", style: "margin-top:4px;color:inherit;opacity:.85",
          text: "没有任何内容送入模型——这正是 CBL 要保障的语义：宁可报错，也不静默丢失死保信息。" }));
    }
    var warns = (data.audit.rules || []).filter(function (r) { return !r.passed; });
    if (warns.length) {
      return h("div", { cls: "banner warn", role: "status" },
        h("strong", { text: "规则警告" }),
        warns.map(function (r) { return r.name + (r.where ? "（" + r.where + "）" : ""); }).join("、") +
        " 不成立，按 warn 级别记入审计报告，组装照常完成。");
    }
    return null;
  }

  /* ---------- 概要指标 ---------- */
  function renderKpis(data) {
    var a = data.audit, ir = data.ir;
    var B = a.budget, W = a.window, deflt = ir ? Math.floor(W * ir.margin) : B;
    var rs = rows(data);
    var cnt = { keep: 0, trim: 0, drop: 0 };
    rs.forEach(function (r) { var k = actionKind(r.a && r.a.action); if (cnt[k] != null) cnt[k]++; });
    var rules = a.rules || [];
    var passed = rules.filter(function (r) { return r.passed; }).length;
    var warn = rules.filter(function (r) { return !r.passed && r.level !== "error"; }).length;
    var rejected = data.stage === "rejected";
    return h("div", { cls: "kpis" },
      h("div", { cls: "kpi" }, h("div", { cls: "k", text: "可用额度 B" }),
        h("div", { cls: "v", text: n(B) }),
        h("div", { cls: "s", text: B === deflt ? "缺省 = " + n(W) + " × " + g(ir ? ir.margin : 0)
                                                : "调用方指定（缺省 " + n(deflt) + "）" })),
      h("div", { cls: "kpi" + (rejected ? " bad" : "") }, h("div", { cls: "k", text: "实际占用" }),
        h("div", { cls: "v", text: rejected ? "—" : n(a.total_used) }),
        h("div", { cls: "s", text: rejected ? "拒绝组装，未送入模型"
                                            : "占 B 的 " + pct(a.total_used, B) + "% · 占窗口 " + pct(a.total_used, W) + "%" })),
      h("div", { cls: "kpi" }, h("div", { cls: "k", text: "预算块" }),
        h("div", { cls: "v", text: rs.length + " 块" }),
        h("div", { cls: "s", text: rejected ? "组装中止" : "完整 " + cnt.keep + " · 裁剪 " + cnt.trim + " · 舍弃 " + cnt.drop })),
      h("div", { cls: "kpi" + (rejected ? " bad" : "") }, h("div", { cls: "k", text: "规则检查" }),
        h("div", { cls: "v", text: rules.length ? passed + " / " + rules.length : "—" }),
        h("div", { cls: "s", text: rules.length ? "通过 " + passed + " · 警告 " + warn + " · 违例 " + (rules.length - passed - warn)
                                                : (rejected ? "组装中止，未求值" : "无规则") })));
  }

  /* ---------- 窗口堆叠条：每块有效额度（实色 = 实际用量）+ 未分配 + 输出预留 ---------- */
  function renderWindowBar(data) {
    var a = data.audit, W = a.window, B = a.budget;
    var rs = rows(data).filter(function (r) { return r.a; });
    var effSum = rs.reduce(function (s, r) { return s + r.a.effective; }, 0);
    var scale = Math.max(W, B, effSum, 1);
    var bar = h("div", { cls: "wbar", role: "img",
      "aria-label": "窗口 " + W + "，可用额度 " + B + "，各块有效额度合计 " + effSum });
    // label = [名字, 数字]：宽段写"名字 数字"，窄段只写名字，太窄不写（数字在下方图例里都有）
    function seg(cls, width, label, title, usedFrac) {
      var frac = width / scale;
      var s = h("div", { cls: "wseg " + cls, style: "flex:0 0 " + (frac * 100) + "%", title: title });
      if (usedFrac != null) s.appendChild(h("div", { cls: "used", style: "width:" + Math.min(100, usedFrac * 100) + "%" }));
      var text = frac > 0.16 ? label.join(" ") : frac > 0.08 ? label[0] : "";
      if (text) s.appendChild(h("div", { cls: "lbl" }, h("span", { text: text })));
      bar.appendChild(s);
    }
    if (!rs.length && data.ir) {                      // 分配阶段就被拒绝：画出死保需求
      var need = mustSum(data);
      seg("need", need, ["死保需要", n(need)], "must_keep 额度之和 " + need + " 超过可用额度 " + B);
      if (scale > need) seg("reserve", scale - need, ["", ""], "");
    } else {
      rs.forEach(function (r) {
        if (r.a.effective <= 0) return;
        var used = data.stage === "rejected" ? 0 : r.a.used;
        seg("p-" + r.a.priority, r.a.effective, [r.a.name, n(r.a.effective)],
            r.a.name + "：有效额度 " + r.a.effective + "（cap " + r.a.cap + "），实际用量 " + used,
            used / r.a.effective);
      });
      if (effSum < B) seg("slack", B - effSum, ["未分配", n(B - effSum)], "各块 cap 之和小于可用额度，剩余部分不分配（ⓑ 额度不回流）");
      if (B < W) seg("reserve", W - B, ["输出预留", n(W - B)], "window − B：留给模型生成回答");
    }
    var wrap = h("div", { cls: "wbar-wrap" }, bar);
    var mk = h("div", { cls: "wmark" + (B / scale > 0.8 ? " right" : ""), style: "left:" + (B / scale * 100) + "%" },
      h("span", { text: "B = " + n(B) }));
    wrap.appendChild(mk);
    var legend = h("div", { cls: "legend" }, rows(data).map(function (r) {
      var p = r.ir.priority, eff = r.a ? r.a.effective : null;
      return h("span", { cls: eff === 0 ? "dropped" : "" },
        h("i", { style: "background:var(--" + (p === "must_keep" ? "must" : p) + ")" }),
        r.ir.name + (eff == null ? "（未组装）" : eff < r.ir.cap ? "  有效 " + n(eff) + " / cap " + n(r.ir.cap) : "  " + n(eff)));
    }));
    return h("div", null, wrap,
      h("div", { cls: "wscale" }, h("span", { text: "0" }), h("span", { text: "window " + n(W) })),
      legend);
  }

  /* ---------- 规则 ---------- */
  function renderRules(data) {
    var rules = data.audit.rules || [];
    if (!rules.length) return h("div", { cls: "muted", text: data.stage === "rejected" ? "组装中止，规则未求值" : "本程序没有声明规则" });
    var neg = { "<=": ">", ">=": "<" }, sym = { "<=": "≤", ">=": "≥", ">": ">", "<": "<" };
    return h("div", { cls: "rules" }, rules.map(function (r) {
      var cls = r.passed ? "pass" : (r.level === "error" ? "fail" : "warn");
      var op = sym[r.passed ? r.op : neg[r.op]];
      var what = r.metric === "every_block_min_tokens" ? "最小有效额度 " : "Σcap ";
      return h("span", { cls: "rule " + cls, title: r.metric + " " + r.op + " " + r.bound },
        h("b", { text: r.passed ? "通过" : (r.level === "error" ? "违例" : "警告") }),
        r.name + "：" + what + n(r.actual) + " " + op + " " + n(r.bound) + (r.where ? "（" + r.where + "）" : ""));
    }));
  }

  /* ---------- 逐块卡片 ---------- */
  function miniBar(a) {
    var scale = Math.max(a.original, a.cap, 1);
    var bar = h("div", { cls: "mini", role: "img",
      "aria-label": "原始 " + a.original + "，cap " + a.cap + "，有效额度 " + a.effective + "，实际 " + a.used });
    bar.appendChild(h("div", { cls: "orig", style: "width:" + (a.original / scale * 100) + "%" }));
    bar.appendChild(h("div", { cls: "used", style: "width:" + (a.used / scale * 100) + "%" }));
    bar.appendChild(h("div", { cls: "cap", style: "left:" + (a.cap / scale * 100) + "%", title: "cap " + a.cap }));
    if (a.effective < a.cap)
      bar.appendChild(h("div", { cls: "eff", style: "left:" + (a.effective / scale * 100) + "%", title: "有效额度 " + a.effective }));
    return bar;
  }

  function renderUnits(v, a, pending) {
    if (!v || !v.units.length) return null;
    var kept = v.units.filter(function (u) { return u.status === "kept"; }).length;
    var part = v.units.filter(function (u) { return u.status === "partial"; }).length;
    var summ = v.units.filter(function (u) { return u.status === "summarized"; }).length;
    var stat = pending ? "原始材料 " + v.units.length + " " + v.unit_name + "（未送入模型）"
      : "完整保留 " + kept + " / " + v.units.length + " " + v.unit_name +
        (part ? " · 部分保留 " + part : "") + (summ ? " · 并入摘要 " + summ : "") +
        (a && a.used ? " · " + n(a.used) + " token" : "");
    var head = h("summary", null, pending ? "原始材料" : "AI 实际看到的内容",
      h("span", { cls: "muted", text: stat + " · 点击单条可展开全文" }));
    var list = h("div", { cls: "units" }, v.units.map(function (u, i) {
      var row = h("div", { cls: "unit " + u.status, title: "第 " + (i + 1) + " " + v.unit_name },
        h("span", { cls: "st", text: UNIT_STATUS[u.status] || u.status }),
        h("span", { cls: "tx", text: u.text }),
        h("span", { cls: "tk", text: n(u.tokens) + " tk" }));
      row.addEventListener("click", function () { row.classList.toggle("open"); });
      return row;
    }));
    var sum = v.summary ? h("div", { cls: "summary-box" }, h("b", { text: "【早期对话摘要】" }), v.summary) : null;
    return h("details", { cls: "seen" }, head, sum, list);
  }

  function renderBlocks(data) {
    var rejected = data.stage === "rejected";
    return h("div", { cls: "blocks" }, rows(data).map(function (r) {
      var b = r.ir, a = r.a, v = r.v, p = b.priority;
      // 拒绝组装时只有"导致拒绝的那一块"保留其动作，其余一律显示"未组装"
      var action = a ? a.action : null;
      if (rejected && action !== "error" && action !== "来源缺失") action = null;
      var kind = actionKind(action);
      var nums = a ? h("div", { cls: "blk-nums" },
          h("span", null, "原始", h("b", { text: n(a.original) })),
          h("span", { cls: "arrow", text: "→" }),
          h("span", null, "有效额度", h("b", { text: n(a.effective) }), h("span", { cls: "muted", text: "（cap " + n(a.cap) + "）" })),
          h("span", { cls: "arrow", text: "→" }),
          h("span", null, "实际用量", h("b", { text: rejected ? "—" : n(a.used) })))
        : h("div", { cls: "blk-nums muted", text: "组装已中止，本块未处理（cap " + n(b.cap) + "）" });
      return h("article", { cls: "blk p-" + p },
        h("div", { cls: "blk-head" },
          h("span", { cls: "badge p-" + p, text: PRI[p] + " · " + p }),
          h("h3", { text: b.name }),
          h("span", { cls: "src", text: b.source_kind === "string" ? '"' + b.source + '"' : b.source }),
          h("span", { cls: "act " + kind, text: actionLabel(action) })),
        nums,
        a ? miniBar(a) : null,
        a ? h("div", { cls: "mini-key" },
              h("span", null, h("i", { cls: "k-used" }), "实际用量"),
              h("span", null, h("i", { cls: "k-orig" }), "原始材料"),
              h("span", null, h("i", { cls: "k-cap" }), "cap"),
              a.effective < a.cap ? h("span", null, h("i", { cls: "k-eff" }), "压缩后的有效额度") : null) : null,
        a && a.detail ? h("div", { cls: "detail", text: (STRATEGY[a.action] ? a.action + "：" : "") + a.detail }) : null,
        renderUnits(v, a, kind === "pending"));
    }));
  }

  function section(title, body, extra) {
    return h("section", { cls: "panel" }, h("h2", null, title, extra || null), body);
  }

  function toggleAll(root) {
    var ds = root.querySelectorAll("details.seen");
    var open = Array.prototype.some.call(ds, function (d) { return !d.open; });
    Array.prototype.forEach.call(ds, function (d) { d.open = open; });
  }

  /* 主视图：横幅 + 指标 + 窗口条 + 规则 + 逐块卡片 */
  function renderMain(root, data) {
    root.textContent = "";
    var banner = renderBanner(data);
    if (banner) root.appendChild(banner);
    root.appendChild(renderKpis(data));
    root.appendChild(section("窗口分配", renderWindowBar(data)));
    root.appendChild(section("规则检查", renderRules(data)));
    var btn = h("button", { cls: "linkbtn", type: "button", text: "全部展开 / 收起", style:
      "float:right;font:inherit;font-size:13px;color:var(--accent);background:none;border:0;cursor:pointer;padding:0" });
    var blocks = renderBlocks(data);
    btn.addEventListener("click", function () { toggleAll(blocks); });
    root.appendChild(section("逐块审计（按声明顺序，即最终 Prompt 的拼接顺序）", blocks, btn));
  }

  /* 独立报告：页眉 + 主视图 + 文本报告 + 最终 Prompt */
  function renderStatic(root, data) {
    var head = h("header", null,
      h("h1", { text: "CBL 组装审计报告" }),
      h("div", { cls: "meta" },
        h("span", { text: "程序：" + (data.file || "—") }),
        h("span", { text: "生成时间：" + (data.generated_at || "—") }),
        h("span", { text: "本轮提问：" + (data.query || "（无）") })));
    var main = h("div", { cls: "report-main" });
    renderMain(main, data);
    root.textContent = "";
    root.appendChild(head);
    root.appendChild(main);
    root.appendChild(section("文本视图", h("pre", { cls: "box", text: data.report_text })));
    if (data.prompt) root.appendChild(section("最终 Prompt（送入模型的全部内容）", h("pre", { cls: "box wrap", text: data.prompt })));
    root.appendChild(h("footer", { text: "由 CBL（上下文预算语言）执行引擎生成 · 审计记录 JSON 见页面源码中的 cbl-data" }));
  }

  global.CBLReport = { h: h, renderMain: renderMain, renderStatic: renderStatic, mustSum: mustSum, capSum: capSum,
                       renderKpis: renderKpis, renderWindowBar: renderWindowBar, renderRules: renderRules,
                       renderBlocks: renderBlocks };
})(window);
