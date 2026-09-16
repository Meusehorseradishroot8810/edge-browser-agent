# E2LLM / SiFR - Ministral 3 3B browser relay evidence

This package contains the exact relay script used for the recorded 10-run series and a public copy of the corresponding JSONL evidence.

## Files

- `README.md` - repository README updated for the relay series.
- `relay_chat.py` - bit-for-bit identical to the script in the source archive.
- `logs/relay_gemini_zai_ministral3_3b_10x_2026-09-15.public.jsonl` - the final 10-run series only.
- `SHA256SUMS` - hashes for the public files.

## Full video

<https://youtu.be/T9fJtp1z3-A>

## Result represented by the public log

- 10 run summaries.
- 10/10 have `ok=true` and `score=3`.
- Each run completed 2 rounds and 4 hops.
- All three run-level checks are true in every run: `delivered`, `reply_not_echo`, `reset_ok`.
- 40 reply records; all 40 have `ok=true` and `echo_free=true`.
- 20 reset records; all 20 have `ok=true`.
- Run time from `RUN START` to `RUN PASSED`: min 7:59.3, median 9:29.5, max 11:55.7.
- Full series wall-clock span: 97:44.4.
- Median runs 1-5: 9:14; median runs 6-10: 10:18 (+11.6%).
- Recorded battery telemetry across the series: 79% down to 63%.
- Recorded battery temperature range: 32.5-35.4 °C.
- SoC temperature was unavailable (`soc_temp_c: null`), so the log does not establish or rule out SoC thermal throttling.
- Run 7 contains one pre-send delivery retry: the first paste was not committed and no send click occurred before the retry.

Timestamps in the JSONL are the timestamps written by the script and do not embed a UTC offset.

## Provenance

Source archive SHA-256:

`bf190d3b5b9de3e380aa152a6b5f5c8eb026eba1a3be5c5d7e94784eeb7526df`

Original full append log SHA-256:

`490b2fd1b0bd52d87cb99a73a6ba04b212f566979bcecb5d93bf8a3cb9b0fff2`

Exact unredacted final-series slice SHA-256:

`82d71e52b050ad73d0e53eacd95db878d9b969b1757b12dce02aeff2a05d117c`

The public JSONL corresponds to original log lines 175-752 inclusive (578 JSONL records).

## Redaction

The original append log contains opaque chat IDs in Gemini and Z.ai URLs. For the public copy:

- 10 unique Gemini chat IDs were replaced consistently with `REDACTED_GEMINI_CHAT_01` … `10`.
- 10 unique Z.ai chat IDs were replaced consistently with `REDACTED_ZAI_CHAT_01` … `10`.
- No other JSON values were changed.
- Line order and JSON formatting were preserved.

The public copy contains no raw Gemini/Z.ai chat IDs from the source log.

## Scope

This evidence supports the reported result for this specific scripted scenario. It is not a general browser-agent benchmark.
