# Hardware: same layer, three devices

Second series, 9-10 September 2026. Nothing was adapted per device: the kit
was copied over, llama.cpp was built from the same commit e107984, and the
runs started. Same task scripts, same prompt, same GGUF files (md5 recorded
in each device's ENV json).

| Device | Year | SoC | RAM usable | Android |
|---|---|---|---|---|
| Galaxy Note 8 (SM-N950F) | 2017 | Exynos 8895 | 5.2 GB | 9 |
| Galaxy S21 (SM-G991B) | 2021 | Exynos 2100 | 7.0 GB | 14, then 15 |
| Galaxy A04e (SM-A042F) | 2022 | MediaTek Helio P35 (mt6765) | 2.7 GB | 14 |

The A04e sells for about 100 dollars. It is the slowest of the three and the
only non-Exynos one. The browser side is Firefox on the laptop for this
series, not Chrome.

## Task 1 (books.toscrape)

Same task as the first series. Pass rate over the last 10 runs per file, then
median seconds per run: total, and the part spent inside the model.

| Model | Note 8 | S21 | A04e | Note 8 s | S21 s | A04e s |
|---|---|---|---|---|---|---|
| Qwen3-0.6B | 10/10 | 10/10 | 10/10 | 25 (19) | 29 (19) | 62 (50) |
| Qwen3.5-0.8B | 7/10 | 10/10 | | 78 (66) | 29 (20) | |
| Qwen2.5-0.5B | 6/10 | 5/10 | | 44 (32) | 40 (28) | |
| Qwen2.5-1.5B | 10/10 | 10/10 | | 79 (67) | 32 (22) | |
| GLM-Edge-1.5B | 9/10 | 4/10 | | 94 (78) | 23 (16) | |
| MiniCPM5-2B | 9/10 | 5/10 | | 110 (91) | 43 (33) | |
| Gemma-2-2B | 10/10 | | | 145 (128) | | |
| Llama-3.2-3B | 10/10 | 10/10 | | 150 (139) | 48 (37) | |
| Ministral 3 3B | 10/10 | 10/10 | | 211 (193) | 59 (47) | |
| LFM2.5-1.2B | 0/10 | 0/10 | | 12 (3) | 11 (3) | |
| Llama-3.2-1B | 0/10 | | | 40 (7) | | |
| Gemma-3-1B | 0/8 | | | 12 (4) | | |
| LFM2-350M | 0/10 | | | 89 (71) | | |
| Gemma-3-270M | 0/10 | | | 11 (4) | | |
| SmolLM2-135M | 0/10 | 0/10 | | 18 (4) | 9 (3) | |

Qwen3.5-0.8B was run more than ten times on the S21: 40 runs across three
sessions, 39 passes. SmolLM2-135M: 30 runs on the S21, 0 passes.

## Wikipedia task

From the Galaxy Note series page, pick the link to the Note 8 phone among
Note 8.0 decoys, read the release date from the infobox.

| Model | Note 8 | S21 | A04e | Note 8 s | S21 s | A04e s |
|---|---|---|---|---|---|---|
| Qwen3-0.6B | 10/10 | 10/10 | 10/10 | 49 (31) | 53 (36) | 57 (38) |
| Qwen3.5-0.8B | | 30/30 | | | 45 (28) | |
| Qwen2.5-0.5B | | 6/10 | | | 37 (23) | |
| Qwen2.5-1.5B | | 1/10 | | | 33 (21) | |
| GLM-Edge-1.5B | 9/10 | 10/10 | | 77 (52) | 50 (31) | |
| MiniCPM5-2B | | 10/10 | | | 49 (31) | |
| Llama-3.2-3B | | 9/10 | | | 49 (31) | |
| Ministral 3 3B | | 10/10 | | | 59 (38) | |
| LFM2.5-1.2B | | 0/9 | | | | |
| SmolLM2-135M | | 0/30 | | | | |

## What the numbers say

**Pass or fail is set by the model. Waiting time is set by the device.**
Qwen3-0.6B is 10/10 on all three devices, including the 100 dollar one with
2.7 GB of usable RAM and a MediaTek chip. What changes is the clock: 25, 29
and 62 seconds per task.

**Between the two flagships, four years of hardware buy nothing for a small
model.** Model time is 19 seconds on both the 2017 and the 2021 device. A
0.6B model on 4 threads waits on memory, not on arithmetic. The gap opens
with model size: Ministral 3B needs 193 seconds of model time on the Note 8
and 47 on the S21, four times faster. Llama-3.2-3B: 139 against 37.

**The budget device pays a real price and is still usable.** The A04e needs
50 seconds of model time against 19 on the flagships. One minute per task.
Building llama.cpp on it took about an hour; running the agent does not.

**Layer overhead is small and predictable.** Capture plus act costs about 6
seconds per task on the Note 8, 10 on the S21, 12 on the A04e. It grows far
more slowly than model time, which spans 3 to 193 seconds across these runs.

**Same GGUF, same llama.cpp commit, same prompt, different SoC, different
pass rate.** Three models move in different directions between the Note 8 and
the S21:

| Model | Note 8 | S21 | What goes wrong |
|---|---|---|---|
| Qwen3.5-0.8B | 7/10 | 39/40 | drops the pound sign, reports 45.17 |
| MiniCPM5-2B | 1 bad report in 10 | 5 bad reports in 10 | swaps the pound sign for a dollar sign |
| GLM-Edge-1.5B | 9/10 | 4/10 | emits the literal placeholder ID as the target |

Both devices ran the same prompt version on the same model files. We do not
have a proven cause. The plausible one is that ggml selects different NEON
kernels for the two CPUs, logits differ slightly, and a token near the
decision boundary falls differently. What we can state without a cause: a
pass rate measured on one phone does not transfer to another phone, and a
result reported without naming the SoC is incomplete.

The layer is the constant in all of this. Same capture, same candidate ids,
same verification on every device. That is what makes the model differences
measurable at all.

## Failure modes worth naming

- **Qwen2.5-1.5B on Wikipedia, 1/10.** It clicks "Galaxy Note 8.0", the 2013
  tablet, instead of "Galaxy Note 8", the 2017 phone, eight times out of ten,
  then reports a null date. The same model passes task 1 at 10/10.
  Qwen3-0.6B, half the size and a year newer, picks the right link 30 times
  out of 30.
- **Nothing below roughly 0.5B answered in the required shape.** SmolLM2-135M
  echoes the mission text back verbatim, including the example JSON.
  LFM2.5-1.2B answers with the literal placeholder from the prompt template
  on every step. These are not wrong choices, they are non-answers, and speed
  does not help: SmolLM2 spends 3 seconds per attempt.
- **GLM-Edge on the S21 fails fast.** 16 seconds of model time per run, the
  quickest of the mid-size models, and 4/10. Speed and correctness are
  separate axes.
- **Expected refusals are normal operation.** "same-URL navigate", "Element
  changed since capture" and similar responses appear in most runs. Models
  act on them and finish the task. They are signals, not errors.

## Reproducing

Each device writes an ENV json next to its logs with the model file md5, the
llama.cpp commit, server flags, SoC, RAM and Android version. Raw jsonl for
every run above is in `logs/`. Server: `-c 4096 -t 4 --jinja`, temperature
0.1. `fleet_run.sh <gguf> <runs>` runs task 1 and the Wikipedia task on any
device and names the logs after the device.
