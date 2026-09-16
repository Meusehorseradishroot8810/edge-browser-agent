# Small local models operating real desktop browsers from Android phones

A local language model runs in `llama.cpp` on an Android phone.  
The browser runs on another machine, in a normal live user session - not headless.  
E2LLM/SiFR exposes the live page as structured runtime state, and the phone-side model makes bounded UI decisions against that state.

This repository contains the harnesses, logs, hardware records, model hashes, controls and replay tooling behind three experiment series run in September 2026.

The newest series moves beyond fixed navigation tasks: **Ministral 3 3B running locally on a Galaxy S21 relayed a live conversation between Google Gemini in Chrome and Z.ai in Firefox. The final series passed 10/10 runs, with 4 browser hops per run and automatic reset of both chats.**

These are controlled harness measurements on specific tasks, not a general browser-agent benchmark.

---

## What this repo is testing

The central question is not "how smart is a tiny model in the abstract?"

It is:

> **How much useful browser work can a small local model do when the observation space is structured before the model sees it?**

The model does not receive a screenshot or the raw page HTML. E2LLM/SiFR captures the live browser state and exposes compact, named UI elements and page facts. The surrounding Python harness handles execution, verification and recovery; the model is used where a model decision is actually needed.

That separation is deliberate. The experiments are about the interaction between:

- **perception** - what the model is shown;
- **decision** - what the local model chooses;
- **execution** - what the browser actually does;
- **verification** - whether the intended effect happened.

The browser session, the model and the compute device do not have to be the same product or even the same machine.

---

# Series 3 - live relay across two browsers

**Date:** 15 September 2026  
**Phone:** Samsung Galaxy S21, SM-G991B, Exynos 2100  
**Local model:** Ministral 3 3B Instruct, Q4_K_M  
**Model file:** `ministral-3-3b-Q4_K_M.gguf`  
**Model SHA-256:** `9ed150d4367e68df0ac8e1540f6ddc65b42d0ee26378329d1ecbca60f93fc5f8`  
**Local server:** `llama.cpp`, OpenAI-compatible endpoint on the phone  
**Browser A:** Chrome with Google Gemini  
**Browser B:** Firefox with Z.ai  
**Harness:** [`relay_chat.py`](relay_chat.py)

The two browser services have no direct integration in the harness. The phone-side script carries the conversation by operating their ordinary web interfaces through E2LLM/SiFR.

The local model itself is local inference. The Python harness on the phone still uses network access to reach the E2LLM relay; Gemini and Z.ai are normal cloud services running in the desktop browsers.

## What happens on each browser hop

The loop is intentionally repetitive:

1. **capture** - get the current browser state through E2LLM/SiFR;
2. **choose** - show the local model a compact candidate list for the current UI decision;
3. **act** - execute the chosen action, resolving stale element ids against fresh state when needed;
4. **settle** - observe the page again and wait for a new reply to appear and stabilize.

Typical model input is not the page. It is something like:

```text
div036: message box, "Enter a prompt for Gemini"
```

and the local model returns a bounded decision:

```json
{"target":"div036"}
```

After the message is pasted, the page is captured again and the send control is chosen from fresh SiFR evidence.

The same model is also used to choose the control for starting a brand-new chat during reset.

## What the local model does - and does not do

The local Ministral model:

- generates the opening message;
- chooses the message composer from the candidates shown by the layer;
- chooses the submit control;
- chooses the new-chat/reset control;
- returns each UI choice as a small JSON decision.

The surrounding Python code:

- captures and queries SiFR;
- pastes and clicks;
- re-resolves stale ids after fresh captures;
- verifies that the composer accepted the text;
- detects a newly appearing reply;
- checks that the observed reply is not merely the sent text echoed back;
- carries the cloud reply to the other browser;
- waits for the UI to settle;
- scores the run;
- performs bounded recovery when the UI changes.

The cloud reply itself is **not rewritten by Ministral between hops**. The harness normalizes/limits the observed reply, adds a relay instruction and carries it to the other browser. This experiment tests browser operation by the local model, not whether a 3B model can replace the cloud models generating the conversation.

`relay_chat.py` contains no domain branches and no hard-coded per-site CSS selectors. It does contain generic semantic heuristics for message fields, submit controls, overlays and "new chat" controls.

## Final 10-run result

The public evidence slice covers the final series from `2026-09-15T18:24:32` to `2026-09-15T20:02:16` as written by the phone-side logger.

| Check | Result |
|---|---:|
| Run summaries | **10/10 PASS 3/3** |
| Completed rounds | **20/20** |
| Completed browser hops | **40/40** |
| Replies observed | **40/40** |
| Replies marked non-echo | **40/40** |
| Fresh-chat resets | **20/20** |
| Run time (min / median / max) | **7:59.3 / 9:29.5 / 11:55.7** |
| Battery | **79% → 63%** |
| Recorded battery temperature | **32.5-35.4 °C** |

Each run had three run-level truth bits:

```text
delivered
reply_not_echo
reset_ok
```

All three were true in all ten final runs.

The ten runs took **97 minutes 44 seconds** wall-clock as a series.

There is a visible late-series slowdown in wall-clock run time. The median of runs 1-5 is **9:14**, while runs 6-10 have a median of **10:18** (about **+11.6%**). If the recovery-heavy run 7 and the unusually fast run 1 are excluded, runs 2-6 have a median of **9:17** and runs 8-10 **10:18** (about **+10.9%**).

Over the full series the battery fell from **79% to 63%**. Recorded **battery** temperature stayed between **32.5 and 35.4 °C**. The log did not capture SoC temperature (`soc_temp_c` is unavailable), so this telemetry does **not** prove or rule out SoC thermal throttling. Wall-clock run time also includes browser and cloud-service response time. The cause of the slowdown is not established.

### A non-happy-path run is included

Run 7 is useful because the series was not ten perfectly identical happy paths.

One delivery attempt failed **before send**: the Chrome composer did not accept the pasted message, so the attempt never reached `MESSAGE VERIFIED`, `CHOOSE SEND` or `CLICK SEND`. The script then re-captured the page, temporarily found no composer, entered its bounded recovery path, recovered the live composer from fresh state, pasted the message again, verified it, and only then clicked send once.

So this recovery path did **not** risk a duplicate submit from a second send click. Run 7 still completed all four hops and passed all three run-level checks.

That recovery is present in the public JSONL.

## Evidence files for the relay series

- [`relay_chat.py`](relay_chat.py) - the exact script used for the final series.
- [`logs/relay_gemini_zai_ministral3_3b_10x_2026-09-15.public.jsonl`](logs/relay_gemini_zai_ministral3_3b_10x_2026-09-15.public.jsonl) - the final 10-run series only.
- [`EVIDENCE.md`](EVIDENCE.md) - provenance, source hashes, slice boundaries and redaction procedure.
- [`SHA256SUMS`](SHA256SUMS) - hashes of the public evidence files.
- [`MODELS.sha256`](MODELS.sha256) - model-file hashes.

The original phone log was append-only and also contained three earlier single-run sessions. The public JSONL is the exact final-series slice: **578 JSONL records**.

The source log contained opaque Gemini and Z.ai chat identifiers inside URLs. For the public copy, those chat ids were replaced consistently. No other JSON values were changed. The original full-log hash and the exact unredacted final-slice hash are recorded in `EVIDENCE.md`.

**Full uncut relay video:** <https://youtu.be/T9fJtp1z3-A>

---

# Series 1 and 2 - fixed browser tasks across small models and phones

The earlier series ask a narrower question: can small zero-shot local models make bounded choices and return verified facts when browser perception is already compact?

## Series 1 - 7 September 2026

**Device:** Galaxy Note 8 (2017)  
**Browser:** Chrome  
**Models tested:** 12

Seven of 12 models completed the main task at least once. Five of 12 scored 10/10. The smallest model to score 10/10 was **Qwen3-0.6B**, about 397 MB.

A no-layer control with the same model showed the cost of handing the model raw HTML instead: on the small sandbox task it used about 25× the prompt tokens and took about 17× the time; on the live Wikipedia task the useful page did not fit the phone's context and the control scored 0/3.

## Series 2 - 9-10 September 2026

**Devices:** Galaxy Note 8, Galaxy S21, Galaxy A04e  
**Browser:** Firefox  
**Models tested:** 15  
**Tasks:** fixed sandbox task + live Wikipedia task

The same harness kit was copied across devices, with the same `llama.cpp` commit and the same GGUF files for the compared runs.

Full per-device timings, token counts and medians are in [`RESULTS.md`](RESULTS.md) and [`HARDWARE.md`](HARDWARE.md).

---

## The three devices

| Device | Year | SoC | RAM usable | Android |
|---|---:|---|---:|---:|
| Galaxy Note 8 (SM-N950F) | 2017 | Exynos 8895 | 5.2 GB | 9 |
| Galaxy S21 (SM-G991B) | 2021 | Exynos 2100 | 7.0 GB | 14, then 15 |
| Galaxy A04e (SM-A042F) | 2022 | MediaTek Helio P35 | 2.7 GB | 14 |

The A04e is the slowest device in this set despite being the newest. Qwen3-0.6B scored 10/10 on all three devices on both fixed tasks. What changed most visibly across those runs was the clock: roughly 25, 29 and 62 seconds per main sandbox task on the three phones.

---

# Fixed-task result table

The main task is implemented in [`agent.py`](agent.py).

Starting from an unrelated site, the agent must:

1. navigate to `books.toscrape.com`;
2. open the **Travel** category;
3. open **It's Only the Himalayas**;
4. return:
   - price,
   - star rating as a word,
   - stock status.

The final report is checked against a fixed expected value.

The table below preserves the results from the September model sweep.

| Model | Size | Year | Note 8 | S21 | A04e | Note |
|---|---:|---:|---:|---:|---:|---|
| Qwen3-0.6B | 0.6B | 2025 | **10/10** | **10/10** | **10/10** | copies facts verbatim |
| Qwen3.5-0.8B | 0.8B | 2026 | 7/10 | 39/40 |  | drops the currency sign on the Note 8 |
| Qwen2.5-0.5B | 0.5B | 2024 | 6/10 | 5/10 |  | wrong id, then placeholder |
| Qwen2.5-1.5B | 1.5B | 2024 | 10/10 | 10/10 |  |  |
| GLM-Edge-1.5B | 1.5B | 2024 | 10/10 | 4/10 |  | see "Pass rate is not portable across SoCs" |
| Gemma-2-2B | 2.6B | 2024 | 10/10 |  |  |  |
| MiniCPM5-2B | 2B | 2026 | 9/10 | 5/10 |  | swaps `£` for `$` |
| Llama-3.2-3B | 3B | 2024 | 10/10 | 10/10 |  |  |
| Ministral 3 3B | 3B | 2026 | 10/10 | 10/10 |  |  |
| Llama-3.2-1B | 1B | 2024 | 0/10 |  |  | pseudo-code `candidate['id']` instead of JSON |
| Gemma-3-1B | 1B | 2025 | 0/8 |  |  | copies the `"ID"` placeholder |
| Gemma-3-270M | 0.27B | 2025 | 0/10 |  |  | same |
| LFM2-350M | 0.35B | 2025 | 0/10 |  |  | valid shape, effectively random link choices |
| LFM2.5-1.2B | 1.2B | 2026 | 0/10 | 0/10 |  | copies the placeholder |
| SmolLM2-135M | 0.135B | 2024 | 0/10 | 0/30 |  | echoes the mission text |

These numbers are task/device measurements, not general model rankings.

---

# Additional fixed tasks

## Live Wikipedia - `wiki.py`

Starting from another site, navigate to Wikipedia, open the Galaxy Note series page, choose **Note 8** among nearby decoys such as:

- Note 8.0
- Samsung Galaxy Note 8.0
- Galaxy Note 8.0
- Note FE

The page exposes roughly 760 interactive nodes. The task ends by returning the Note 8 release date from the infobox.

Qwen3-0.6B scored 10/10 on all three phones, 30 runs total.

Ten additional models were tested on the S21. One useful failure case: Qwen2.5-1.5B scored 1/10 because it repeatedly selected the 2013 Note 8.0 tablet despite passing the simpler books task.

## Five fields - `book2.py`

From the catalogue home page, find the target book without a category hint and return:

- title;
- price;
- rating;
- stock;
- UPC.

Qwen3-0.6B: 10/10.

## GitHub stars - `github.py`

Read star and fork counts from a repository page and check the answer against the GitHub API.

Qwen3-0.6B on Firefox: 10/10.

---

# Control - the same model without the perception layer

`control.py` and `control_wiki.py` use Qwen3-0.6B with the same sites, the same browser action path and the same verification idea, but replace the structured observation with raw HTML.

Scripts and styles are stripped. The model must find the target href itself and extract final facts from HTML.

The local server was restarted between control runs so the prompt cache did not carry over. Context was 16,384 tokens, the largest context used on that phone for the control.

|  | Sandbox, with layer | Sandbox, raw HTML | Wikipedia, with layer | Wikipedia, raw HTML |
|---|---:|---:|---:|---:|
| Page size | - | 24,831 chars | - | 466,744 chars; 40,000 sent (~9%) |
| Prompt tokens per task | ~500 | ~12,240 | ~500 | 12,341 for one step |
| Time per task on Note 8 | ~80 s | 22-23 min | ~90 s | 35-44 min |
| Result | 10/10 | 4/5 correct route; one invented href | 10/10 | 0/3 |

On the small page, the model can sometimes complete the task without the layer, but at roughly **25× the prompt tokens** and **17× the wall time**. On the live Wikipedia page, the raw HTML does not fit the local context and the control does not find the required link in the portion that fits.

This control is intentionally narrow. It compares two observation formats for this harness; it does not establish a universal cost ratio for browser agents.

---

# Pass rate is not portable across SoCs

One of the unexpected results of the multi-device series was that the same quantized model file did not always preserve the same pass rate across phones.

| Model | Note 8 | S21 | Observed failure |
|---|---:|---:|---|
| Qwen3.5-0.8B | 7/10 | 39/40 | drops the pound sign, reports `45.17` |
| MiniCPM5-2B | 1 bad report in 10 | 5 bad reports in 10 | swaps `£` for `$` |
| GLM-Edge-1.5B | 10/10 | 4/10 | emits the literal placeholder id |

The compared runs used the same GGUF files, the same prompt, the same server configuration, the same candidate lists from the layer and the same `llama.cpp` commit (`e107984`).

We do **not** have a proven cause.

A plausible explanation is that different CPU/NEON kernels slightly alter logits around a decision boundary, but that remains a hypothesis. What the measurements support directly is narrower:

> **A pass rate measured on one phone should not automatically be assumed to transfer to another SoC.**

The structured observation remains the constant, which is what makes those model/device differences visible.

---

# Who does what in the fixed-task harness

The relay experiment above has its own role split. The fixed tasks use a simpler one.

## Eyes - E2LLM/SiFR

- capture the live page as structured runtime state;
- query the interactive nodes;
- reduce the page to a compact candidate set for the harness;
- expose page facts needed by the task;
- execute browser actions in the user's live browser session.

For the fixed tasks, the harness keeps at most ten candidates: exact target-name matches first, then an even sample across page sections, excluding links to the current page.

## Brain - local model

For the main fixed task:

- step 0: emit a `navigate` action to the given URL;
- steps 1-2: choose a target id from the presented candidate list;
- final step: return a structured report from the facts it was given.

The model does not receive raw HTML, screenshots or candidate URLs in the layer condition.

That is deliberate. The experiment is measuring what changes when the observation space is compact and task-relevant.

---

# Limits

The most important limitations are part of the result, not footnotes.

- **These are not standard web-agent benchmarks.** They are purpose-built harnesses with explicit verification.
- The fixed tasks are mostly name matching and fact copying. They are useful for testing observation format and minimum model capability, not broad planning ability.
- Where more judgement is required, small models fail. Qwen2.5-1.5B passes the simple books task at 10/10 but repeatedly chooses the wrong Note 8 on Wikipedia.
- Pass rates are **per device / SoC**.
- In the books tasks the target appears on the first catalogue page; pagination was not part of those measurements.
- Copying is not always verbatim. Some models normalize words to digits or corrupt currency symbols.
- Below roughly 0.5B in this sweep, models generally failed to maintain the required action/report shape.
- The live relay is one repeated scenario with two web services, not proof of universal site compatibility.
- The 10/10 relay result includes script-side verification and bounded recovery. It should not be read as "the model made every low-level operation perfectly on the first attempt."
- Reproducing live browser runs requires E2LLM access because the relay is hosted by the authors.

---

# How to reproduce

## 1. Phone setup

Termux:

```bash
pkg install python git cmake clang make termux-api
pip install requests
```

Build `llama.cpp` from source. The fixed-task September series used commit `e107984` (full environment records are in the `ENV*.json` files).

Example local server:

```bash
./llama.cpp/build/bin/llama-server \
  -m models/qwen3-0.6b-Q4_K_M.gguf \
  -c 4096 \
  -t 4 \
  --port 8080 \
  --jinja \
  --log-disable
```

For the relay series, use the Ministral model recorded in `MODELS.sha256`:

```text
mistralai/Ministral-3-3B-Instruct-2512-GGUF
Ministral-3-3B-Instruct-2512-Q4_K_M.gguf
```

## 2. Browser / E2LLM

Install the E2LLM extension in Chrome or Firefox and connect the browser through:

<https://e2llm.com/start>

The fixed single-browser series should have one test browser connected at a time.

The live relay is different: **Chrome and Firefox are intentionally connected at the same time.**

## 3. Fixed-task runs

```bash
python hdr.py
./run_model.sh <gguf> "<label>" <log-name>
./fleet_run.sh <gguf> [runs]

python wiki.py
python book2.py
python github.py

# no-layer controls
python control.py
python control_wiki.py
```

`fleet_run.sh` writes an `ENV_<device>.json` beside the logs with device information, model-file hash, `llama.cpp` commit, server flags, SoC, RAM and Android version, then packages the run material.

## 4. Live relay

Have one target service open in Chrome and the other in Firefox, both connected through E2LLM.

With the local Ministral server already running:

```bash
MODEL_NAME="Ministral 3 3B" python relay_chat.py \
  --a Chrome \
  --b Firefox \
  --rounds 2 \
  --runs 10 \
  --log logs/relay_gemini_zai.jsonl
```

The exact public evidence file in this repository is a redacted slice of the phone's append-only source log, not a log regenerated after the fact.

---

# Replay without a browser or an E2LLM account

[`replay.py`](replay.py) re-runs the **model side of the fixed-task harness** offline.

It takes recorded candidate lists and facts from the fixed-task logs, rebuilds the prompts, sends them to an OpenAI-compatible local server and scores the decisions.

No E2LLM relay and no live browser are needed for this replay mode.

```bash
python replay.py logs/wiki_note8.jsonl

python replay.py logs/*.jsonl \
  --url http://127.0.0.1:11434/v1/chat/completions
```

Limit: if a live run produced an invalid decision before the candidate list was logged in replayable form, that step cannot be replayed.

Replay scoring is also intentionally stricter than live scoring in one respect: a live run that clicks a wrong target and later recovers can still pass live verification, while replay marks the initial wrong decision as a failure.

`replay.py` does **not** currently recreate the full live Gemini ↔ Z.ai relay; the relay JSONL is provided as evidence rather than an offline browser simulation.

---

# Logs and provenance

## Fixed-task logs

`logs/` contains the September fixed-task runs, including early runs where the harness itself still had bugs.

Second-series files follow the pattern:

```text
<device>_<task>_<model>_<date>.jsonl
```

Two early/interrupted experiment files are not counted in the model tables:

- `e2llm_onboarding_5steps.jsonl`
- `cookie_banners.jsonl`

During the 10 September sweep the authors' relay also experienced infrastructure failures. Affected records contain errors such as:

```text
ReadTimeout
handshake operation timed out
403
ConnectionError
```

Those infrastructure failures were not counted as model failures in the tables. The logs retain them.

## Relay evidence

The live-relay public evidence is handled separately because the source file was append-only and contained private chat ids in service URLs.

See [`EVIDENCE.md`](EVIDENCE.md) for:

- source archive SHA-256;
- original full append-log SHA-256;
- exact unredacted final-series slice SHA-256;
- source line range;
- public redaction procedure.

`SHA256SUMS` covers the public relay files.

---

# Model hashes

[`MODELS.sha256`](MODELS.sha256) records hashes for the model files used in the sweep.

For models that still existed on the phone, hashes were computed from the local files. For models deleted to free storage, the repository notes where the matching Hugging Face LFS metadata was used instead.

The Ministral relay model entry is:

```text
9ed150d4367e68df0ac8e1540f6ddc65b42d0ee26378329d1ecbca60f93fc5f8  ministral-3-3b-Q4_K_M.gguf
```

---

# Prior work

The general idea that agent performance depends strongly on the observation/action space is not new.

Relevant prior work includes:

- **AgentOccam (2024)** - simplifying observations and actions improved WebArena performance without fine-tuning.
- **WebLINX (2024)** - studied language-model interaction with web navigation/dialogue data.
- **MindAct** - showed the value of compact candidate/action representations for web interaction.

The September experiments in this repository push a related question toward the low-compute edge:

- no task-specific fine-tuning;
- models down into the sub-1B range;
- phones from 2017-2022;
- a no-layer raw-HTML control;
- multi-SoC repeats;
- open logs;
- and, in the newest series, a 3B local model operating two independent live browser applications in sequence.

We have not established a comparable standard-benchmark number for the smallest models here. A third-party benchmark such as MiniWoB++ would be a separate experiment and should not be inferred from these harness results.

---

# Why the live relay matters

The relay is intentionally a simple conversation task. The content of the conversation is not the point.

The architectural fact being tested is that:

- the **model compute** can live on a phone;
- the **application state** can live in the user's existing desktop browsers;
- the **cloud services** can remain independent;
- a structured perception/action layer can connect the model to those real interfaces without handing it the whole raw page.

We use the term **Browser as Shared Space (BaSS)** for the broader direction: the browser remains the visible user-governed workspace, while different models and compute locations can participate through the same live environment.

The result here is evidence for one concrete configuration of that idea - not proof of the entire thesis.

---

# License

MIT for the harness code in this repository.

Models are subject to their authors' licenses.

E2LLM/SiFR is a separate product used here as the browser perception/action layer.
