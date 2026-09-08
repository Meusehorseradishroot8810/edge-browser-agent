import json, re, time, os, sys, subprocess, posixpath
from datetime import datetime
from urllib.parse import urlparse
import requests

BASE = "https://mcp.e2llm.com"
CID = "e2llm-extension"
LLAMA = "http://127.0.0.1:8080/v1/chat/completions"
SITE = "https://books.toscrape.com/"
MAX_STEPS = 6
MAX_CANDIDATES = 10
LOG = "logs/toscrape_task_lfm25.jsonl"
MODEL = "LFM2.5-1.2B-Q4_K_M (llama.cpp, local)"

CATEGORY = "Travel"
BOOK = "It's Only the Himalayas"
EXPECTED = {"price": "£45.17", "rating": "Two", "stock": "In stock"}

def _norm(k, v):
    v = str(v).strip()
    if k == "rating":
        words = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5"}
        v = words.get(v.lower(), v)
    return v
SESSION = None

def load():
    try:
        with open("token.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save(x):
    with open("token.json", "w", encoding="utf-8") as f:
        json.dump(x, f)

def refresh(x):
    rt = x.get("refresh_token")
    if not rt:
        return None
    r = requests.post(BASE + "/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": rt, "client_id": CID
    }, timeout=30)
    y = r.json()
    if not y.get("access_token"):
        print("Token refresh failed:", y)
        return None
    y.setdefault("refresh_token", rt)
    save(y)
    print("Token refreshed.")
    return y["access_token"]

def get_token():
    x = load()
    token = x.get("access_token")
    if not token:
        sys.exit("No access_token in token.json.")
    try:
        r = requests.get(BASE + "/mcp",
                         headers={"Authorization": "Bearer " + token}, timeout=15)
        if r.status_code != 401:
            return token
    except Exception:
        return token
    print("Token expired.")
    token = refresh(x)
    if not token:
        sys.exit("Token refresh failed.")
    return token

TOKEN = get_token()

def call(method, params, timeout=120):
    global SESSION, TOKEN
    headers = {"Authorization": "Bearer " + TOKEN,
               "Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    if SESSION:
        headers["MCP-Session-ID"] = SESSION
    response = requests.post(BASE + "/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params
    }, timeout=timeout)
    if response.status_code == 401:
        TOKEN = refresh(load())
        if not TOKEN:
            sys.exit("Token refresh failed.")
        return call(method, params, timeout)
    response.raise_for_status()
    if method == "initialize":
        SESSION = response.headers.get("mcp-session-id", "")
    return response.json()

def tool(name, arguments):
    response = call("tools/call", {"name": name, "arguments": arguments})
    if response.get("error"):
        raise RuntimeError(json.dumps(response["error"], ensure_ascii=False))
    content = response.get("result", {}).get("content", [])
    text = next((item.get("text") for item in content if item.get("text")), "")
    if name == "act" and not text.strip():
        return {"ok": True, "raw": response}
    if not text.strip():
        raise RuntimeError("Empty response from " + name + ": " +
                           json.dumps(response, ensure_ascii=False)[:1200])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print("NON-JSON from", name, ":", text[:300].replace(chr(10), " | "))
        return {"ok": name == "act", "raw_text": text}

def qwen(prompt):
    response = requests.post(LLAMA, json={
        "model": "local",
        "messages": [
            {"role": "system", "content": "Return exactly one JSON object. No Markdown."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1, "max_tokens": 80,
        "chat_template_kwargs": {"enable_thinking": False}
    }, timeout=600)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()

def parse_choice(text):
    import ast
    text = re.sub(r"```[a-zA-Z]*", "", text).replace("```", "")
    match = re.search(r"{.*}", text, re.S)
    if not match:
        raise ValueError("No JSON from model: " + repr(text[:500]))
    blob = match.group(0)
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        fixed = re.sub(r"\bTrue\b", "true", blob)
        fixed = re.sub(r"\bFalse\b", "false", fixed)
        fixed = re.sub(r"\bNone\b", "null", fixed)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            return ast.literal_eval(blob)

def device_info():
    def run(command):
        try:
            return subprocess.check_output(command, shell=True, text=True).strip()
        except Exception:
            return ""
    total_kb = 0
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1]); break
    except Exception:
        pass
    return {"device": (run("getprop ro.product.manufacturer") + " " +
                       run("getprop ro.product.model")).strip(),
            "android": run("getprop ro.build.version.release"),
            "ram_gb": round(total_kb / 1048576, 1) if total_kb else None}

DEVICE = device_info()
BROWSER_FACTS = {"viewport": None, "extension": None}

def page_info(page):
    metadata = page.get("metadata", {}) or {}
    vp = metadata.get("viewport")
    if isinstance(vp, dict):
        BROWSER_FACTS["viewport"] = str(vp.get("width", "?")) + "x" + str(vp.get("height", "?"))
    if metadata.get("extensionVersion"):
        BROWSER_FACTS["extension"] = str(metadata["extensionVersion"])
    return {"title": page.get("title", "") or metadata.get("title", ""),
            "url": page.get("url", "") or metadata.get("url", ""),
            "sessionId": page.get("sessionId", "")}

def banner(step):
    print()
    print("-" * 55)
    print("STEP", step, "OF", MAX_STEPS)
    print("BRAIN   :", MODEL)
    print("PHONE   :", DEVICE["device"], "| Android", DEVICE["android"],
          "|", DEVICE["ram_gb"], "GB RAM")
    print("EYES    : E2LLM extension", BROWSER_FACTS["extension"] or "",
          "in desktop Chrome | viewport", BROWSER_FACTS["viewport"] or "?")
    print("-" * 55)

# ---- goal memory ----
VISITED = []

def on_book_page(url):
    return "its-only-the-himalayas" in url

def progress():
    done = []
    if any("travel_2" in u for u in VISITED):
        done.append(1)
    if any(on_book_page(u) for u in VISITED):
        done.append(2)
    return done

def next_step(url, done):
    if on_book_page(url):
        return 3
    if 1 in done and "travel_2" in url:
        return 2
    return 1

STEP_TARGET = {1: CATEGORY, 2: BOOK}

BLOCKED = ("login", "log in", "logout", "log out", "sign in", "sign out",
           "submit", "buy", "pay", "purchase", "checkout", "basket", "cart",
           "delete", "remove", "settings", "account", "profile")

def query_all(session, **filters):
    nodes, cursor = [], None
    for _ in range(10):
        args = {"sessionId": session}
        args.update(filters)
        if cursor is not None:
            args["cursor"] = str(cursor)
        r = tool("query", args)
        if isinstance(r, list):
            nodes += r; break
        data = r.get("data")
        if isinstance(data, dict):
            batch = next((v for v in data.values() if isinstance(v, list)), [])
        elif isinstance(data, list):
            batch = data
        else:
            batch = []
        nodes += batch
        pag = r.get("pagination") or {}
        nxt = pag.get("cursor") or pag.get("nextCursor") or pag.get("next")
        if pag.get("hasMore") is False or nxt is None or str(nxt) == str(cursor):
            break
        cursor = nxt
    return [n for n in nodes if isinstance(n, dict)]

def hint_text(node):
    h = node.get("hints")
    if isinstance(h, dict):
        return str(h.get("action", ""))
    if isinstance(h, list):
        return " ".join(str(x) for x in h)
    return str(h or "")

def href_path(href):
    if not href:
        return ""
    p = urlparse(href)
    return p.path if p.scheme else href

def get_candidates(nodes, sid, current_url, used):
    cur_path = urlparse(current_url).path.rstrip("/")
    cur_dir = posixpath.dirname(cur_path)
    seen_text, choices = set(), []
    for node in nodes:
        node_id = node.get("id")
        if not node_id or (sid, node_id) in used:
            continue
        text = (node.get("text") or "").strip()
        if not text:
            continue
        hint = hint_text(node)
        href = str(node.get("href") or "")
        if not href and "navigates:" in hint:
            href = hint.split("navigates:", 1)[1].split()[0]
        if any(w in (text + " " + hint + " " + href).lower() for w in BLOCKED):
            continue
        hp = href_path(href).rstrip("/")
        if hp and hp in (cur_path, cur_dir, cur_dir + "/index.html"):
            continue
        key = text.lower()
        if key in seen_text:
            continue
        seen_text.add(key)
        choices.append({"id": node_id, "text": text[:50], "_dir": posixpath.dirname(hp)})
    return choices

def rank(options, target):
    t = target.lower()
    hit = [o for o in options if t in o["text"].lower()]
    rest = [o for o in options if o not in hit]
    room = max(MAX_CANDIDATES - len(hit), 0)
    groups = {}
    for o in rest:
        groups.setdefault(o["_dir"], []).append(o)
    picked = []
    while len(picked) < room and any(groups.values()):
        for d in list(groups.keys()):
            if groups[d] and len(picked) < room:
                picked.append(groups[d].pop(0))
    return [{k: v for k, v in o.items() if k != "_dir"} for o in hit + picked]

# ---- the eyes: structured facts from the product page ----
def read_facts(session):
    facts = {"price": None, "rating": None, "stock": None, "raw": []}
    try:
        for n in query_all(session, selector="product_main"):
            t = (n.get("text") or "").strip()
            m = re.search(r"£\d+\.\d\d", t)
            if m:
                facts["price"] = m.group(0); facts["raw"].append("main:" + t[:40]); break
    except Exception as e:
        print("product_main query failed:", str(e)[:120])
    try:
        nodes = query_all(session, text="£")
        for n in nodes:
            facts["raw"].append((n.get("text") or "").strip()[:60])
        if not facts["price"]:
            for n in nodes:
                t = (n.get("text") or "").strip()
                if re.fullmatch(r"£\d+\.\d\d", t):
                    facts["price"] = t; break
        if not facts["price"]:
            for n in nodes:
                m = re.search(r"£\d+\.\d\d", (n.get("text") or ""))
                if m:
                    facts["price"] = m.group(0); break
    except Exception as e:
        print("price query failed:", str(e)[:120])
    try:
        for n in query_all(session, text="stock"):
            t = (n.get("text") or "").strip()
            if "stock" in t.lower() and not facts["stock"]:
                facts["stock"] = "In stock" if "in stock" in t.lower() else t[:40]
    except Exception as e:
        print("stock query failed:", str(e)[:120])
    try:
        for n in query_all(session, selector="star-rating"):
            blob = json.dumps(n, ensure_ascii=False)
            m = re.search(r"star-rating\s+(One|Two|Three|Four|Five)", blob)
            if m:
                facts["rating"] = m.group(1); break
    except Exception as e:
        print("rating query failed:", str(e)[:120])
    return facts

def build_prompt(nxt, options, facts=None):
    if nxt == 0:
        return ("MISSION step 0: go to " + SITE + ". "
                'Return only {"action":"navigate","target":"' + SITE + '"}')
    if nxt == 3:
        return (
            "FACTS read from the product page: "
            "book=" + json.dumps(BOOK) + ", price=" + json.dumps(facts["price"]) +
            ", rating=" + json.dumps(facts["rating"]) + ", stock=" + json.dumps(facts["stock"]) + ". "
            "Copy these facts into the report. "
            'Return only {"action":"report","book":"...","price":"...","rating":"...","stock":"..."}'
        )
    target = STEP_TARGET[nxt]
    return (
        "YOUR TASK NOW: click the link whose text is exactly " + json.dumps(target) + ". "
        'Return only {"action":"click","target":"ID"} with the id of that candidate. '
        "CANDIDATES=" + json.dumps(options, ensure_ascii=False) + " "
        "TASK AGAIN: click the link whose text is exactly " + json.dumps(target) + "."
    )

def log(record):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + chr(10))

os.makedirs("logs", exist_ok=True)
print("Task: find", BOOK, "in", CATEGORY, "and report price / rating / stock")
print("=" * 55)
print(json.dumps(DEVICE, ensure_ascii=False))
print("=" * 55)

call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "qwen-e2llm", "version": "2.1"}})

tabs_data = tool("list_tabs", {})
if tabs_data.get("extensionConnected") is False:
    sys.exit(tabs_data.get("message", "E2LLM extension disconnected."))
tabs = tabs_data.get("tabs", [])
if not tabs:
    sys.exit("No browser tabs in connected browser.")
tab = next((t for t in tabs if t.get("active")), tabs[0])
tab_id = tab["id"]
browser = tab.get("browser")
def with_browser(args):
    if browser:
        args["browser"] = browser
    return args
print("Tab:", tab_id, "| Start URL:", tab.get("url", ""))
if "toscrape.com" in (tab.get("url") or ""):
    try:
        _p = tool("sifr_capture", with_browser({"tabId": tab_id, "preset": "normal"}))
        tool("act", with_browser({"sessionId": _p.get("sessionId", ""), "action": "navigate",
                     "target": "https://example.com/", "idempotencyKey": "reset-" + str(int(time.time()))}))
        print("reset: moved tab to example.com before the run")
        time.sleep(3)
    except Exception as _e:
        print("reset failed:", type(_e).__name__, str(_e)[:200])
if "toscrape.com" in (tab.get("url") or ""):
    _p = tool("sifr_capture", with_browser({"tabId": tab_id, "preset": "normal"}))
    tool("act", {"sessionId": _p.get("sessionId", ""), "action": "navigate",
                 "target": "https://example.com/", "idempotencyKey": "reset-" + str(int(time.time()))})
    print("reset: moved tab to example.com before the run")
    time.sleep(3)


used = set()
verdict = None

for step in range(1, MAX_STEPS + 1):
    started = time.time()
    try:
        page_before = tool("sifr_capture", with_browser({"tabId": tab_id, "preset": "normal"}))
        before = page_info(page_before)
        on_site = "toscrape.com" in before["url"]
        if on_site:
            VISITED.append(before["url"])
        done = progress() if on_site else []
        nxt = next_step(before["url"], done) if on_site else 0

        banner(step)
        print("Before:", before["title"], before["url"])
        print("Session:", before["sessionId"], "| done:", done, "| next:", nxt)
        if not before["sessionId"]:
            print("Capture has no sessionId. Stop."); break

        options, facts = [], None
        if nxt in (1, 2):
            nodes = query_all(before["sessionId"], salience="interactive")
            print("interactive:", len(nodes))
            options = rank(get_candidates(nodes, before["sessionId"], before["url"], used),
                           STEP_TARGET[nxt])
            print("Candidates:", len(options))
            for o in options:
                print("  ", o["id"], "|", o["text"])
            if not options:
                print("No candidates. Stop."); break
        elif nxt == 3:
            facts = read_facts(before["sessionId"])
            print("EYES read:", json.dumps({k: v for k, v in facts.items() if k != "raw"}, ensure_ascii=False))
            print("EYES raw £ nodes:", facts["raw"][:5])

        prompt = build_prompt(nxt, options, facts)
        raw = qwen(prompt)
        decision = parse_choice(raw)
        print("Model:", raw)

        record = {"step": step, "time": datetime.now().isoformat(), "brain": MODEL,
                  "phone": DEVICE, "eyes": dict(BROWSER_FACTS), "before": before,
                  "done": done, "next": nxt, "candidates": options, "facts": facts,
                  "qwen": raw, "decision": decision}
        action = decision.get("action")

        if action == "report":
            checks = {k: (_norm(k, decision.get(k, "")) == _norm(k, EXPECTED[k])) for k in EXPECTED}
            verdict = all(checks.values())
            print("REPORT:", json.dumps(decision, ensure_ascii=False))
            print("EXPECTED:", json.dumps(EXPECTED, ensure_ascii=False))
            print("CHECKS:", checks, "->", "PASS" if verdict else "FAIL")
            record.update({"status": "report", "checks": checks, "verdict": verdict,
                           "seconds": round(time.time() - started, 2)})
            log(record); break

        if action == "navigate":
            if on_site or str(decision.get("target", "")).strip().rstrip("/") != SITE.rstrip("/"):
                raise ValueError("Bad navigate: " + repr(decision))
            act_result = tool("act", with_browser({
                "sessionId": before["sessionId"], "action": "navigate",
                "target": SITE, "idempotencyKey": "task-nav-" + str(step)}))
            print("ACT:", json.dumps(act_result, ensure_ascii=False)[:200])
            record.update({"status": "ok", "act": act_result,
                           "seconds": round(time.time() - started, 2)})
            log(record); time.sleep(3); continue

        if action != "click":
            raise ValueError("Invalid decision: " + repr(decision))
        target = decision.get("target")
        if target not in {o["id"] for o in options}:
            raise ValueError("Target not in candidates: " + repr(decision))
        selected = next(o for o in options if o["id"] == target)
        print("Clicking:", selected)
        act_result = tool("act", with_browser({
            "sessionId": before["sessionId"], "action": "click", "target": target,
            "idempotencyKey": "task-" + str(step) + "-" + target}))
        print("ACT:", json.dumps(act_result, ensure_ascii=False)[:200])
        used.add((before["sessionId"], target))
        record.update({"status": "ok", "selected": selected, "act": act_result,
                       "after_url": act_result.get("newUrl", ""),
                       "seconds": round(time.time() - started, 2)})
        log(record); time.sleep(2)

    except Exception as error:
        import traceback
        print("ERROR:", type(error).__name__, str(error))
        traceback.print_exc(limit=2)
        log({"step": step, "time": datetime.now().isoformat(), "status": "error",
             "error": type(error).__name__ + ": " + str(error)})
        break

print()
print("RESULT:", {True: "TASK COMPLETE - report verified (PASS)",
                  False: "TASK FAILED - report did not match expected",
                  None: "NOT COMPLETE"}[verdict])
print("Trail:", " -> ".join(urlparse(u).path for u in VISITED))
print("Log:", LOG)
