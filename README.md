# Sub-3B local models drive a real desktop browser from three Android phones

**Setup:** a local model in llama.cpp on an Android phone, E2LLM structured
browser perception, a laptop with a live browser session (not headless).

**What was run:** a harness in which 0.1-3B language models, running on
phones from 2017, 2021 and 2022, complete verifiable tasks in a desktop
browser on another machine. The page is handed to the model neither as HTML
nor as a screenshot, but as structure: a short list of named links and
fields. The model only chooses among the presented elements and formats the
final report. Perception, candidate reduction, browser execution, page
reading and verification are handled by the surrounding stack.

**Two series:**

- **7 September 2026, Galaxy Note 8, Chrome, 12 models.** 7 of 12 completed
  the task at least once, 5 of 12 scored 10/10. The smallest 10/10 model was
  Qwen3-0.6B (397 MB). The same model given raw HTML instead of the layer
  needs 25 times the tokens and 17 times the time on a small page, and does
  not complete the task on a real one.
- **9-10 September 2026, three phones, Firefox, 15 models, two tasks.** Same
  kit copied to each device, same llama.cpp commit, same GGUF files. Full
  numbers in [HARDWARE.md](HARDWARE.md).

These are harness measurements on fixed tasks, not a benchmark. All runs are
in `logs/` untouched.

## The three devices

| Device | Year | SoC | RAM usable | Android |
|---|---|---|---|---|
| Galaxy Note 8 (SM-N950F) | 2017 | Exynos 8895 | 5.2 GB | 9 |
| Galaxy S21 (SM-G991B) | 2021 | Exynos 2100 | 7.0 GB | 14, then 15 |
| Galaxy A04e (SM-A042F) | 2022 | MediaTek Helio P35 | 2.7 GB | 14 |

The A04e costs about 100 dollars, has a MediaTek chip rather than an Exynos,
and is slower than the 2017 flagship. Qwen3-0.6B scores 10/10 on all three
devices on both tasks. What changes across devices is the clock, not the
result: 25, 29 and 62 seconds per task.

## Table

One task (`agent.py`): from an unrelated site, go to books.toscrape.com, open
the Travel category, open the book "It's Only the Himalayas", return price /
star rating as a word / stock status. Verification: the report is checked
against a fixed expected value. Pass rate over the last 10 runs per file,
identical prompt for all models.

| Model | Size | Year | Note 8 | S21 | A04e | Note |
|---|---|---|---|---|---|---|
| Qwen3-0.6B | 0.6B | 2025 | **10/10** | **10/10** | **10/10** | copies facts verbatim |
| Qwen3.5-0.8B | 0.8B | 2026 | 7/10 | 39/40 | | drops the currency sign on the Note 8 |
| Qwen2.5-0.5B | 0.5B | 2024 | 6/10 | 5/10 | | wrong id, then placeholder |
| Qwen2.5-1.5B | 1.5B | 2024 | 10/10 | 10/10 | | |
| GLM-Edge-1.5B | 1.5B | 2024 | 10/10 | 4/10 | | see "pass rate is not portable" |
| Gemma-2-2B | 2.6B | 2024 | 10/10 | | | |
| MiniCPM5-2B | 2B | 2026 | 9/10 | 5/10 | | swaps "£" for "$" |
| Llama-3.2-3B | 3B | 2024 | 10/10 | 10/10 | | |
| Ministral 3 3B | 3B | 2026 | 10/10 | 10/10 | | |
| Llama-3.2-1B | 1B | 2024 | 0/10 | | | pseudo-code `candidate['id']` instead of JSON |
| Gemma-3-1B | 1B | 2025 | 0/8 | | | copies the `"ID"` placeholder from the template |
| Gemma-3-270M | 0.27B | 2025 | 0/10 | | | same |
| LFM2-350M | 0.35B | 2025 | 0/10 | | | keeps the format, picks links at random |
| LFM2.5-1.2B | 1.2B | 2026 | 0/10 | 0/10 | | copies the placeholder |
| SmolLM2-135M | 0.135B | 2024 | 0/10 | 0/30 | | echoes the mission text back |

Full table with timings, token counts and per-device medians: `RESULTS.md`
and [HARDWARE.md](HARDWARE.md).

Additional tasks:

- **Live site** (`wiki.py`): from another site go to Wikipedia, on the Galaxy
  Note series page pick the link "Note 8" among "Note 8.0", "Samsung Galaxy
  Note 8.0", "Galaxy Note 8.0", "Note FE" (a page with about 760 interactive
  nodes), return the release date from the infobox. Qwen3-0.6B: 10/10 on all
  three phones, 30 runs total. Ten more models on the S21 in
  [HARDWARE.md](HARDWARE.md), including Qwen2.5-1.5B at 1/10, which keeps
  clicking the 2013 tablet.
- **Five fields** (`book2.py`): from the home page, find the book with no
  category hint, return title / price / rating / stock / UPC from the Product
  Information table. Qwen3-0.6B: 10/10.
- **GitHub stars** (`github.py`): read star and fork counts from a repository
  page, checked against the GitHub API. Qwen3-0.6B on Firefox: 10/10.

## Pass rate is not portable across SoCs

The clearest result of the second series, and the one we did not expect.
Three models move in different directions between the Note 8 and the S21 on
the same task:

| Model | Note 8 | S21 | What goes wrong |
|---|---|---|---|
| Qwen3.5-0.8B | 7/10 | 39/40 | drops the pound sign, reports 45.17 |
| MiniCPM5-2B | 1 bad report in 10 | 5 bad reports in 10 | swaps the pound sign for a dollar sign |
| GLM-Edge-1.5B | 10/10 | 4/10 | emits the literal placeholder ID as the target |

Same GGUF files by md5, same llama.cpp commit e107984, same prompt, same
server flags, same candidate lists from the layer. We do not have a proven
cause. The plausible one is that ggml selects different NEON kernels for the
two CPUs, logits differ slightly, and a token sitting near the decision
boundary falls differently. What we can state without a cause: a pass rate
measured on one phone does not transfer to another phone, and a result
reported without naming the SoC is incomplete.

The layer is the constant here. Same capture, same candidate ids, same
verification on every device. That is what makes the model differences
measurable at all.

## Control: the same model without the perception layer

`control.py` / `control_wiki.py`: Qwen3-0.6B, same sites, same hands (`act`),
same verification. Instead of ten candidates, the model receives the raw HTML
of the current page (scripts and styles stripped) and has to return an href
itself; on the final page it extracts the facts from the HTML. Server
restarted between runs so no prompt cache carries over. Context: 16,384
tokens, the most this phone runs.

|  | sandbox, with the layer | sandbox, raw HTML | Wikipedia, with the layer | Wikipedia, raw HTML |
|---|---|---|---|---|
| page size | - | 24,831 chars | - | 466,744 chars, 40,000 sent (9%) |
| prompt tokens per task | about 500 | about 12,240 | about 500 | 12,341 (one step) |
| time per task on the Note 8 | about 80 s | 22-23 min | about 90 s | 35-44 min |
| result | 10/10 | 4/5 correct route (one invented href) | 10/10 | 0/3, returned the current page's own URL every time |

What the control shows: on a small page the model can do it without the layer
at 25 times the tokens and 17 times the time, and not every time. On a real
page the raw HTML does not fit the context a phone can run, and the model
does not find the link in the part that fits.

## Who does what

**Eyes** (E2LLM: browser extension + relay, MCP):

- the page is captured as structure; `query` returns every interactive node
  with its text and href;
- the harness keeps at most 10 candidates: exact matches to the target first,
  the rest as an even sample across the site's sections, links to the current
  page excluded;
- facts are read from the product page and the infobox (`read_page`); the
  star rating comes from a CSS class that does not exist in the page text.

**Brain** (the model):

- step 0: `navigate` to a given URL;
- steps 1-2: `{"action":"click","target":"<id>"}`, a choice from the list, by
  name;
- last step: `{"action":"report", ...}`, copying the facts it was given.

The model never sees HTML, screenshots, or the candidates' URLs. This is
deliberate: what is measured is what perception contributes, not what the
model can do.

## Limits

- The tasks are name matching and copying. Where judgement about the page is
  needed, 1.5B breaks: Qwen2.5-1.5B could not pick "next" among topical
  decoys (`toscrape_autonav.jsonl`), and on Wikipedia it picks the Note 8.0
  tablet 8 times out of 10 while passing task 1 at 10/10.
- **Pass rates are per device.** See the section above. Any number in these
  tables is a number for one model on one SoC.
- In tasks 1 and 3 the book sits on the first catalogue page; pagination was
  not tested.
- Failure modes worth knowing before putting a small model into a loop:
  cannot hold the format (Llama-3.2-1B); copies the placeholder from the
  template (Gemma 3 at both sizes, LFM2.5, GLM-Edge on the S21, partly
  Qwen2.5-0.5B); picks at random while keeping a valid format (LFM2-350M);
  echoes the prompt back (SmolLM2-135M). The line does not run along size: a
  0.6B model from 2025 passes where 1B models from two vendors do not, and
  nothing below roughly 0.5B produced an answer in the required shape at all.
- Copying is not always verbatim: GLM-Edge normalises a word into a digit,
  MiniCPM5 swaps the currency. Verification treats "Two" and "2" as equal; a
  currency swap is not accepted.
- The relay is hosted by the authors; reproducing the runs requires an e2llm
  account.

## How to reproduce

Phone (Termux):

```
pkg install python git cmake clang make termux-api
pip install requests
# llama.cpp built from source, commit e107984 (see the ENV json files)
./llama.cpp/build/bin/llama-server -m models/qwen3-0.6b-Q4_K_M.gguf -c 4096 -t 4 --port 8080 --jinja --log-disable &
```

Browser: E2LLM extension in Chrome or Firefox; connection and `token.json`
via <https://e2llm.com/start>. Only one browser should be connected during a
series.

Runs:

```
python hdr.py                                 # header: model / device / browser / battery temperature
./run_model.sh <gguf> "<label>" <log-name>    # 10 runs of task 1, single model
./fleet_run.sh <gguf> [runs]                  # task 1 + Wikipedia, logs named after the device
python wiki.py                                # live site
python book2.py                               # five fields
python github.py                              # GitHub stars, needs E2LLM_BROWSER=Firefox
python control.py                             # no-layer control (server with -c 16384)
```

`fleet_run.sh` writes an `ENV_<device>.json` next to the logs with the model
file md5, the llama.cpp commit, server flags, SoC, RAM and Android version,
and packs the series into a tgz in Downloads.

Model hashes: `MODELS.sha256`; first-series environment: `ENV.json`; video of
a single run (1:13, one continuous take): <https://youtu.be/-7OC7sge4bA>

### Replay without a browser or an account

`replay.py` re-runs only the model side, offline: it takes the candidate
lists and facts recorded in `logs/`, rebuilds the exact prompts the harness
used, sends them to any OpenAI-compatible local server and scores the
decisions against the task. No E2LLM, no relay, no browser.

```
python replay.py logs/wiki_note8.jsonl
python replay.py logs/*.jsonl --url http://127.0.0.1:11434/v1/chat/completions
```

Limit: steps where a model produced an invalid decision (a placeholder,
pseudo-code) were logged as errors without their candidate list, so they
cannot be replayed; every step with a valid decision, including wrong clicks,
can. Run-level PASS in replay is stricter than the live one: a run where the
model clicked wrong and then recovered is a PASS live and a FAIL in replay,
so expect replay to be lower than the table by the number of such recoveries
(Qwen2.5-0.5B: 5/10 against 6/10).

## Logs

`logs/` contains every run of 7-10 September, including early ones with
harness bugs (wrong link filter, infobox reading, a partially downloaded
GGUF). Second-series files are named `<device>_<task>_<model>_<date>.jsonl`.
Two files are interrupted series from before the model table and are not part
of any result above: `e2llm_onboarding_5steps.jsonl` (first attempts on 5-6
September, mobile Firefox, onboarding page) and `cookie_banners.jsonl` (an
abandoned cookie-banner experiment, 7 September). Tables count the last 10
runs per file. Nothing was cut.

During the 10 September runs our own relay went down three times: an unbounded
internal message queue filled memory, found and fixed the same day. Affected
runs appear in the logs as `ReadTimeout`, `handshake operation timed out` or
`403`, and are excluded from the tables. They are infrastructure failures on
our side, not model failures. Runs where llama-server had not finished
loading appear as `ConnectionError` and are excluded the same way.

`MODELS.sha256`: hashes computed on the phone after the runs; for models
deleted to free space, taken from Hugging Face LFS metadata for the same
download URLs.

## Prior work

The thesis "observation space matters more than brain size" is not ours:

- **AgentOccam** (2024) showed it for the GPT-4 class on WebArena:
  simplifying observations and actions gave +161% with no fine-tuning.
- **WebLINX** (2024) and **MindAct** showed that small models work with a
  compact page representation, after fine-tuning.

Here the same hypothesis is tested at the extreme: no fine-tuning, below 1B,
on phones from 2017 to 2022, with open logs and a no-layer control. We found
no published zero-shot results for sub-1B models on standard web benchmarks;
a comparable number can only come from running a third-party benchmark (the
closest in nature is MiniWoB++), and that is the next series.

## License

MIT for the harness. Models under their authors' licences. E2LLM is a
separate product, used here as the perception layer.
