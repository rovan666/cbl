/* CBL 互动教程站 交互脚本：自测题、步进动画、AST 树、诊断联动、引擎滑块、学习进度。
   数据来源：assets/data.js（由 build_data.py 用真实编译器生成）。 */
(function () {
  "use strict";
  var D = window.TUTORIAL_DATA || {};

  function h(tag, attrs, text) {
    var el = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === "class") el.className = attrs[k]; else el.setAttribute(k, attrs[k]);
    });
    if (text != null) el.textContent = text;
    return el;
  }

  /* ---------- 学习进度（localStorage） ---------- */
  var LS = "cbl-tutorial-progress";
  function getProgress() { try { return JSON.parse(localStorage.getItem(LS) || "{}"); } catch (e) { return {}; } }
  function setProgress(id) {
    var p = getProgress(); p[id] = true;
    try { localStorage.setItem(LS, JSON.stringify(p)); } catch (e) {}
  }
  var lessonId = document.body.getAttribute("data-lesson");
  var doneBtn = document.querySelector(".done-btn");
  if (doneBtn && lessonId) {
    if (getProgress()[lessonId]) { doneBtn.classList.add("done"); doneBtn.textContent = "✔ 已完成本课（点击取消标记）"; }
    doneBtn.addEventListener("click", function () {
      if (doneBtn.classList.contains("done")) {
        var p = getProgress(); delete p[lessonId];
        try { localStorage.setItem(LS, JSON.stringify(p)); } catch (e) {}
        doneBtn.classList.remove("done"); doneBtn.textContent = "我学完了这一课";
      } else {
        setProgress(lessonId);
        doneBtn.classList.add("done"); doneBtn.textContent = "✔ 已完成本课（点击取消标记）";
      }
    });
  }
  // 首页进度标记
  document.querySelectorAll(".card[data-lid]").forEach(function (c) {
    if (getProgress()[c.getAttribute("data-lid")]) {
      c.querySelector(".st").textContent = "✅";
    }
  });
  var pill = document.querySelector(".progress-pill");
  if (pill) {
    var n = Object.keys(getProgress()).length;
    pill.textContent = "已完成 " + n + " / 8 课";
  }

  /* ---------- 自测题 ---------- */
  document.querySelectorAll(".quiz").forEach(function (q) {
    var ans = q.getAttribute("data-answer");
    var opts = q.querySelectorAll("button.opt");
    opts.forEach(function (b, i) {
      b.addEventListener("click", function () {
        if (q.classList.contains("solved")) return;
        if (String(i) === ans) {
          b.classList.add("right"); q.classList.add("solved");
        } else {
          b.classList.add("wrong");
          setTimeout(function () { b.classList.remove("wrong"); }, 900);
        }
      });
    });
  });

  /* ---------- Token 步进动画 ---------- */
  function srcOffset(src, line, col) {
    var lines = src.split("\n"), off = 0;
    for (var i = 0; i < line - 1; i++) off += lines[i].length + 1;
    return off + col - 1;
  }
  function markSrc(src, tok) {
    if (tok.kind === "EOF") return escapeHtml(src) + '<mark>⏎</mark>';
    var a = srcOffset(src, tok.line, tok.col), b = a + tok.value.length;
    return escapeHtml(src.slice(0, a)) + "<mark>" + escapeHtml(src.slice(a, b)) + "</mark>" + escapeHtml(src.slice(b));
  }
  function escapeHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  document.querySelectorAll(".stepper[data-kind=tokens]").forEach(function (box) {
    var demo = D.tokens_demo[Number(box.getAttribute("data-idx") || 0)];
    if (!demo) return;
    var toks = demo.tokens, i = 0, timer = null;
    box.innerHTML =
      '<div class="stage"><div><div class="muted" style="font-size:12px;margin-bottom:4px">源码（黄色=当前字符段）</div>' +
      '<pre class="src"></pre></div>' +
      '<div><div class="muted" style="font-size:12px;margin-bottom:4px">产出的 Token</div><div class="tokcard"></div></div></div>' +
      '<div class="bar"><button class="primary play">▶ 自动播放</button>' +
      '<button class="step">单步 →</button><button class="reset">重置</button>' +
      '<span class="pos"></span></div><div class="stream"></div>';
    var srcEl = box.querySelector(".src"), card = box.querySelector(".tokcard"),
        pos = box.querySelector(".pos"), stream = box.querySelector(".stream");
    stream.innerHTML = toks.map(function (t, k) {
      return "<span data-k=" + k + ">" + escapeHtml(t.kind === "EOF" ? "EOF" : t.value) + "</span>";
    }).join("");
    function render() {
      var t = toks[i];
      srcEl.innerHTML = markSrc(demo.src, t);
      card.innerHTML = '<div class="kind">' + t.kind + '</div><table>' +
        "<tr><td>字面值</td><td><code>" + escapeHtml(t.value || "（空）") + "</code></td></tr>" +
        "<tr><td>位置</td><td>行 " + t.line + " 列 " + t.col + "</td></tr>" +
        "<tr><td>怎么认出的</td><td>" + (WHY[t.kind] || "") + "</td></tr></table>";
      pos.textContent = (i + 1) + " / " + toks.length;
      stream.querySelectorAll("span").forEach(function (s, k) {
        s.className = k < i ? "done" : (k === i ? "cur" : "");
      });
      box.querySelector(".step").disabled = i >= toks.length - 1;
    }
    var WHY = {
      KEYWORD: "按标识符读完整词，查关键字表命中",
      IDENT: "按标识符读完，关键字表未命中",
      INT: "数字分支：连续数字（最长匹配）",
      FLOAT: "数字分支：小数点后还有数字",
      STRING: '双引号起，到下一个双引号止',
      SYMBOL: "界符/运算符（双字符优先判断）",
      EOF: "源码读完，追加的哨兵 Token"
    };
    function stop() { if (timer) { clearInterval(timer); timer = null; box.querySelector(".play").textContent = "▶ 自动播放"; } }
    box.querySelector(".step").addEventListener("click", function () { stop(); if (i < toks.length - 1) { i++; render(); } });
    box.querySelector(".reset").addEventListener("click", function () { stop(); i = 0; render(); });
    box.querySelector(".play").addEventListener("click", function () {
      if (timer) return stop();
      this.textContent = "⏸ 暂停";
      timer = setInterval(function () {
        if (i >= toks.length - 1) return stop();
        i++; render();
      }, 900);
    });
    render();
  });

  /* ---------- AST 可折叠树 ---------- */
  document.querySelectorAll(".astree[data-kind=ast]").forEach(function (box) {
    var tree = D.ast_demo && D.ast_demo.tree;
    if (!tree) return;
    function build(node) {
      var wrap = h("div", { class: "node" });
      var lbl = h("div", { class: "lbl" });
      lbl.appendChild(document.createTextNode(node.label + " "));
      if (node.detail) lbl.appendChild(h("span", { class: "detail" }, node.detail));
      if (node.line) lbl.appendChild(h("span", { class: "ln" }, "  ← 行" + node.line));
      wrap.appendChild(lbl);
      (node.children || []).forEach(function (pair) {
        var sub = build(pair[1]);
        sub.insertBefore(h("span", { class: "detail" }, pair[0] + " = "), sub.firstChild);
        wrap.appendChild(sub);
      });
      lbl.addEventListener("click", function () { wrap.classList.toggle("closed"); });
      return wrap;
    }
    box.appendChild(build(tree));
  });

  /* ---------- 诊断联动（语义课 / 错误恢复） ---------- */
  document.querySelectorAll(".diaglink").forEach(function (box) {
    var kind = box.getAttribute("data-kind");
    var data = kind === "syntax" ? D.syntax_recovery : D.diag_demo;
    if (!data) return;
    var items = kind === "syntax" ? data.errors : data.diags;
    var lines = data.src.split("\n");
    var pre = h("pre", { class: "srcview" });
    function renderSrc(hlLine) {
      pre.innerHTML = lines.map(function (ln, i) {
        var s = '<span class="no">' + String(i + 1).padStart(2, " ") + "│ </span>" + escapeHtml(ln);
        return '<span class="row' + (i + 1 === hlLine ? " hl" : "") + '">' + s + "</span>";
      }).join("\n");
    }
    var list = h("div", { class: "diaglist" });
    items.forEach(function (d) {
      var b = h("button", { class: d.level === "警告" ? "w" : "e" }, d.text);
      b.addEventListener("click", function () { renderSrc(d.line); });
      list.appendChild(b);
    });
    renderSrc(0);
    var grid = h("div", { class: "stage" });
    grid.style.display = "grid"; grid.style.gridTemplateColumns = "1fr 1fr"; grid.style.gap = "14px";
    grid.appendChild(pre); grid.appendChild(list);
    box.appendChild(grid);
  });

  /* ---------- 引擎额度滑块（教学复刻 allocate：与 engine.py 同算法） ---------- */
  document.querySelectorAll(".eng[data-kind=alloc]").forEach(function (box) {
    var blocks = [
      { name: "system_prompt", cap: 1500, pri: "must_keep" },
      { name: "allergy_notes", cap: 300, pri: "must_keep" },
      { name: "retrieved_docs", cap: 3200, pri: "high" },
      { name: "chat_history", cap: 1600, pri: "medium" },
      { name: "tool_output", cap: 500, pri: "low" }
    ];
    var total = blocks.reduce(function (s, b) { return s + b.cap; }, 0);   // 7100
    var must = blocks.filter(function (b) { return b.pri === "must_keep"; })
                     .reduce(function (s, b) { return s + b.cap; }, 0);     // 1800
    box.innerHTML = '<div class="muted" style="font-size:13px">拖动滑块改变本次可用额度 B（死保总额 1800、cap 总和 7100 是两个临界点）：</div>' +
      '<input type="range" min="0" max="7100" step="100" value="7100">' +
      '<div class="msg"></div><div class="rows"></div>';
    var slider = box.querySelector("input"), rows = box.querySelector(".rows"), msg = box.querySelector(".msg");
    // 与 cbl/engine.py allocate() 同一算法：low → medium → high 逐级压缩，同级最大余数法
    function allocate(B) {
      var eff = {}; blocks.forEach(function (b) { eff[b.name] = b.cap; });
      if (must > B) return null;
      var excess = total - B;
      ["low", "medium", "high"].forEach(function (lv) {
        if (excess <= 0) return;
        var group = blocks.filter(function (b) { return b.pri === lv; });
        var gtot = group.reduce(function (s, b) { return s + b.cap; }, 0);
        if (!gtot) return;
        var keep = gtot - Math.min(excess, gtot);
        var exact = group.map(function (b) { return b.cap * keep / gtot; });
        var floors = exact.map(Math.floor);
        var rest = keep - floors.reduce(function (s, v) { return s + v; }, 0);
        exact.map(function (x, i) { return { i: i, frac: x - floors[i] }; })
             .sort(function (a, b) { return b.frac - a.frac; })
             .slice(0, rest).forEach(function (o) { floors[o.i]++; });
        group.forEach(function (b, i) { eff[b.name] = floors[i]; });
        excess -= Math.min(excess, gtot);
      });
      return eff;
    }
    function render() {
      var B = Number(slider.value), eff = allocate(B);
      rows.innerHTML = "";
      blocks.forEach(function (b) {
        var v = eff ? eff[b.name] : 0;
        var row = h("div", { class: "bar-row" });
        row.appendChild(h("span", { class: "name" }, b.name));
        row.appendChild(h("span", { class: "pri " + b.pri }, b.pri));
        var track = h("div", { class: "track" });
        track.appendChild(h("div", { class: "fill" }));
        track.firstChild.style.width = (v / total * 100) + "%";
        row.appendChild(track);
        row.appendChild(h("span", { class: "val" }, eff ? ("cap " + b.cap + " → " + v) : ("cap " + b.cap)));
        rows.appendChild(row);
      });
      if (!eff) {
        msg.textContent = "⚠ B=" + B + " 低于死保总额 1800：无解，拒绝组装（约束②的编译期版本是 E201）";
        msg.style.color = "#b42318";
      } else if (B >= total) {
        msg.textContent = "B=" + B + " ≥ cap 总和 7100：额度充足，每块即得其 cap";
        msg.style.color = "#067647";
      } else {
        msg.textContent = "B=" + B + "：超出 " + (total - B) + "，按 low → medium → high 逐级压缩";
        msg.style.color = "#b54708";
      }
    }
    slider.addEventListener("input", render);
    render();
  });

  /* ---------- 策略对照（引擎课） ---------- */
  document.querySelectorAll(".strat").forEach(function (box) {
    var sd = D.strategy_demos;
    if (!sd) return;
    var names = ["truncate_tail", "sliding_window", "summarize", "rerank_drop"];
    var tabs = h("div", { class: "bar" });
    var out = h("div");
    names.forEach(function (n, i) {
      var b = h("button", null, name);
      b.style.cssText = "padding:5px 12px;border-radius:6px;border:1.5px solid #2856d9;background:#fff;color:#2856d9;cursor:pointer";
      b.addEventListener("click", function () { show(i); });
      tabs.appendChild(b);
    });
    function show(i) {
      var n = names[i], r = sd.results[n];
      out.innerHTML = "";
      var pre = h("pre", { class: "srcview" });
      pre.textContent = r.text;
      out.appendChild(h("p", null, ""));
      out.firstChild.innerHTML = "动作：<b>" + escapeHtml(r.detail) + "</b>　最终 " + r.tokens +
        " token（上限 " + sd.limit + "）";
      out.appendChild(pre);
    }
    box.appendChild(h("p", null, "同一材料：" + sd.units.length + " 轮对话，上限 " + sd.limit + " token。点策略名看各自产出："));
    box.appendChild(tabs);
    box.appendChild(out);
    show(0);
  });

  /* ---------- 综合考察（quiz 页） ---------- */
  var exam = document.querySelector("#exam");
  if (exam && window.EXAM_QUESTIONS) {
    var pool = window.EXAM_QUESTIONS.slice();
    var count = Math.min(Number(exam.getAttribute("data-count") || 10), pool.length);
    var start = h("button", { class: "done-btn" }, "开始抽测（从 " + pool.length + " 题中随机抽 " + count + " 题）");
    exam.appendChild(start);
    start.addEventListener("click", function () {
      start.remove();
      pool.sort(function () { return Math.random() - 0.5; });
      var qs = pool.slice(0, count), score = 0, answered = 0;
      var board = h("p", null, "");
      exam.appendChild(board);
      qs.forEach(function (q, qi) {
        var box = h("div", { class: "quiz" });
        box.appendChild(h("p", { class: "q" }, (qi + 1) + ". " + q.q));
        q.opts.forEach(function (op, oi) {
          var b = h("button", { class: "opt" }, op);
          b.addEventListener("click", function () {
            if (box.classList.contains("solved")) return;
            box.classList.add("solved");
            answered++;
            if (oi === q.a) { b.classList.add("right"); score++; }
            else { b.classList.add("wrong"); box.querySelectorAll(".opt")[q.a].classList.add("right"); }
            if (q.why) { var fb = h("div", { class: "fb" }); fb.style.display = "block"; fb.textContent = "解析：" + q.why; box.appendChild(fb); }
            board.textContent = "已答 " + answered + " / " + count + "　答对 " + score;
            if (answered === count) {
              var r = h("h3", null, "总分 " + score + " / " + count + "　" +
                (score === count ? "满分！可以上答辩场了。" :
                 score >= count * 0.8 ? "不错，把错题对应的那课再翻一遍。" :
                 "建议回到错题对应的课程重新过一遍。"));
              exam.appendChild(r);
            }
          });
          box.appendChild(b);
        });
        exam.appendChild(box);
      });
    });
  }
})();
