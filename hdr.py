import json, sys, subprocess, requests
BASE = "https://mcp.e2llm.com"; CID = "e2llm-extension"
tok = json.load(open("token.json", encoding="utf-8"))
T = tok.get("access_token", "")
def mcp(method, params, sess=None):
    h = {"Authorization": "Bearer " + T, "Content-Type": "application/json",
         "Accept": "application/json, text/event-stream"}
    if sess: h["MCP-Session-ID"] = sess
    r = requests.post(BASE + "/mcp", headers=h, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=60)
    if r.status_code == 401:
        y = requests.post(BASE + "/oauth/token", data={"grant_type": "refresh_token",
              "refresh_token": tok.get("refresh_token"), "client_id": CID}, timeout=30).json()
        if y.get("access_token"):
            y.setdefault("refresh_token", tok.get("refresh_token")); json.dump(y, open("token.json", "w"))
            globals()["T"] = y["access_token"]; return mcp(method, params, sess)
    r.raise_for_status()
    return r, r.headers.get("mcp-session-id", "")
def run(c):
    try: return subprocess.check_output(c, shell=True, text=True).strip()
    except Exception: return ""
kb = 0
for line in open("/proc/meminfo"):
    if line.startswith("MemTotal:"): kb = int(line.split()[1]); break
try:
    m = requests.get("http://127.0.0.1:8080/v1/models", timeout=10).json()
    model = m["data"][0]["id"] if m.get("data") else "?"
except Exception as e:
    model = "llama-server not reachable: " + type(e).__name__
print("HDR BRAIN   :", model, "(llama.cpp, local)")
print("HDR PHONE   :", (run("getprop ro.product.manufacturer") + " " + run("getprop ro.product.model")).strip(),
      "| Android", run("getprop ro.build.version.release"), "|", round(kb / 1048576, 1), "GB RAM")
r, sess = mcp("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "hdr", "version": "1"}})
r, _ = mcp("tools/call", {"name": "list_tabs", "arguments": {}}, sess)
txt = next((c.get("text") for c in r.json().get("result", {}).get("content", []) if c.get("text")), "{}")
try: tabs = json.loads(txt).get("tabs", [])
except Exception: tabs = []; print("HDR list_tabs:", txt[:200])
browsers = sorted({t.get("browser") or "?" for t in tabs})
print("HDR BROWSERS:", ", ".join(browsers) if browsers else "none", "|", len(tabs), "tabs")
active = next((t for t in tabs if t.get("active")), tabs[0] if tabs else None)
if active:
    args = {"tabId": active["id"], "preset": "normal"}
    if active.get("browser"): args["browser"] = active["browser"]
    r, _ = mcp("tools/call", {"name": "sifr_capture", "arguments": args}, sess)
    txt = next((c.get("text") for c in r.json().get("result", {}).get("content", []) if c.get("text")), "")
    try:
        p = json.loads(txt); md = p.get("metadata", {}) or {}; vp = md.get("viewport") or {}
        print("HDR EYES    : E2LLM", md.get("extensionVersion", "?"), "| browser", active.get("browser") or "?",
              "| viewport", str(vp.get("width", "?")) + "x" + str(vp.get("height", "?")), "| active tab:", active.get("url", "")[:70])
    except Exception:
        print("HDR EYES    : capture failed:", txt[:200])
