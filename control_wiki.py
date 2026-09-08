import json, re, time, os, sys, html
from datetime import datetime
from urllib.parse import urlparse, urljoin
import requests

BASE = "https://mcp.e2llm.com"; CID = "e2llm-extension"
LLAMA = "http://127.0.0.1:8080/v1/chat/completions"
SITE = "https://en.wikipedia.org/wiki/Samsung_Galaxy_Note_series"
BOOK = "Note 8"
EXPECTED = {"first_released": "15 September 2017"}
MAX_STEPS = 5; CTX_CHARS = 40000     # ~12-15k tokens of raw HTML
LOG = "logs/control_rawhtml_wiki.jsonl"; SESSION = None

def load():
    try:
        with open("token.json", encoding="utf-8") as f: return json.load(f)
    except Exception: return {}
def save(x):
    with open("token.json", "w", encoding="utf-8") as f: json.dump(x, f)
def refresh(x):
    rt = x.get("refresh_token")
    if not rt: return None
    y = requests.post(BASE + "/oauth/token", data={"grant_type": "refresh_token", "refresh_token": rt, "client_id": CID}, timeout=30).json()
    if not y.get("access_token"): return None
    y.setdefault("refresh_token", rt); save(y); return y["access_token"]
def get_token():
    x = load(); t = x.get("access_token")
    if not t: sys.exit("No access_token.")
    try:
        r = requests.get(BASE + "/mcp", headers={"Authorization": "Bearer " + t}, timeout=15)
        if r.status_code != 401: return t
    except Exception: return t
    t = refresh(x)
    if not t: sys.exit("Token refresh failed.")
    return t
TOKEN = get_token()

def call(method, params, timeout=120):
    global SESSION, TOKEN
    h = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if SESSION: h["MCP-Session-ID"] = SESSION
    r = requests.post(BASE + "/mcp", headers=h, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=timeout)
    if r.status_code == 401:
        TOKEN = refresh(load())
        if not TOKEN: sys.exit("Token refresh failed.")
        return call(method, params, timeout)
    r.raise_for_status()
    if method == "initialize": SESSION = r.headers.get("mcp-session-id", "")
    try: return r.json()
    except ValueError:
        if method == "initialize": raise
        SESSION = None
        call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "control", "version": "1"}})
        return call(method, params, timeout)

def tool(name, arguments):
    resp = call("tools/call", {"name": name, "arguments": arguments})
    if resp.get("error"): raise RuntimeError(json.dumps(resp["error"], ensure_ascii=False))
    text = next((i.get("text") for i in resp.get("result", {}).get("content", []) if i.get("text")), "")
    if not text.strip(): return {"ok": name == "act"}
    try: return json.loads(text)
    except json.JSONDecodeError: return {"ok": name == "act", "raw_text": text}

def model_name():
    try:
        m = requests.get("http://127.0.0.1:8080/v1/models", timeout=10).json(); return m["data"][0]["id"] if m.get("data") else "?"
    except Exception: return "?"
MODEL = model_name()
USAGE = {"prompt": 0, "completion": 0, "seconds": 0.0}

def llm(prompt, max_tokens=120):
    t0 = time.time()
    r = requests.post(LLAMA, json={"model": "local", "messages": [
        {"role": "system", "content": "Return exactly one JSON object. No Markdown."}, {"role": "user", "content": prompt}],
        "temperature": 0.1, "max_tokens": max_tokens, "chat_template_kwargs": {"enable_thinking": False}}, timeout=3600)
    r.raise_for_status(); y = r.json()
    u = y.get("usage", {}); USAGE["prompt"] += u.get("prompt_tokens", 0); USAGE["completion"] += u.get("completion_tokens", 0)
    USAGE["seconds"] += time.time() - t0
    print("  llm: prompt_tokens=" + str(u.get("prompt_tokens")) + " completion=" + str(u.get("completion_tokens")) + " seconds=" + str(round(time.time() - t0, 1)))
    return y["choices"][0]["message"]["content"].strip()

def parse_choice(text):
    import ast
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"```[a-zA-Z]*", "", text).replace("```", "")
    m = re.search(r"{.*}", text, re.S)
    if not m: raise ValueError("No JSON from model: " + repr(text[:300]))
    blob = m.group(0)
    try: return json.loads(blob)
    except json.JSONDecodeError:
        f = re.sub(r"\bTrue\b", "true", blob); f = re.sub(r"\bFalse\b", "false", f); f = re.sub(r"\bNone\b", "null", f)
        try: return json.loads(f)
        except json.JSONDecodeError: return ast.literal_eval(blob)

def raw_html(url):
    rr = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"}); rr.encoding = "utf-8"; h = rr.text
    h = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "", h, flags=re.S)
    h = re.sub(r"\s+", " ", h)
    return h[:CTX_CHARS], len(h)

def page_info(p):
    md = p.get("metadata", {}) or {}
    return {"title": p.get("title", "") or md.get("title", ""), "url": p.get("url", "") or md.get("url", ""), "sessionId": p.get("sessionId", "")}

def log(rec):
    with open(LOG, "a", encoding="utf-8") as fh: fh.write(json.dumps(rec, ensure_ascii=False) + chr(10))

os.makedirs("logs", exist_ok=True)
print("CONTROL: same task, same model, same hands - RAW HTML instead of the perception layer")
call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "control", "version": "1"}})
tabs = tool("list_tabs", {}).get("tabs", [])
tab = next((t for t in tabs if t.get("active")), tabs[0]); tab_id = tab["id"]
print("BRAIN:", MODEL, "| Tab:", tab_id, "| Start URL:", tab.get("url", ""))
if "wikipedia.org" in (tab.get("url") or ""):
    try:
        p = tool("sifr_capture", {"tabId": tab_id, "preset": "normal"})
        tool("act", {"sessionId": p.get("sessionId", ""), "action": "navigate", "target": "https://example.com/", "idempotencyKey": "ctl-reset-" + str(int(time.time()))})
        print("reset: example.com"); time.sleep(3)
    except Exception as e: print("reset failed:", str(e)[:100])

verdict = None; VISITED = []
for step in range(1, MAX_STEPS + 1):
    t0 = time.time()
    try:
        page = tool("sifr_capture", {"tabId": tab_id, "preset": "normal"})   # used ONLY to learn the current URL and get a session for act
        before = page_info(page); url = before["url"]; VISITED.append(url)
        on_site = "wikipedia.org" in url; on_book = url.rstrip("/").endswith("Samsung_Galaxy_Note_8")
        print(); print("-" * 55); print("STEP", step, "| page:", before["title"][:50], "|", url[:80])
        if not on_site:
            prompt = ("You are on " + url + ". MISSION step 0: go to " + SITE + ". " 'Return only {"action":"navigate","target":"' + SITE + '"}')
            raw = llm(prompt, 60); d = parse_choice(raw); print("Model:", raw[:200])
            tgt = str(d.get("target", "")).rstrip("/")
            if d.get("action") != "navigate" or tgt != SITE.rstrip("/"): raise ValueError("Bad navigate: " + repr(d))
            res = tool("act", {"sessionId": before["sessionId"], "action": "navigate", "target": SITE, "idempotencyKey": "ctl-nav-" + str(step)})
            print("ACT:", res.get("result")); log({"step": step, "status": "ok", "decision": d}); time.sleep(3); continue
        body, full_len = raw_html(url)
        print("raw html: " + str(full_len) + " chars, sent " + str(len(body)))
        if not on_book:
            task = ("Find the link to the Wikipedia article about the Samsung Galaxy Note 8 phone (its link text is " + json.dumps(BOOK) + "). Return that link's href. "
                    "Do not return links to Note 8.0 tablets.")
            prompt = ("TASK: " + task + " Below is the RAW HTML of the current page (" + url + "). "
                      'Return only {"action":"navigate","target":"<href exactly as it appears in the HTML>"}. HTML=' + body)
            raw = llm(prompt, 120); print("Model:", raw[:300]); d = parse_choice(raw)
            href = str(d.get("target", "")).strip()
            if d.get("action") != "navigate" or not href: raise ValueError("Bad decision: " + repr(d))
            absolute = urljoin(url, html.unescape(href))
            if "wikipedia.org" not in absolute: raise ValueError("Off-site href: " + absolute)
            print("Navigating to:", absolute)
            res = tool("act", {"sessionId": before["sessionId"], "action": "navigate", "target": absolute, "idempotencyKey": "ctl-" + str(step)})
            print("ACT:", res.get("result"))
            log({"step": step, "status": "ok", "url": url, "html_chars": full_len, "decision": d, "target": absolute}); time.sleep(3); continue
        prompt = ("TASK: from the RAW HTML of this Wikipedia article, extract the 'First released' date from the infobox, exactly as written (e.g. 15 September 2017). "
                  'Return only {"action":"report","first_released":"..."}. HTML=' + body)
        raw = llm(prompt, 120); print("Model:", raw[:300]); d = parse_choice(raw)
        checks = {k: str(d.get(k, "")).strip().startswith(v) for k, v in EXPECTED.items()}
        verdict = all(checks.values())
        print("REPORT:", json.dumps(d, ensure_ascii=False)); print("EXPECTED:", json.dumps(EXPECTED, ensure_ascii=False))
        print("CHECKS:", checks, "->", "PASS" if verdict else "FAIL")
        log({"step": step, "status": "report", "decision": d, "checks": checks, "verdict": verdict}); break
    except Exception as e:
        print("ERROR:", type(e).__name__, str(e)[:300]); log({"step": step, "status": "error", "error": type(e).__name__ + ": " + str(e)[:300]}); break

print(); print("RESULT:", {True: "PASS", False: "FAIL", None: "NOT COMPLETE"}[verdict])
print("Tokens: prompt", USAGE["prompt"], "| completion", USAGE["completion"], "| model seconds", round(USAGE["seconds"], 1))
print("Trail:", " -> ".join(urlparse(u).path for u in VISITED)); print("Log:", LOG)
log({"summary": True, "verdict": verdict, "usage": USAGE, "trail": VISITED, "brain": MODEL, "time": datetime.now().isoformat()})
