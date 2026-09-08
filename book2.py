import json, re, time, os, sys
from datetime import datetime
from urllib.parse import urlparse
import requests

BASE = "https://mcp.e2llm.com"; CID = "e2llm-extension"
LLAMA = "http://127.0.0.1:8080/v1/chat/completions"
SITE = "https://books.toscrape.com/"
BOOK = "It's Only the Himalayas"
EXPECTED = {"title": "It's Only the Himalayas", "price": "£45.17", "rating": "Two", "stock": "In stock", "upc": "a22124811bfa8350"}
MAX_STEPS = 6; MAX_CANDIDATES = 10
LOG = "logs/book2_upc.jsonl"; SESSION = None

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
        call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "qwen-e2llm-book2", "version": "1"}})
        return call(method, params, timeout)

def tool(name, arguments):
    resp = call("tools/call", {"name": name, "arguments": arguments})
    if resp.get("error"): raise RuntimeError(json.dumps(resp["error"], ensure_ascii=False))
    text = next((i.get("text") for i in resp.get("result", {}).get("content", []) if i.get("text")), "")
    if not text.strip(): return {"ok": name == "act"}
    try: return json.loads(text)
    except json.JSONDecodeError:
        print("NON-JSON from", name, ":", text[:200].replace(chr(10), " | ")); return {"ok": name == "act", "raw_text": text}

def query_all(session, **filters):
    nodes, cursor = [], None
    for _ in range(15):
        args = {"sessionId": session}; args.update(filters)
        if cursor is not None: args["cursor"] = str(cursor)
        r = tool("query", args)
        data = r.get("data") if isinstance(r, dict) else r
        batch = next((v for v in data.values() if isinstance(v, list)), []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        nodes += batch
        pag = (r.get("pagination") or {}) if isinstance(r, dict) else {}
        nxt = pag.get("cursor") or pag.get("nextCursor") or pag.get("next")
        if pag.get("hasMore") is False or nxt is None or str(nxt) == str(cursor): break
        cursor = nxt
    return [n for n in nodes if isinstance(n, dict)]

def model_name():
    try:
        m = requests.get("http://127.0.0.1:8080/v1/models", timeout=10).json(); return m["data"][0]["id"] if m.get("data") else "?"
    except Exception: return "?"
MODEL = model_name()

def llm(prompt):
    r = requests.post(LLAMA, json={"model": "local", "messages": [
        {"role": "system", "content": "Return exactly one JSON object. No Markdown."}, {"role": "user", "content": prompt}],
        "temperature": 0.1, "max_tokens": 120, "chat_template_kwargs": {"enable_thinking": False}}, timeout=600)
    r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()

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

def page_info(p):
    md = p.get("metadata", {}) or {}
    return {"title": p.get("title", "") or md.get("title", ""), "url": p.get("url", "") or md.get("url", ""), "sessionId": p.get("sessionId", "")}

BLOCKED = ("login", "log in", "sign in", "basket", "cart", "checkout", "buy", "account")
def hint_text(n):
    h = n.get("hints")
    if isinstance(h, dict): return str(h.get("action", ""))
    if isinstance(h, list): return " ".join(str(x) for x in h)
    return str(h or "")

def candidates(nodes, sid, cur_url, used):
    cur_path = urlparse(cur_url).path.rstrip("/"); seen, out = set(), []
    for n in nodes:
        nid = n.get("id"); text = (n.get("text") or "").strip()
        if not nid or not text or (sid, nid) in used: continue
        href = str(n.get("href") or ""); hint = hint_text(n)
        if not href and "navigates:" in hint: href = hint.split("navigates:", 1)[1].split()[0]
        if any(w in (text + " " + href).lower() for w in BLOCKED): continue
        hp = urlparse(href).path if href.startswith("http") else href
        if hp and hp.rstrip("/") == cur_path: continue
        if text.lower() in seen: continue
        seen.add(text.lower()); out.append({"id": nid, "text": text[:50]})
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

def read_facts(session):
    f = {"title": None, "price": None, "rating": None, "stock": None, "upc": None, "raw": []}
    try:
        r = tool("read_page", {"sessionId": session, "selector": "product_page"})
        c = r.get("content", "") if isinstance(r, dict) else ""
        f["raw"].append(c[:300].replace(chr(10), " "))
        m = re.search(r"\|\s*UPC\s*\|\s*([0-9a-f]{8,})\s*\|", c, re.I);                      f["upc"] = m.group(1) if m else None
        m = re.search(r"£\d+\.\d\d", c);                                                     f["price"] = m.group(0) if m else None
        m = re.search(r"In stock", c, re.I);                                                 f["stock"] = "In stock" if m else None
        m = re.search(r"^(?:#\s*)?(.+?)\s*$", c.split(chr(10))[1] if chr(10) in c else "", re.M)
    except Exception as e: print("read_page failed:", str(e)[:120])
    try:
        for n in query_all(session, selector="product_main"):
            if str(n.get("tag", "")).lower() == "h1" and n.get("text"): f["title"] = n["text"].strip(); break
        if not f["title"]:
            for n in query_all(session, tag="h1"):
                if n.get("text"): f["title"] = n["text"].strip(); break
    except Exception as e: print("title query failed:", str(e)[:120])
    try:
        for n in query_all(session, selector="star-rating"):
            m = re.search(r"star-rating\s+(One|Two|Three|Four|Five)", json.dumps(n, ensure_ascii=False))
            if m: f["rating"] = m.group(1); break
    except Exception as e: print("rating query failed:", str(e)[:120])
    return f

def log(rec):
    with open(LOG, "a", encoding="utf-8") as fh: fh.write(json.dumps(rec, ensure_ascii=False) + chr(10))

os.makedirs("logs", exist_ok=True)
print("Task: from books.toscrape.com home, find", BOOK, "and report title/price/rating/stock/UPC")
call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "qwen-e2llm-book2", "version": "1"}})
tabs = tool("list_tabs", {}).get("tabs", [])
if not tabs: sys.exit("No browser tabs.")
tab = next((t for t in tabs if t.get("active")), tabs[0]); tab_id = tab["id"]
print("Tab:", tab_id, "| Start URL:", tab.get("url", ""))
if "toscrape.com" in (tab.get("url") or ""):
    try:
        p = tool("sifr_capture", {"tabId": tab_id, "preset": "normal"})
        tool("act", {"sessionId": p.get("sessionId", ""), "action": "navigate", "target": "https://example.com/", "idempotencyKey": "b2-reset-" + str(int(time.time()))})
        print("reset: moved tab to example.com"); time.sleep(3)
    except Exception as e: print("reset failed:", str(e)[:120])

used = set(); verdict = None; VISITED = []
for step in range(1, MAX_STEPS + 1):
    t0 = time.time()
    try:
        page = tool("sifr_capture", {"tabId": tab_id, "preset": "normal"})
        before = page_info(page); url = before["url"]; VISITED.append(url)
        on_site = "toscrape.com" in url; on_book = "its-only-the-himalayas" in url
        nxt = 0 if not on_site else (2 if on_book else 1)
        print(); print("-" * 55); print("STEP", step, "| BRAIN:", MODEL, "| page:", before["title"][:50], "|", url[:80])
        if not before["sessionId"]: print("No sessionId. Stop."); break
        options, facts = [], None
        if nxt == 0:
            prompt = ("You are on " + url + ". MISSION step 0: go to " + SITE + ". " 'Return only {"action":"navigate","target":"' + SITE + '"}')
        elif nxt == 1:
            nodes = query_all(before["sessionId"], salience="interactive")
            options = rank(candidates(nodes, before["sessionId"], url, used), BOOK)
            print("interactive:", len(nodes), "| candidates:", len(options))
            for o in options: print("  ", o["id"], "|", o["text"])
            if not options: print("No candidates. Stop."); break
            task = "find the book " + json.dumps(BOOK) + " and click the link whose text is exactly its title"
            prompt = ("You are on books.toscrape.com: " + before["title"][:60] + ". YOUR TASK NOW: " + task + ". "
                      "If the book is not in CANDIDATES, click a category or page link that could lead to it. "
                      'Return only {"action":"click","target":"ID"} with an id from CANDIDATES. '
                      "CANDIDATES=" + json.dumps(options, ensure_ascii=False) + " TASK AGAIN: " + task + ".")
        else:
            facts = read_facts(before["sessionId"])
            print("EYES read:", json.dumps({k: v for k, v in facts.items() if k != "raw"}, ensure_ascii=False))
            prompt = ("FACTS read from the product page: title=" + json.dumps(facts["title"]) + ", price=" + json.dumps(facts["price"]) +
                      ", rating=" + json.dumps(facts["rating"]) + ", stock=" + json.dumps(facts["stock"]) + ", upc=" + json.dumps(facts["upc"]) + ". "
                      "Copy these facts into the report exactly. "
                      'Return only {"action":"report","title":"...","price":"...","rating":"...","stock":"...","upc":"..."}')
        raw = llm(prompt); print("Model:", raw.replace(chr(10), " ")[:220])
        d = parse_choice(raw); action = d.get("action")
        rec = {"step": step, "time": datetime.now().isoformat(), "brain": MODEL, "before": before, "next": nxt,
               "candidates": options, "facts": facts, "raw": raw, "decision": d}
        if action == "report":
            exp = dict(EXPECTED); exp["upc"] = EXPECTED["upc"] or facts["upc"]
            checks = {k: str(d.get(k, "")).strip() == str(exp[k]) for k in exp}
            verdict = all(checks.values()) and facts["upc"] is not None
            print("REPORT:", json.dumps(d, ensure_ascii=False)); print("EXPECTED:", json.dumps(exp, ensure_ascii=False))
            print("CHECKS:", checks, "->", "PASS" if verdict else "FAIL")
            rec.update({"status": "report", "checks": checks, "verdict": verdict, "seconds": round(time.time() - t0, 1)}); log(rec); break
        if action == "navigate":
            if on_site or str(d.get("target", "")).rstrip("/") != SITE.rstrip("/"): raise ValueError("Bad navigate: " + repr(d))
            res = tool("act", {"sessionId": before["sessionId"], "action": "navigate", "target": SITE, "idempotencyKey": "b2-nav-" + str(step)})
            print("ACT:", res.get("result")); rec.update({"status": "ok", "act": res}); log(rec); time.sleep(3); continue
        if action != "click": raise ValueError("Invalid decision: " + repr(d))
        target = d.get("target")
        if target not in {o["id"] for o in options}: raise ValueError("Target not in candidates: " + repr(d))
        sel = next(o for o in options if o["id"] == target); print("Clicking:", sel)
        res = tool("act", {"sessionId": before["sessionId"], "action": "click", "target": target, "idempotencyKey": "b2-" + str(step) + "-" + target})
        print("ACT:", res.get("result"), res.get("newUrl", "")[:80]); used.add((before["sessionId"], target))
        rec.update({"status": "ok", "selected": sel, "act": res, "seconds": round(time.time() - t0, 1)}); log(rec); time.sleep(2)
    except Exception as e:
        import traceback; print("ERROR:", type(e).__name__, str(e)[:200]); traceback.print_exc(limit=2)
        log({"step": step, "status": "error", "error": type(e).__name__ + ": " + str(e)[:200]}); break

print(); print("RESULT:", {True: "TASK COMPLETE (PASS)", False: "TASK FAILED", None: "NOT COMPLETE"}[verdict])
print("Trail:", " -> ".join(urlparse(u).path for u in VISITED)); print("Log:", LOG)
