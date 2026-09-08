#!/usr/bin/env python3
"""
replay.py - re-run the model side of the logged runs OFFLINE.

No browser, no relay, no account. Each log line of a step contains the candidate list
(or the facts) the model saw; this script rebuilds the same prompt text the harness used,
sends it to any OpenAI-compatible local server (llama.cpp, Ollama, vLLM...) and checks the
decision against the expected one derived from the task.

Usage:
  python replay.py logs/wiki_note8.jsonl                      # default server http://127.0.0.1:8080
  python replay.py logs/toscrape_task_qwen3_06.jsonl --url http://127.0.0.1:11434/v1/chat/completions
  python replay.py logs/*.jsonl --last 0                     # all runs in the file, not only the last 10
  python replay.py logs/*.jsonl --limit 40 --think            # keep thinking mode on (Qwen3 / MiniCPM5)

What is checked:
  step 0 (navigate): target URL equals the task's start URL
  click steps:       chosen id is the candidate whose text matches the task's target text
  report step:       every field equals the fact the model was given (rating "Two" == "2")
Runs with an invalid model decision (placeholder, pseudo-code, bad target) count as failed runs.
Runs with infrastructure errors (phone network, relay) are excluded from both numerator and denominator
BEFORE the --last window is taken and before any step is replayed, unless --strict-errors is given.
Every exclusion / failure classification is printed per run.
Note: thinking mode is disabled via chat_template_kwargs (llama.cpp); other servers ignore the field silently -
for Qwen3 / MiniCPM5 on such servers pass --think and expect <think> blocks (they are stripped before parsing).
Run-level PASS here means: every replayed step of that run was correct, given the logged context of each step.
This is step-conditional replay - a wrong click in the live run did not change what the next step saw.
It is stricter than the live PASS: a run where the model clicked wrong and then recovered counts as PASS live
and as FAIL here. Expect replay run-PASS <= table PASS by the number of such recoveries (e.g. Qwen2.5-0.5B 5/10 vs 6/10).
"""
import json, re, sys, argparse, glob, time
import requests

SITE_BOOKS = "https://books.toscrape.com/"
SITE_WIKI = "https://en.wikipedia.org/wiki/Samsung_Galaxy_Note_series"
BOOK = "It's Only the Himalayas"

def kind_of(path):
    n = path.split("/")[-1]
    if n.startswith("toscrape_task"): return "agent"
    if n.startswith("wiki_note8"): return "wiki"
    if n.startswith("book2"): return "book2"
    return None

# ---- prompt reconstruction: identical text to agent.py / wiki.py / book2.py ----
def prompt_agent(rec):
    nxt = rec.get("next"); opts = rec.get("candidates") or []; facts = rec.get("facts")
    if nxt == 0:
        return ("MISSION step 0: go to " + SITE_BOOKS + ". "
                'Return only {"action":"navigate","target":"' + SITE_BOOKS + '"}')
    if nxt == 3:
        return ("FACTS read from the product page: book=" + json.dumps(BOOK) + ", price=" + json.dumps(facts["price"]) +
                ", rating=" + json.dumps(facts["rating"]) + ", stock=" + json.dumps(facts["stock"]) + ". "
                "Copy these facts into the report. "
                'Return only {"action":"report","book":"...","price":"...","rating":"...","stock":"..."}')
    target = {1: "Travel", 2: BOOK}[nxt]
    return ("YOUR TASK NOW: click the link whose text is exactly " + json.dumps(target) + ". "
            'Return only {"action":"click","target":"ID"} with the id of that candidate. '
            "CANDIDATES=" + json.dumps(opts, ensure_ascii=False) + " "
            "TASK AGAIN: click the link whose text is exactly " + json.dumps(target) + ".")

def prompt_wiki(rec):
    nxt = rec.get("next"); opts = rec.get("candidates") or []; facts = rec.get("facts"); before = rec.get("before", {})
    if nxt == 0:
        return ("You are on " + before.get("url", "") + ". MISSION step 0: go to " + SITE_WIKI + ". "
                'Return only {"action":"navigate","target":"' + SITE_WIKI + '"}')
    if nxt == 2:
        return ("FACTS read from the Wikipedia infobox: device=" + json.dumps("Note 8") +
                ", first_released=" + json.dumps(facts["first_released"]) + ". "
                "Copy these facts into the report. "
                'Return only {"action":"report","device":"...","first_released":"..."}')
    task = "click the link whose text is exactly " + json.dumps("Note 8") + " and nothing more"
    return ("You are on Wikipedia: " + before.get("title", "") + ". YOUR TASK NOW: " + task + ". "
            "Pick the one candidate that does exactly this task. "
            'Return only {"action":"click","target":"ID"} with an id from CANDIDATES. '
            "CANDIDATES=" + json.dumps(opts, ensure_ascii=False) + " TASK AGAIN: " + task + ".")

def prompt_book2(rec):
    nxt = rec.get("next"); opts = rec.get("candidates") or []; facts = rec.get("facts"); before = rec.get("before", {})
    if nxt == 0:
        return ("You are on " + before.get("url", "") + ". MISSION step 0: go to " + SITE_BOOKS + ". "
                'Return only {"action":"navigate","target":"' + SITE_BOOKS + '"}')
    if nxt == 2:
        return ("FACTS read from the product page: title=" + json.dumps(facts["title"]) + ", price=" + json.dumps(facts["price"]) +
                ", rating=" + json.dumps(facts["rating"]) + ", stock=" + json.dumps(facts["stock"]) + ", upc=" + json.dumps(facts["upc"]) + ". "
                "Copy these facts into the report exactly. "
                'Return only {"action":"report","title":"...","price":"...","rating":"...","stock":"...","upc":"..."}')
    task = "find the book " + json.dumps(BOOK) + " and click the link whose text is exactly its title"
    return ("You are on books.toscrape.com: " + before.get("title", "")[:60] + ". YOUR TASK NOW: " + task + ". "
            "If the book is not in CANDIDATES, click a category or page link that could lead to it. "
            'Return only {"action":"click","target":"ID"} with an id from CANDIDATES. '
            "CANDIDATES=" + json.dumps(opts, ensure_ascii=False) + " TASK AGAIN: " + task + ".")

PROMPTS = {"agent": prompt_agent, "wiki": prompt_wiki, "book2": prompt_book2}
REPORT_STEP = {"agent": 3, "wiki": 2, "book2": 2}
SITE_OF = {"agent": SITE_BOOKS, "wiki": SITE_WIKI, "book2": SITE_BOOKS}
CLICK_TARGET = {"agent": {1: "Travel", 2: BOOK}, "wiki": {1: "Note 8"}, "book2": {1: BOOK}}
WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5"}
INFRA = re.compile(r"ConnectionError|NameResolutionError|ReadTimeout|ConnectTimeout|HTTPError|RemoteDisconnected|MCP unreachable|Network is unreachable", re.I)

def expected_click(kind, rec):
    target = CLICK_TARGET[kind].get(rec.get("next"))
    if not target: return None
    t = target.lower()
    cands = rec.get("candidates") or []
    exact = [o["id"] for o in cands if (o.get("text") or "").strip().lower() == t]
    if exact and kind != "wiki": return set(exact)
    # whole-phrase match: target present and not continued by "." or a digit ("Note 8" ok, "Note 8.0" not)
    ok = set()
    for o in cands:
        txt = (o.get("text") or "").lower()
        for m in re.finditer(re.escape(t), txt):
            nxt = txt[m.end():m.end() + 1]
            if not (nxt == "." or nxt.isdigit()): ok.add(o["id"]); break
    return ok or None

def norm(k, v):
    v = str(v).strip()
    return WORDS.get(v.lower(), v) if k == "rating" else v

def parse(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"```[a-zA-Z]*", "", text).replace("```", "")
    m = re.search(r"{.*}", text, re.S)
    if not m: return None
    blob = m.group(0)
    for fixer in (lambda s: s, lambda s: re.sub(r"\bNone\b", "null", re.sub(r"\bFalse\b", "false", re.sub(r"\bTrue\b", "true", s)))):
        try: return json.loads(fixer(blob))
        except Exception: pass
    return None

def ask(url, prompt, think, max_tokens):
    body = {"model": "local", "messages": [
        {"role": "system", "content": "Return exactly one JSON object. No Markdown."},
        {"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": max_tokens}
    if not think: body["chat_template_kwargs"] = {"enable_thinking": False}
    r = requests.post(url, json=body, timeout=600); r.raise_for_status()
    y = r.json(); return y["choices"][0]["message"]["content"].strip(), y.get("usage", {})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--url", default="http://127.0.0.1:8080/v1/chat/completions")
    ap.add_argument("--limit", type=int, default=0, help="max steps per file (0 = all)")
    ap.add_argument("--think", action="store_true", help="do not disable thinking mode")
    ap.add_argument("--last", type=int, default=10, help="replay only the last N runs of each file, as the table does (0 = all)")
    ap.add_argument("--strict-errors", action="store_true", help="count runs with infrastructure errors (network, relay) as failed instead of excluding them")
    a = ap.parse_args()
    files = [f for pat in a.logs for f in sorted(glob.glob(pat))]
    grand = {"steps": 0, "ok": 0}
    for path in files:
        kind = kind_of(path)
        if not kind: print("skip (unknown log type):", path); continue
        stats = {"navigate": [0, 0], "click": [0, 0], "report": [0, 0]}; skipped_open = 0
        n = 0; toks = 0; t0 = time.time()
        # 1) split the file into runs (a new run starts at step 1)
        groups, g = [], []
        for line in open(path, encoding="utf-8"):
            try: rec = json.loads(line)
            except Exception: continue
            if rec.get("step") == 1 and g: groups.append(g); g = []
            g.append(rec)
        if g: groups.append(g)
        # 2) classify every run BEFORE slicing the window and before replaying anything
        classified = []
        for gi, grp in enumerate(groups, 1):
            verdict, why = "valid", ""
            for rec in grp:
                if rec.get("status") in ("error", "invalid"):
                    err = str(rec.get("error", "")).strip()
                    if not err:
                        verdict, why = "failed", "unclassified (empty error field)"
                    elif INFRA.search(err) and not a.strict_errors:
                        verdict, why = "excluded", "infra: " + err[:80]
                    else:
                        verdict, why = "failed", "invalid decision: " + err[:80]
                    break
            classified.append((gi, grp, verdict, why))
        excluded_runs = [c for c in classified if c[2] == "excluded"]
        window = [c for c in classified if c[2] != "excluded"]
        if a.last: window = window[-a.last:]
        for gi, grp, verdict, why in excluded_runs:
            print("  run {} excluded: {}".format(gi, why))
        for gi, grp, verdict, why in window:
            if verdict == "failed": print("  run {} failed: {}".format(gi, why))
        excluded = len(excluded_runs)
        # 3) replay only the steps of runs in the window
        runs = []          # list of dicts: {"ok": bool, "report": bool, "steps": int}
        cur = None
        for gi, grp, verdict, why in window:
            cur = {"ok": verdict == "valid", "report": False, "steps": 0, "id": gi}; runs.append(cur)
            for rec in grp:
                if rec.get("status") not in ("ok", "report", "done") or rec.get("next") is None: continue
                if rec.get("next") not in (0, REPORT_STEP[kind]) and not rec.get("candidates"): continue
                if rec.get("next") == REPORT_STEP[kind] and not rec.get("facts"): continue
                if a.limit and n >= a.limit: break
                prompt = PROMPTS[kind](rec)
                nxt = rec["next"]
                if nxt not in (0, REPORT_STEP[kind]) and expected_click(kind, rec) is None:
                    skipped_open += 1; continue        # open step: harness allowed several answers, no single expected id
                n += 1
                try: raw, usage = ask(a.url, prompt, a.think, 120)
                except Exception as e: print("  request failed:", e); cur["ok"] = False; continue
                toks += usage.get("prompt_tokens", 0)
                d = parse(raw) or {}
                if nxt == 0:
                    key = "navigate"; ok = d.get("action") == "navigate" and str(d.get("target", "")).rstrip("/") == SITE_OF[kind].rstrip("/")
                elif nxt == REPORT_STEP[kind]:
                    key = "report"; facts = rec["facts"]; cur["report"] = True
                    fields = [k for k in facts if k not in ("raw",)]
                    ok = d.get("action") == "report" and all(norm(k, d.get(k, "")) == norm(k, facts.get(k, "")) for k in fields if facts.get(k) is not None)
                else:
                    key = "click"; exp = expected_click(kind, rec)
                    ok = d.get("action") == "click" and d.get("target") in exp
                stats[key][1] += 1; stats[key][0] += int(bool(ok)); cur["steps"] += 1
                if not ok: cur["ok"] = False
                print(("  OK  " if ok else "  MISS") + " " + key.ljust(8), "step", rec.get("step"), "|", (raw.replace(chr(10), " ")[:100]))
        tot_ok = sum(v[0] for v in stats.values()); tot = sum(v[1] for v in stats.values())
        grand["steps"] += tot; grand["ok"] += tot_ok
        counted = [r for r in runs if r["steps"] > 0 or not r["ok"]]
        run_pass = sum(1 for r in counted if r["ok"] and r["report"])
        grand.setdefault("runs", 0); grand.setdefault("runs_ok", 0)
        grand["runs"] += len(counted); grand["runs_ok"] += run_pass
        print(path)
        print("  steps: navigate {}/{} | click {}/{} | report {}/{} | total {}/{}".format(
            stats["navigate"][0], stats["navigate"][1], stats["click"][0], stats["click"][1],
            stats["report"][0], stats["report"][1], tot_ok, tot))
        print("  runs : {}/{} PASS (all replayed steps correct incl. report; open steps skipped: {}; runs excluded for infra errors: {})".format(run_pass, len(counted), skipped_open, excluded))
        print("  prompt tokens {} | {:.0f}s".format(toks, time.time() - t0))
    if len(files) > 1:
        print("ALL: steps", grand["ok"], "/", grand["steps"], "| runs", grand.get("runs_ok", 0), "/", grand.get("runs", 0))

if __name__ == "__main__":
    main()
