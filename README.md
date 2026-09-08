# Qwen3-0.6B running on a 2017 Galaxy Note 8 drives a real desktop Chrome session

**Setup:** local Qwen3-0.6B on a Samsung Galaxy Note 8, E2LLM structured browser perception, a laptop with a live Chrome session (not headless).

**What was run:** a harness in which 0.6-3B language models, running in llama.cpp on a Samsung Galaxy Note 8 (2017, Android 9, 6 GB), complete verifiable tasks in desktop Chrome on another machine. The page is handed to the model neither as HTML nor as a screenshot, but as structure: a short list of named links and fields. The model only chooses among the presented elements and formats the final report. Perception, candidate reduction, browser execution, page reading and verification are handled by the surrounding stack.

**Result:** 7 of 12 models completed the task at least once; 5 of 12 scored 10/10. The smallest 10/10 model was Qwen3-0.6B (397 MB). The same model given raw HTML instead of the layer needs 25× the tokens and 17× the time on a small page, and does not complete the task on a real one.

This is a harness measurement on three fixed tasks, not a benchmark. Series date: 7 September 2026. All runs are in `logs/` untouched.

## Table

One task (`agent.py`): from an unrelated site, go to books.toscrape.com, open the Travel category, open the book "It's Only the Himalayas", return price / star rating as a word / stock status. Verification: the report is checked against a fixed expected value. 10 runs per model, identical prompt for all.

| Model | Size | Year | Result | Note |
|---|---|---|---|---|
| Qwen3-0.6B | 0.6B | 2025 | **10/10** | copies facts verbatim |
| Qwen2.5-0.5B | 0.5B | 2024 | 6/10 | failures: wrong id, then placeholder |
| Qwen2.5-1.5B | 1.5B | 2024 | 10/10 | |
| GLM-Edge-1.5B | 1.5B | 2024 | 10/10 | writes the rating as a digit ("2" for "Two") |
| Gemma-2-2B | 2.6B | 2024 | 10/10 | |
| MiniCPM5-2B | 2B | 2026 | 9/10 | replaced "£" with "$" once |
| Llama-3.2-3B | 3B | 2024 | 10/10 | |
| Llama-3.2-1B | 1B | 2024 | 0/10 | writes pseudo-code `candidate['id']` instead of JSON |
| Gemma-3-1B | 1B | 2025 | 0/10 | copies the `"ID"` placeholder from the template |
| Gemma-3-270M | 0.27B | 2025 | 0/10 | same |
| LFM2-350M | 0.35B | 2025 | 0/10 | keeps the format, picks links at random |
| LFM2.5-1.2B | 1.2B | 2026 | 0/10 | copies the placeholder |

Full table with timings and token counts: `RESULTS.md`.

Two additional tasks on Qwen3-0.6B:

- **Live site** (`wiki.py`): from investing.com go to Wikipedia, on the Galaxy Note series page pick the link "Note 8" among "Note 8.0", "Samsung Galaxy Note 8.0", "Galaxy Note 8.0", "Note FE" (a page with ~760 interactive nodes), return the release date from the infobox - **10/10**. GLM-Edge-1.5B on the same task: 9/10 (the tenth run was disrupted by the operator switching the active tab).
- **Five fields** (`book2.py`): from the home page, find the book with no category hint, return title / price / rating / stock / UPC from the Product Information table - **10/10**.

## Control: the same model without the perception layer

`control.py` / `control_wiki.py`: Qwen3-0.6B, same sites, same hands (`act`), same verification. Instead of ten candidates, the model receives the raw HTML of the current page (scripts and styles stripped) and has to return an href itself; on the final page it extracts the facts from the HTML. Server restarted between runs so no prompt cache carries over. Context: 16,384 tokens - the most this phone runs.

| | sandbox, with the layer | sandbox, raw HTML | Wikipedia, with the layer | Wikipedia, raw HTML |
|---|---|---|---|---|
| page size | - | 24,831 chars | - | 466,744 chars, 40,000 sent (9%) |
| prompt tokens per task | ~500 | ~12,240 | ~500 | 12,341 (one step) |
| time per task on the Note 8 | ~80 s | 22-23 min | ~90 s | 35-44 min |
| result | 10/10 | 4/5 correct route (one invented href) | 10/10 | 0/3 - returned the current page's own URL every time |

What the control shows: on a small page the model can do it without the layer - 25× more tokens, 17× slower, and not every time. On a real page the raw HTML does not fit the context a phone can run, and the model does not find the link in the part that fits. The layer is what makes the task cheap and reliable on the small page, and possible at all on the large one.

## Who does what

**Eyes** (E2LLM: Chrome extension + relay, MCP):
- the page is captured as structure; `query` returns every interactive node with its text and href;
- the harness keeps at most 10 candidates: exact matches to the target first, the rest as an even sample across the site's sections, links to the current page excluded;
- facts are read from the product page and the infobox (`read_page`); the star rating comes from a CSS class that does not exist in the page text.

**Brain** (the model):
- step 0: `navigate` to a given URL;
- steps 1-2: `{"action":"click","target":"<id>"}` - a choice from the list, by name;
- last step: `{"action":"report", ...}` - copying the facts it was given.

The model never sees HTML, screenshots, or the candidates' URLs. This is deliberate: what is measured is what perception contributes, not what the model can do. Measuring perception was the point.

## Limits

- The tasks are name matching and copying. Where judgement about the page is needed, 1.5B breaks: in an earlier series Qwen2.5-1.5B could not pick "next" among topical decoys (`toscrape_autonav.jsonl`).
- In tasks 1 and 3 the book sits on the first catalogue page; pagination was not tested.
- Three failure modes worth knowing before putting a small model into a loop: cannot hold the format (Llama-3.2-1B); copies the placeholder from the template (Gemma 3 at both sizes, LFM2.5, partly Qwen2.5-0.5B); picks at random while keeping a valid format (LFM2-350M). The line does not run along size: a 0.6B model from 2025 passes where 1B models from two vendors do not.
- Copying is not always verbatim: GLM-Edge normalises a word into a digit, MiniCPM5 once swapped the currency. Verification treats "Two" and "2" as equal; a currency swap is not accepted.
- The relay is hosted by the authors; reproducing the runs requires an e2llm account. The phone's network dropped several times during the day - visible in the logs as `ConnectionError`; those runs are not counted in the table.

## Prior work

The thesis "observation space matters more than brain size" is not ours:

- **AgentOccam** (2024) showed it for the GPT-4 class on WebArena: simplifying observations and actions gave +161% with no fine-tuning.
- **WebLINX** (2024) and **MindAct** showed that small models work with a compact page representation - after fine-tuning.

Here the same hypothesis is tested at the extreme: no fine-tuning, below 1B, on a 2017 phone, with open logs and a no-layer control. We found no published zero-shot results for sub-1B models on standard web benchmarks; a comparable number can only come from running a third-party benchmark (the closest in nature is MiniWoB++), and that is the next series.

## How to reproduce

Phone (Termux):
```
pkg install python git
# llama.cpp built from source, commit e107984 (see ENV.json)
./llama.cpp/build/bin/llama-server -m models/qwen3-0.6b-Q4_K_M.gguf -c 4096 -t 4 --port 8080 --jinja --log-disable &
```

Browser: E2LLM extension in Chrome (1.5.36); connection and `token.json` via https://e2llm.com/start.

Runs:
```
python hdr.py                                 # header: model / device / browser
./run_model.sh <gguf> "<label>" <log-name>    # 10 runs of task 1
python wiki.py                                # live site
python book2.py                               # five fields
python control.py                             # no-layer control (server with -c 16384)
```

Model hashes: `MODELS.sha256`; environment: `ENV.json`; video of a single run (1:13, one continuous take): https://youtu.be/-7OC7sge4bA

### Replay without a browser or an account

`replay.py` re-runs only the model side, offline: it takes the candidate lists and facts recorded in `logs/`, rebuilds the exact prompts the harness used, sends them to any OpenAI-compatible local server and scores the decisions against the task. No E2LLM, no relay, no browser.

```
python replay.py logs/wiki_note8.jsonl                       # llama.cpp on :8080 by default
python replay.py logs/*.jsonl --url http://127.0.0.1:11434/v1/chat/completions   # e.g. Ollama
```

Limit: steps where a model produced an invalid decision (a placeholder, pseudo-code) were logged as errors without their candidate list, so they cannot be replayed; every step with a valid decision, including wrong clicks, can. Replay reports both step accuracy and run-level PASS (last 10 runs per file, as the table). Run-level PASS in replay is stricter than the live one: a run where the model clicked wrong and then recovered is a PASS live and a FAIL in replay, so expect replay ≤ table by the number of such recoveries (Qwen2.5-0.5B: 5/10 vs 6/10).

## Logs

`logs/` contains every run of 7-8 September, including early ones with harness bugs (wrong link filter, infobox reading, a partially downloaded GGUF). Two files are interrupted series from before the model table and are not part of any result above: `e2llm_onboarding_5steps.jsonl` (first attempts on 5-6 September, mobile Firefox, onboarding page) and `cookie_banners.jsonl` (an abandoned cookie-banner experiment, 7 September). The table counts the last 10 runs per file; the summary can be recomputed with the script in `RESULTS.md`. Nothing was cut.

`MODELS.sha256`: six hashes computed on the phone after the runs; six for models deleted to free space are taken from Hugging Face LFS metadata for the same download URLs.

## License

MIT for the harness. Models under their authors' licences. E2LLM is a separate product, used here as the perception layer.
