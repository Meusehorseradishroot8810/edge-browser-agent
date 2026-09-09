import json, re, time, os, sys, subprocess
from datetime import datetime
from urllib.parse import urlparse, unquote
import requests

BASE = "https://mcp.e2llm.com"
CID = "e2llm-extension"
LLAMA = "http://127.0.0.1:8080/v1/chat/completions"
START = "https://github.com/e2llm"                 # org page; the task starts from an unrelated site
REPO_TEXT = "edge-browser-agent"                   # step 1: click the repo by name
REPO_PATH = "/e2llm/edge-browser-agent"
FOLDER_TEXT = "logs"                                # step 2: click the folder by name
FOLDER_PATH = "/tree/main/logs"
API = "https://api.github.com/repos/e2llm/edge-browser-agent"   # ground truth, fetched at report time
MAX_STEPS = 6
MAX_CANDIDATES = 10
LOG = "logs/github_stars_ff.jsonl"
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
                            "clientInfo": {"name": "qwen-e2llm-github", "version": "1"}})
        return call(method, params, timeout)

BROWSER = os.environ.get("E2LLM_BROWSER", "")
def tool(name, arguments):
    if BROWSER and name in ("sifr_capture", "list_tabs") and "browser" not in arguments:
        arguments = dict(arguments, browser=BROWSER)
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

BLOCKED = ("log in", "login", "sign in", "sign up", "settings", "pricing", "marketplace", "sponsor",
           "notifications", "/issues", "/pulls", "/actions", "/security", "/commits", "/stargazers", "/forks", "#")

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
        if not (href.startswith("/") or "github.com/" in href): continue
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

def read_stars(session):
    facts = {"stars": None, "raw": []}
    try:
        r = tool("read_page", {"sessionId": session})
        content = r.get("content", "") if isinstance(r, dict) else ""
        m = re.search(r"\bStar(?:s|red)?\b\D{0,12}(\d[\d,]*)", content) or re.search(r"(\d[\d,]*)\s+stars?\b", content, re.I)
        if m:
            facts["stars"] = int(m.group(1).replace(",", "")); facts["raw"].append(m.group(0)[:60])
    except Exception as e:
        print("read_page failed:", str(e)[:120])
    return facts

def count_log_files(session):
    facts = {"log_files": None, "raw": []}
    try:
        nodes = query_all(session, salience="interactive")
        names = set()
        for n in nodes:
            href = str(n.get("href") or ""); hint = hint_text(n)
            if not href and "navigates:" in hint: href = hint.split("navigates:", 1)[1].split()[0]
            if "/blob/main/logs/" in href: names.add(href.split("/blob/main/logs/", 1)[1].split("?")[0])
        facts["log_files"] = len(names); facts["raw"] = sorted(names)[:3]
    except Exception as e:
        print("query failed:", str(e)[:120])
    return facts

def ground_truth():
    """GitHub API at report time. Unauthenticated limit is 60 requests/hour per IP; set GITHUB_TOKEN to lift it."""
    h = {"User-Agent": "edge-browser-agent-check", "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"): h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    out = {"stars": None, "log_files": None}
    try:
        r = requests.get(API, headers=h, timeout=20)
        if r.status_code != 200: print("API", r.status_code, r.text[:80]); return out
        out["stars"] = r.json().get("stargazers_count")
        r = requests.get(API + "/contents/logs", headers=h, timeout=20)
        if r.status_code != 200: print("API", r.status_code, r.text[:80]); return out
        out["log_files"] = len([x for x in r.json() if isinstance(x, dict) and x.get("type") == "file"])
    except Exception as e:
        print("API failed:", str(e)[:120])
    return out

def log(rec):
    with open(LOG, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False) + chr(10))

os.makedirs("logs", exist_ok=True)
print("Task: from an unrelated site, open the e2llm org on GitHub, open", REPO_TEXT, "read its star count, open", FOLDER_TEXT, "and report stars + number of log files")
call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "qwen-e2llm-github", "version": "1"}})
tabs = tool("list_tabs", {}).get("tabs", [])
if not tabs: sys.exit("No browser tabs.")
tab = next((t for t in tabs if t.get("active")), tabs[0]); tab_id = tab["id"]
BROWSER_NAME = tab.get("browser") or BROWSER or "?"
print("Browser:", BROWSER_NAME, "| Tab:", tab_id, "| Start URL:", tab.get("url", ""))
if "github.com" in (tab.get("url") or ""):
    try:
        p = tool("sifr_capture", {"tabId": tab_id, "preset": "normal"})
        tool("act", {"sessionId": p.get("sessionId", ""), "action": "navigate", "target": "https://example.com/",
                     "idempotencyKey": "gh-reset-" + str(int(time.time()))})
        print("reset: moved tab to example.com"); time.sleep(3)
    except Exception as e:
        print("reset failed:", str(e)[:120])

used = set(); verdict = None; VISITED = []; STARS = None
for step in range(1, MAX_STEPS + 1):
    t0 = time.time()
    try:
        page = tool("sifr_capture", {"tabId": tab_id, "preset": "normal"})
        before = page_info(page); url = before["url"]; VISITED.append(url)
        path = urlparse(url).path.rstrip("/")
        on_gh = "github.com" in url
        on_repo = path.startswith(REPO_PATH)
        on_folder = FOLDER_PATH in path
        nxt = 0 if not on_gh else (3 if on_folder else (2 if on_repo else 1))
        print(); print("-" * 55); print("STEP", step, "| BRAIN:", MODEL, "| page:", before["title"][:60], "|", url[:80])
        if not before["sessionId"]: print("No sessionId. Stop."); break

        options, facts = [], None
        if nxt == 0:
            prompt = ("You are on " + url + ". MISSION step 0: go to " + START + ". "
                      'Return only {"action":"navigate","target":"' + START + '"}')
        elif nxt in (1, 2):
            if nxt == 2 and STARS is None:
                STARS = read_stars(before["sessionId"]); print("EYES read stars:", STARS["stars"], "| raw:", STARS["raw"][:1])
            target_text = REPO_TEXT if nxt == 1 else FOLDER_TEXT
            nodes = query_all(before["sessionId"], salience="interactive")
            options = rank(candidates(nodes, before["sessionId"], url, used), target_text)
            print("interactive:", len(nodes), "| candidates:", len(options))
            for o in options: print("  ", o["id"], "|", o["text"], "|", o.get("_href", ""))
            options = [{"id": o["id"], "text": o["text"]} for o in options]
            if not options: print("No candidates. Stop."); break
            task = "click the link whose text is exactly " + json.dumps(target_text) + " and nothing more"
            prompt = ("You are on GitHub: " + before["title"][:60] + ". YOUR TASK NOW: " + task + ". "
                      "Pick the one candidate that does exactly this task. "
                      'Return only {"action":"click","target":"ID"} with an id from CANDIDATES. '
                      "CANDIDATES=" + json.dumps(options, ensure_ascii=False) + " TASK AGAIN: " + task + ".")
        else:
            files = count_log_files(before["sessionId"])
            if STARS is None: STARS = read_stars(before["sessionId"])
            facts = {"stars": STARS["stars"], "log_files": files["log_files"], "raw": STARS["raw"] + files["raw"]}
            print("EYES read: stars =", facts["stars"], "| log files =", facts["log_files"], "| e.g.", files["raw"][:2])
            prompt = ("FACTS read from GitHub: repo=" + json.dumps(REPO_TEXT) + ", stars=" + json.dumps(facts["stars"]) +
                      ", log_files=" + json.dumps(facts["log_files"]) + ". "
                      "Copy these facts into the report. "
                      'Return only {"action":"report","repo":"...","stars":"...","log_files":"..."}')

        raw = llm(prompt); print("Model:", raw.replace(chr(10), " ")[:200])
        decision = parse_choice(raw); action = decision.get("action")
        rec = {"step": step, "time": datetime.now().isoformat(), "brain": MODEL, "browser": BROWSER_NAME, "before": before,
               "next": nxt, "candidates": options, "facts": facts, "raw": raw, "decision": decision}

        if action == "report":
            truth = ground_truth()
            got = {k: str(decision.get(k, "")).strip() for k in ("stars", "log_files")}
            checks = {k: (truth[k] is not None and got[k] == str(truth[k])) for k in got}
            verdict = all(checks.values())
            print("REPORT:", json.dumps(decision, ensure_ascii=False))
            print("GROUND TRUTH (GitHub API):", truth, "| CHECKS:", checks, "->", "PASS" if verdict else "FAIL")
            rec.update({"status": "report", "truth": truth, "checks": checks, "verdict": verdict, "seconds": round(time.time() - t0, 1)})
            log(rec); break
        if action == "navigate":
            if on_gh or str(decision.get("target", "")).rstrip("/") != START.rstrip("/"):
                raise ValueError("Bad navigate: " + repr(decision))
            res = tool("act", {"sessionId": before["sessionId"], "action": "navigate", "target": START,
                               "idempotencyKey": "gh-nav-" + str(step)})
            print("ACT:", res.get("result")); rec.update({"status": "ok", "act": res}); log(rec)
            time.sleep(4); continue
        if action != "click": raise ValueError("Invalid decision: " + repr(decision))
        target = decision.get("target")
        if target not in {o["id"] for o in options}: raise ValueError("Target not in candidates: " + repr(decision))
        sel = next(o for o in options if o["id"] == target); print("Clicking:", sel)
        res = tool("act", {"sessionId": before["sessionId"], "action": "click", "target": target,
                           "idempotencyKey": "gh-" + str(step) + "-" + target})
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

