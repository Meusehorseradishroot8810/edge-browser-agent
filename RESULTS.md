# RESULTS

Date: 2026-09-07. Phone: Samsung Galaxy Note 8 (SM-N950F), Android 9, 6 GB (5.2 GB usable). Inference: llama.cpp commit e107984, Q4_K_M unless noted, `-c 4096 -t 4`. Eyes: E2LLM extension 1.5.36 via mcp.e2llm.com. Browser: desktop Chrome, viewport 1920x945 (tasks 1-3, first series) / 1536x730 (laptop, later series). Runs per row: last 10 in the log file. Prompt: identical for all models.

## Task 1 - books.toscrape.com, 3 facts (`agent.py`)

Route: foreign site → home → Travel → "It's Only the Himalayas" → report {price, rating, stock}. Expected: £45.17 / Two / In stock.

| Model | Params | Quant | File size | Log | PASS | Failure pattern |
|---|---|---|---|---|---|---|
| Qwen3-0.6B | 0.6B | Q4_K_M | 397 MB | toscrape_task_qwen3_06.jsonl | 10/10 | - |
| Qwen2.5-0.5B-Instruct | 0.5B | Q4_K_M | 491 MB | toscrape_task_qwen05.jsonl | 6/10 | wrong id at category step, then `"ID"` placeholder |
| Qwen2.5-1.5B-Instruct | 1.5B | Q4_K_M | 986 MB | toscrape_task.jsonl | 10/10 | - |
| GLM-Edge-1.5B-Chat | 1.5B | Q4_K_M | 980 MB | toscrape_task_glm.jsonl | 10/10 | rating as digit ("2"); accepted |
| Gemma-2-2B-it | 2.6B | Q4_K_M | 1,709 MB | toscrape_task_gemma2.jsonl | 10/10 | - |
| MiniCPM5-2B | 2B | Q4_K_M | 1,561 MB | toscrape_task_minicpm5.jsonl | 9/10 | "£45.17" → "$45.17" (run 1) |
| Qwen3.5-0.8B (unsloth GGUF) | 0.8B | Q4_K_M | 533 MB | toscrape_task_qwen35_08.jsonl | 6/10 | navigation 10/10; "45.17" without "£" in 4 reports (8 Sep; an earlier 6-run series in the same file was cut by a network drop) |
| Llama-3.2-3B-Instruct | 3B | Q4_K_M | 2,019 MB | toscrape_task_llama3b.jsonl | 10/10 | - |
| Ministral-3-3B-Instruct-2512 (official GGUF) | 3B | Q4_K_M | 2,147 MB | toscrape_task_ministral3.jsonl | 10/10 | Firefox; JSON in code fences; battery 31.0 → 41.6 °C, 39 → 15% over 10 runs (9 Sep) |
| Llama-3.2-1B-Instruct | 1B | Q4_K_M | 808 MB | toscrape_task_llama1b.jsonl | 0/10 | pseudo-code `candidate['id']`; one run echoed the candidate list |
| Gemma-3-1B-it | 1B | Q4_K_M | 806 MB | toscrape_task_gemma.jsonl | 0/10 | `"ID"` placeholder |
| Gemma-3-270M-it | 0.27B | Q8_0 | 292 MB | toscrape_task_gemma270.jsonl | 0/10 | `"ID"` placeholder |
| LFM2-350M | 0.35B | Q4_K_M | 229 MB | toscrape_task_lfm2.jsonl | 0/10 | valid JSON, valid ids, random link choice |
| LFM2.5-1.2B-Instruct | 1.2B | Q4_K_M | ~750 MB | toscrape_task_lfm25.jsonl | 0/10 | `"ID"` placeholder |

Per-decision prompt size, passing models: 165-235 tokens (from llama.cpp `prompt_tokens`). Task time, Qwen2.5-1.5B: ~80 s (10 runs, spread within seconds). Node ids differ between runs (e.g. a055 / a056 for the same book).

Thinking mode: disabled for Qwen3 via `chat_template_kwargs: {"enable_thinking": false}` (5 earlier runs with thinking enabled returned empty content; excluded, present in the log).

## Task 2 - Wikipedia, live site (`wiki.py`)

Route: investing.com → Samsung Galaxy Note series → link "Note 8" → report first_released from infobox. Expected: "15 September 2017". Decoys in candidate list: "Note 8.0", "Samsung Galaxy Note 8.0", "Galaxy Note 8.0", "Note FE". Interactive nodes on series page: ~760.

| Model | Log | PASS | Note |
|---|---|---|---|
| Qwen3-0.6B | wiki_note8.jsonl | 10/10 | chose "Note 8" (id a0253) in all 10 |
| GLM-Edge-1.5B | wiki_note8_glm.jsonl | 9/10 | run 8: operator switched the active tab; run 7: detour via "Samsung Galaxy S10" → "N950x (Galaxy Note 8)", still PASS |

## Task 3 - five fields incl. UPC (`book2.py`)

Route: foreign site → home → "It's Only the Himalayas" (no category hint) → report {title, price, rating, stock, upc}. Expected UPC: a22124811bfa8350.

| Model | Log | PASS |
|---|---|---|
| Qwen3-0.6B | book2_upc.jsonl | 10/10 |

## Task 4 - GitHub, live site, Firefox (`github.py`)

Route: unrelated site → github.com/e2llm → click "edge-browser-agent" by name → eyes read the star count from the repo header → click "logs" by name → eyes count files by `/blob/main/logs/` links → report {repo, stars, log_files}. Ground truth: GitHub API (`stargazers_count`, `contents/logs`) fetched at report time. Browser: Firefox (E2LLM extension 1.5.35), Chrome closed.

| Model | Log | PASS | Battery temp over 10 runs | Note |
|---|---|---|---|---|
| Qwen3-0.6B | github_stars_ff.jsonl | 10/10 | 28.7 → 32.7 °C, 57 → 52%, unplugged | 2 stars, 20 log files in every report; API agreed every time |

Thermal reference (task 1, Qwen3-0.6B, 3 back-to-back runs, unplugged, idle 10 min before): 31.2 / 31.5 / 31.5 °C, wall-clock 53 / 54 / 54 s, all PASS. Run 1 without prompt cache.

## Control - raw HTML instead of the perception layer (`control.py`, `control_wiki.py`)

Qwen3-0.6B, `-c 16384`, server restarted before each run (no prompt cache). Input: raw HTML of the current page (scripts/styles stripped, truncated to CTX_CHARS), model returns an href; on the final page it extracts the facts from HTML.

Sandbox (books.toscrape.com, task 1). Expected: £45.17 / Two / In stock.

| Run | Date | HTML chars | Prompt tokens (nav step) | Seconds (nav step) | Returned href | Report | Outcome |
|---|---|---|---|---|---|---|---|
| 1 | 09-07 | 24,831 | 8,507 | 1,099 | `/it-s-only-the-himalayas.html` (does not exist) | - | FAIL (404 → placeholder) |
| 2 | 09-07 | 24,831 | 8,507 | 44 (prompt cache from run 1) | correct | correct; harness encoding bug on "£" | not counted |
| 3 | 09-08 | 24,831 | 8,487 | 1,067 | correct | correct | PASS, 12,245 tokens, 1,360 s total |
| 4 | 09-08 | 24,831 | 8,487 | 999 | correct | correct | PASS, 12,242 tokens, 1,383 s total |
| 5 | 09-08 | 24,831 | 8,487 | 1,095 | correct | correct | PASS, 12,242 tokens, 1,335 s total |

Counted: 4 of 5 correct routes; 3/3 full PASS on 09-08. Reference with the layer: ~500 prompt tokens and ~80 s per task, 10/10.

Wikipedia (task 2). Page: Samsung Galaxy Note series. Expected link: "Note 8" → /wiki/Samsung_Galaxy_Note_8.

| Run | HTML chars (full) | Chars sent | Prompt tokens | Seconds | Returned | Outcome |
|---|---|---|---|---|---|---|
| 0 | 466,744 | 60,000 | - | - | HTTP 400 from llama-server (prompt exceeds 16k context) | not counted |
| 1 | 466,744 | 40,000 (8.6%) | 12,341 | 2,616 | `/wiki/Samsung_Galaxy_Note` (current page), no `action` field | FAIL |
| 2 | 466,744 | 40,000 | 12,341 | 2,336 | same | FAIL |
| 3 | 466,744 | 40,000 | 12,341 | 2,113 | same | FAIL |

0/3. Reference with the layer: ~200 prompt tokens and 15-20 s for the same decision, "Note 8" chosen 10/10.

## Environment

`ENV.json`, `MODELS.sha256`. Network on the phone dropped several times during the day (`ConnectionError`, `NameResolutionError` in logs); affected runs are not counted.

## Recount

```
python - <<'PY'
import json, glob, os
for path in sorted(glob.glob("logs/*.jsonl")):
    runs, cur = [], []
    for line in open(path, encoding="utf-8"):
        try: r = json.loads(line)
        except Exception: continue
        if r.get("step") == 1 and cur: runs.append(cur); cur = []
        cur.append(r)
    if cur: runs.append(cur)
    last = runs[-10:]
    ok = sum(1 for x in last if x[-1].get("verdict") is True or (x[-1].get("status") == "done" and x[-1].get("verified")))
    print(os.path.basename(path).ljust(34), "runs", len(runs), "| last 10 PASS", ok)
PY
```
