# -*- coding: utf-8 -*-
"""网页演示（webui）与 HTML 报告的测试用例（由 run_tests.py 统一收集运行）。

  1. analyze()：编译各阶段失败、拒绝组装、逐单位状态（保留/部分/摘要/丢弃/未组装）；
  2. HTML 报告：内嵌数据不能被材料里的 </script> 截断（XSS）；
  3. HTTP 服务：在随机端口起真实服务，逐个接口请求，含越权路径与超大请求体。
"""
import http.client
import json
import os
import threading
from http.server import ThreadingHTTPServer

from cbl.webui import analyze, make_handler, MAX_BODY
from cbl.report import build_html

ROOT = os.path.join(os.path.dirname(__file__), "..")
EXAMPLE = os.path.join(ROOT, "examples", "medical_assistant.cbl")
MATERIALS = os.path.join(ROOT, "examples", "materials")
SOURCE = open(EXAMPLE, encoding="utf-8").read()


def _statuses(res, name):
    view = [b for b in res["blocks"] if b["name"] == name][0]
    out = {}
    for u in view["units"]:
        out[u["status"]] = out.get(u["status"], 0) + 1
    return out, view


# ---------- 1. analyze ----------

def case_webui_analyze_default():
    res = analyze(SOURCE, MATERIALS)
    assert res["stage"] == "ok" and len(res["blocks"]) == 5, res["stage"]
    st, view = _statuses(res, "chat_history")
    # 回归：早期轮次的首句会被摘要引用，曾被误判为"部分保留"
    assert st == {"summarized": 4, "kept": 4}, st
    assert view["summary"] and not view["summary"].startswith("【"), "摘要正文应去掉标签"
    st, _ = _statuses(res, "retrieved_docs")
    assert st == {"kept": 15, "dropped": 9}, st
    st, _ = _statuses(res, "tool_output")
    assert st == {"partial": 1}, f"工具输出只有一段，被截尾应为部分保留：{st}"
    assert _statuses(res, "system_prompt")[0] == {"kept": 8}
    assert res["prompt"] and res["report_text"].startswith("=== CBL 组装审计报告 ===")


def case_webui_analyze_squeezed():
    res = analyze(SOURCE, MATERIALS, budget=6000)
    assert _statuses(res, "tool_output")[0] == {"dropped": 1}
    st, view = _statuses(res, "chat_history")
    assert st == {"kept": 3, "dropped": 5} and not view["summary"], "额度不足时退化为滑动窗口，无摘要"


def case_webui_analyze_rejected():
    res = analyze(SOURCE, MATERIALS, budget=1700)
    assert res["stage"] == "rejected" and res["prompt"] == ""
    for b in res["blocks"]:
        assert all(u["status"] == "pending" for u in b["units"]), f"拒绝组装时不应显示保留：{b['name']}"


def case_webui_analyze_compile_errors():
    res = analyze("window 8000 ;\nblock a { cap: 100 ; source: @ ; }", MATERIALS)
    assert res["stage"] == "lex" and res["error"]["line"] == 2 and res["audit"] is None
    res = analyze("window 8000\nblock a { cap: 100 ; }", MATERIALS)
    assert res["stage"] == "syntax" and res["error"]["line"] == 1, "缺分号报在缺的那一行"
    res = analyze('window 8000 ;\nblock a { source: chat_log ; cap: 100 ; }', MATERIALS)
    assert res["stage"] == "semantic" and [d["code"] for d in res["diags"]] == ["E601"], res["diags"]
    assert res["diags"][0]["text"].startswith("[错误] 行2 E601: ")


def case_webui_source_sandbox():
    # 网页允许改源码：越出材料目录的路径必须读不到（否则局域网模式下可读任意文件）
    evil = SOURCE.replace('"kb/medical_kb.txt"', '"../../README.md"')
    res = analyze(evil, MATERIALS)
    docs = [b for b in res["audit"]["blocks"] if b["name"] == "retrieved_docs"][0]
    assert docs["action"] == "来源缺失" and "越出材料目录" in docs["detail"], docs
    assert "# CBL" not in res["prompt"], "不得读出材料目录外的文件内容"


# ---------- 2. HTML 报告 ----------

def case_html_report_embed_safe():
    attack = "</script><script>alert(1)</script>"
    res = analyze(SOURCE, MATERIALS, query="青霉素过敏 " + attack)
    html = build_html(res)
    assert attack not in html, "材料/提问中的 </script> 必须被转义"
    assert html.count("</script>") == 3, "只应有 数据/渲染器/启动 三个脚本标签"
    data = html.split('id="cbl-data">', 1)[1].split("</script>", 1)[0]
    assert json.loads(data)["query"].endswith(attack), "转义后的 JSON 必须能还原原文"


# ---------- 3. HTTP 服务 ----------

class _Server:
    def __enter__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(EXAMPLE, MATERIALS))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()

    def req(self, method, path, body=None, raw=None):
        # http.client 直连，不经环境变量里的代理；也不会把 ../ 规范化掉
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=10)
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        conn.request(method, path, body=data, headers={"Content-Type": "application/json"})
        r = conn.getresponse()
        out = (r.status, r.getheader("Content-Type") or "", r.read())
        conn.close()
        return out

    def oversized(self, path):
        """只在请求头里声明超大 Content-Length、不发请求体：服务端必须不等数据直接拒绝。
        （真发 256KB 会与服务端提前关连接抢跑，在 Windows 上偶发连接中止，测试不稳定。）"""
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=10)
        conn.putrequest("POST", path)
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(MAX_BODY + 1))
        conn.endheaders()
        status = conn.getresponse().status
        conn.close()
        return status


def case_server_endpoints():
    with _Server() as s:
        code, ctype, body = s.req("GET", "/")
        assert code == 200 and "text/html" in ctype and "CBL 预算实验台".encode() in body
        assert s.req("GET", "/?budget=6000")[0] == 200
        assert s.req("GET", "/static/report.js")[0] == 200
        assert s.req("GET", "/static/report.css")[0] == 200
        for bad in ("/static/../cli.py", "/static/..%2fcli.py", "/static/.hidden", "/nope"):
            assert s.req("GET", bad)[0] == 404, f"{bad} 应为 404"
        code, _, body = s.req("GET", "/api/init")
        init = json.loads(body)
        assert code == 200 and init["source"] == SOURCE and init["query"]
        code, _, body = s.req("POST", "/api/analyze", {"source": SOURCE, "budget": 6000})
        res = json.loads(body)
        eff = {b["name"]: b["effective"] for b in res["audit"]["blocks"]}
        assert code == 200 and eff["chat_history"] == 1000 and eff["tool_output"] == 0, eff
        code, ctype, body = s.req("POST", "/api/report", {"source": SOURCE, "budget": 6000})
        assert code == 200 and "text/html" in ctype and b'id="cbl-data"' in body
        assert s.req("POST", "/api/report", {"source": "window ;"})[0] == 400, "编译失败不能出报告"
        assert s.req("POST", "/api/analyze", {"source": SOURCE, "budget": -5})[0] == 400
        assert s.req("POST", "/api/analyze", raw=b"{not json")[0] == 400
        assert s.oversized("/api/analyze") == 413, "超大请求体应只看请求头就拒绝"
