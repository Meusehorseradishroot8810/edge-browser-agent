import json, re, time, os, sys, subprocess
from datetime import datetime
from urllib.parse import urlparse, unquote
import requests

BASE = "https://mcp.e2llm.com"
CID = "e2llm-extension"
LLAMA = "http://127.0.0.1:8080/v1/chat/completions"
START = "https://en.wikipedia.org/wiki/Samsung_Galaxy_Note_series"
TARGET_TEXT = "Note 8"
TARGET_PATH = "Galaxy_Note_8"
EXPECTED_DATE = "15 September 2017"      # correct from the page if the infobox says otherwise
MAX_STEPS = 5
MAX_CANDIDATES = 10
LOG = "logs/wiki_note8_glm.jsonl"
SESSION = None

def load():
    try:
        with open("token.json", encoding="utf-8") as f: return json.load(f)
    except Exception: return {}
def save(x):
    with open("token.json", "w", encoding="utf-8") as f: json.dump(x, f)
def refresh(x):
    rt = x.get("refresh_token")
    if not rt: return None
    y = requests.post(BASE + "/oauth/token", data={"grant_type": "refresh_token", "refresh_token": rt,
                      "client_id": CID}, timeout=30).json()
    if not y.get("access_token"): return None
    y.setdefault("refresh_token", rt); save(y); return y["access_token"]
def get_token():
    x = load(); t = x.get("access_token")
    if not t: sys.exit("No access_token in token.json.")
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
    h = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json",
         "Accept": "application/json, text/event-stream"}
    if SESSION: h["MCP-Session-ID"] = SESSION
    r = requests.post(BASE + "/mcp", headers=h, json={"jsonrpc": "2.0", "id": 1, "method": method,
                      "params": params}, timeout=timeout)
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
        call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                            "clientInfo": {"name": "qwen-e2llm-wiki", "version": "1"}})
        return call(method, params, timeout)

def tool(name, arguments):
    resp = call("tools/call", {"name": name, "arguments": arguments})
    if resp.get("error"): raise RuntimeError(json.dumps(resp["error"], ensure_ascii=False))
    text = next((i.get("text") for i in resp.get("result", {}).get("content", []) if i.get("text")), "")
    if not text.strip(): return {"ok": name == "act"}
    try: return json.loads(text)
    except json.JSONDecodeError:
        print("NON-JSON from", name, ":", text[:200].replace(chr(10), " | "))
        return {"ok": name == "act", "raw_text": text}

def query_all(session, **filters):
    nodes, cursor = [], None
    for _ in range(15):
        args = {"sessionId": session}; args.update(filters)
        if cursor is not None: args["cursor"] = str(cursor)
        r = tool("query", args)
        data = r.get("data") if isinstance(r, dict) else r
        batch = next((v for v in data.values() if isinstance(v, list)), []) if isinstance(data, dict) \
            else (data if isinstance(data, list) else [])
        nodes += batch
        pag = r.get("pagination") or {} if isinstance(r, dict) else {}
        nxt = pag.get("cursor") or pag.get("nextCursor") or pag.get("next")
        if pag.get("hasMore") is False or nxt is None or str(nxt) == str(cursor): break
        cursor = nxt
    return [n for n in nodes if isinstance(n, dict)]

def model_name():
    try:
        m = requests.get("http://127.0.0.1:8080/v1/models", timeout=10).json()
        return m["data"][0]["id"] if m.get("data") else "?"
    except Exception: return "?"
MODEL = model_name()

def llm(prompt):
    r = requests.post(LLAMA, json={"model": "local",
        "messages": [{"role": "system", "content": "Return exactly one JSON object. No Markdown."},
                     {"role": "user", "content": prompt}],
        "temperature": 0.1, "max_tokens": 80,
        "chat_template_kwargs": {"enable_thinking": False}}, timeout=600)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()

def parse_choice(text):
    import ast
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"```[a-zA-Z]*", "", text).replace("```", "")
    m = re.search(r"{.*}", text, re.S)
    if not m: raise ValueError("No JSON from model: " + repr(text[:300]))
    blob = m.group(0)
    try: return json.loads(blob)
    except json.JSONDecodeError:
        fixed = re.sub(r"\bTrue\b", "true", blob); fixed = re.sub(r"\bFalse\b", "false", fixed)
        fixed = re.sub(r"\bNone\b", "null", fixed)
        try: return json.loads(fixed)
        except json.JSONDecodeError: return ast.literal_eval(blob)

def page_info(page):
    md = page.get("metadata", {}) or {}
    return {"title": page.get("title", "") or md.get("title", ""),
            "url": page.get("url", "") or md.get("url", ""), "sessionId": page.get("sessionId", "")}

BLOCKED = ("log in", "login", "create account", "sign in", "settings", "edit", "talk", "donate",
           "upload", "special:", "help:", "wikipedia:", "portal:", "category:", "template:", "file:")

def hint_text(n):
    h = n.get("hints")
    if isinstance(h, dict): return str(h.get("action", ""))
    if isinstance(h, list): return " ".join(str(x) for x in h)
    return str(h or "")

def candidates(nodes, sid, cur_url, used):
    cur_path = urlparse(cur_url).path.rstrip("/")
    seen, out = set(), []
    for n in nodes:
        nid = n.get("id"); text = (n.get("text") or "").strip()
        if not nid or not text or (sid, nid) in used: continue
        href = str(n.get("href") or ""); hint = hint_text(n)
        if not href and "navigates:" in hint: href = hint.split("navigates:", 1)[1].split()[0]
        low = (text + " " + href).lower()
        if any(w in low for w in BLOCKED): continue
        hp = urlparse(href).path if href.startswith("http") else href
        if hp and unquote(hp).rstrip("/") == unquote(cur_path): continue
        if not (href.startswith("/wiki/") or "en.wikipedia.org/wiki/" in href): continue
        if text.lower() in seen: continue
        seen.add(text.lower())
        out.append({"id": nid, "text": text[:50], "_href": href[-40:]})
    return out

def rank(opts, target):
    t = target.lower()
    hit = [o for o in opts if o["text"].lower() == t]
    soft = [o for o in opts if o not in hit and t in o["text"].lower()]
    rest = [o for o in opts if o not in hit and o not in soft]
    room = max(MAX_CANDIDATES - len(hit) - len(soft), 0)
    if len(rest) > room and room > 0:
        step = len(rest) / room; rest = [rest[int(i * step)] for i in range(room)]
    return hit + soft + rest[:room]

def read_release(session):
    facts = {"first_released": None, "raw": []}
    months = "January|February|March|April|May|June|July|August|September|October|November|December"
    date_re = r"(\d{1,2}\s+(?:" + months + r")\s+\d{4}|(?:" + months + r")\s+\d{1,2},\s+\d{4})"
    try:
        r = tool("read_page", {"sessionId": session, "selector": "infobox"})
        content = r.get("content", "") if isinstance(r, dict) else ""
        m = re.search(r"First released\s*\|\s*([^|]+)\|", content)
        row = m.group(1) if m else ""
        facts["raw"].append(row.strip()[:120])
        d = re.search(date_re, row)
        if d: facts["first_released"] = d.group(1)
    except Exception as e:
        print("read_page failed:", str(e)[:120])
    return facts

def log(rec):
    with open(LOG, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False) + chr(10))

os.makedirs("logs", exist_ok=True)
print("Task: from Samsung Galaxy Note series, open", TARGET_TEXT, "and report its first release date")
call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "qwen-e2llm-wiki", "version": "1"}})
tabs = tool("list_tabs", {}).get("tabs", [])
if not tabs: sys.exit("No browser tabs.")
tab = next((t for t in tabs if t.get("active")), tabs[0]); tab_id = tab["id"]
print("Tab:", tab_id, "| Start URL:", tab.get("url", ""))
if "wikipedia.org" in (tab.get("url") or ""):
    try:
        p = tool("sifr_capture", {"tabId": tab_id, "preset": "normal"})
        tool("act", {"sessionId": p.get("sessionId", ""), "action": "navigate", "target": "https://example.com/",
                     "idempotencyKey": "wiki-reset-" + str(int(time.time()))})
        print("reset: moved tab to example.com"); time.sleep(3)
    except Exception as e:
        print("reset failed:", str(e)[:120])

used = set(); verdict = None; VISITED = []
for step in range(1, MAX_STEPS + 1):
    t0 = time.time()
    try:
        page = tool("sifr_capture", {"tabId": tab_id, "preset": "normal"})
        before = page_info(page); url = before["url"]; VISITED.append(url)
        on_wiki = "wikipedia.org" in url
        on_target = TARGET_PATH in url
        nxt = 0 if not on_wiki else (2 if on_target else 1)
        print(); print("-" * 55); print("STEP", step, "| BRAIN:", MODEL, "| page:", before["title"][:60], "|", url[:80])
        if not before["sessionId"]: print("No sessionId. Stop."); break

        options, facts = [], None
        if nxt == 0:
            prompt = ("You are on " + url + ". MISSION step 0: go to " + START + ". "
                      'Return only {"action":"navigate","target":"' + START + '"}')
        elif nxt == 1:
            nodes = query_all(before["sessionId"], salience="interactive")
            options = rank(candidates(nodes, before["sessionId"], url, used), TARGET_TEXT)
            print("interactive:", len(nodes), "| candidates:", len(options))
            for o in options: print("  ", o["id"], "|", o["text"], "|", o.get("_href", ""))
            options = [{"id": o["id"], "text": o["text"]} for o in options]
            if not options: print("No candidates. Stop."); break
            task = "click the link whose text is exactly " + json.dumps(TARGET_TEXT) + " and nothing more"
            prompt = ("You are on Wikipedia: " + before["title"] + ". YOUR TASK NOW: " + task + ". "
                      "Pick the one candidate that does exactly this task. "
                      'Return only {"action":"click","target":"ID"} with an id from CANDIDATES. '
                      "CANDIDATES=" + json.dumps(options, ensure_ascii=False) + " TASK AGAIN: " + task + ".")
        else:
            facts = read_release(before["sessionId"])
            print("EYES read:", facts["first_released"], "| raw:", facts["raw"][:2])
            prompt = ("FACTS read from the Wikipedia infobox: device=" + json.dumps(TARGET_TEXT) +
                      ", first_released=" + json.dumps(facts["first_released"]) + ". "
                      "Copy these facts into the report. "
                      'Return only {"action":"report","device":"...","first_released":"..."}')

        raw = llm(prompt); print("Model:", raw.replace(chr(10), " ")[:200])
        decision = parse_choice(raw); action = decision.get("action")
        rec = {"step": step, "time": datetime.now().isoformat(), "brain": MODEL, "before": before,
               "next": nxt, "candidates": options, "facts": facts, "raw": raw, "decision": decision}

        if action == "report":
            got = str(decision.get("first_released", "")).strip()
            verdict = (got == EXPECTED_DATE)
            print("REPORT:", json.dumps(decision, ensure_ascii=False))
            print("EXPECTED first_released:", EXPECTED_DATE, "| eyes read:", facts["first_released"],
                  "->", "PASS" if verdict else "FAIL")
            rec.update({"status": "report", "verdict": verdict, "seconds": round(time.time() - t0, 1)})
            log(rec); break
        if action == "navigate":
            if on_wiki or str(decision.get("target", "")).rstrip("/") != START.rstrip("/"):
                raise ValueError("Bad navigate: " + repr(decision))
            res = tool("act", {"sessionId": before["sessionId"], "action": "navigate", "target": START,
                               "idempotencyKey": "wiki-nav-" + str(step)})
            print("ACT:", res.get("result")); rec.update({"status": "ok", "act": res}); log(rec)
            time.sleep(4); continue
        if action != "click": raise ValueError("Invalid decision: " + repr(decision))
        target = decision.get("target")
        if target not in {o["id"] for o in options}: raise ValueError("Target not in candidates: " + repr(decision))
        sel = next(o for o in options if o["id"] == target); print("Clicking:", sel)
        res = tool("act", {"sessionId": before["sessionId"], "action": "click", "target": target,
                           "idempotencyKey": "wiki-" + str(step) + "-" + target})
        print("ACT:", res.get("result"), res.get("newUrl", "")[:80])
        used.add((before["sessionId"], target))
        rec.update({"status": "ok", "selected": sel, "act": res, "seconds": round(time.time() - t0, 1)})
        log(rec); time.sleep(3)
    except Exception as e:
        import traceback
        print("ERROR:", type(e).__name__, str(e)[:200]); traceback.print_exc(limit=2)
        log({"step": step, "status": "error", "error": type(e).__name__ + ": " + str(e)[:200]}); break

print(); print("RESULT:", {True: "TASK COMPLETE (PASS)", False: "TASK FAILED", None: "NOT COMPLETE"}[verdict])
print("Trail:", " -> ".join(urlparse(u).path for u in VISITED))
print("Log:", LOG)
