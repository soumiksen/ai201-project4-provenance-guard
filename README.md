# Provenance Guard

A text-provenance detection API: submitted text is scored by two detection
signals, combined into a confidence score, mapped to a transparency label,
and logged to an append/update-able audit trail. Creators can appeal a
label, which flips the submission's status to `under_review` without
erasing the original automated decision.

Full design rationale lives in [`planning.md`](./planning.md). This README
covers running the app and the evidence gathered while building it.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # optional - see below
python3 app.py          # runs on http://localhost:5000
```

### Optional: real Signal 1 (Groq)

Signal 1 calls Groq's chat completions API for a structured AI-likelihood
assessment. Without a key, it automatically falls back to a local heuristic
scorer so the app is runnable and testable out of the box - the fallback is
clearly marked (`signal_1_source: "heuristic_fallback"` in every audit log
entry) and is not a substitute for the real signal.

```
# .env
GROQ_API_KEY=your-key-here
GROQ_MODEL=llama-3.1-8b-instant
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/submit` | Submit text for classification |
| `POST` | `/appeal` | Appeal a submission's label |
| `GET` | `/log` | View recent audit log entries |
| `GET` | `/health` | Liveness check |

### `POST /submit`

```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "...", "creator_id": "some-user"}'
```

Returns `content_id`, `attribution`, `confidence`, the full transparency
`label` (headline + subtext), and both individual `signals`.

### `POST /appeal`

```bash
curl -s -X POST http://localhost:5000/appeal \
  -H "Content-Type: application/json" \
  -d '{"content_id": "<id-from-submit>", "creator_reasoning": "..."}'
```

Sets the submission's status to `under_review` and records
`appeal_reasoning` + `appeal_timestamp` on its audit log entry, alongside
the original (unmodified) classification fields. No automated
re-classification happens - this milestone only requires logging and
status change, per spec.

## Rate limiting

`/submit` is limited to **10 per minute; 100 per day** per client, `/appeal`
to **10 per minute**.

**Reasoning:** a writer submitting their own drafts realistically sends a
handful of requests in a sitting - 10/minute is roughly one submission every
6 seconds, comfortably above normal typing/pasting pace, while a flooding
script hits the ceiling almost immediately. The 100/day cap exists
separately from the per-minute cap so a well-behaved but prolific user
(submitting steadily across a full day) isn't blocked, while a burst-then-
retry abuse pattern still gets capped over the course of a day.

**Verified evidence** (fresh server, 12 rapid sequential requests against
the 10/minute limit):

```
$ for i in $(seq 1 12); do
    curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:5000/submit \
      -H "Content-Type: application/json" \
      -d '{"text": "This is a test submission for rate limit testing purposes only.", "creator_id": "rate-test-user"}'
  done

201
201
201
201
201
201
201
201
201
201
429
429
```

First 10 requests succeed, remaining 2 are correctly rejected with `429`.

## Transparency label variants

All three variants confirmed reachable by submitting inputs at different
confidence levels (real responses, captured live):

- **Likely human** (confidence 0.154): `✅ Likely Human-Written (confidence: 0.154)`
- **Uncertain** (confidence 0.557): `❓ Uncertain (confidence: 0.557)`
- **Likely AI** (confidence 0.83): `⚠️ Likely AI-Generated (confidence: 0.83)`

## Appeals workflow verification

Appeal filed against a `likely_human` submission (`content_id`
`57756018-...`), then confirmed via `GET /log`:

```json
{
  "content_id": "57756018-762f-467f-b796-7f9b57ae9d79",
  "status": "under_review",
  "appeal_filed": true,
  "appeal_reasoning": "I wrote this myself from personal experience at a ramen restaurant last week.",
  "appeal_timestamp": "2026-07-01T03:07:33.520343+00:00",
  "attribution": "likely_human",
  "confidence": 0.154
}
```

Status flipped to `under_review`, `appeal_reasoning` is populated, and the
original `attribution`/`confidence` from the automated decision are
preserved untouched.

## Audit log

Every `/submit` call and `/appeal` call is written to `audit_log.json` as a
structured entry (not console output) capturing: `timestamp`, `content_id`,
`creator_id`, `attribution`, `confidence`, both individual signal scores
(`llm_score`, `stylometric_score` plus their sub-metrics), `status`, and
appeal fields once filed. `GET /log?limit=N` returns the N most recent
entries, newest first.

## Known limitations (see planning.md Section 5 for the full list)

- The offline Signal 1 fallback is a rough heuristic, not a real LLM call -
  expect it to under-perform the real Groq-backed signal on ambiguous text.
- Sentence-length variance is unreliable on single-sentence submissions
  (`sentence_length_cv` returns `null` in that case rather than a
  misleading number).
- Type-token ratio barely varies on short (~40-70 word) paragraphs
  regardless of origin, so it's intentionally down-weighted relative to
  sentence-length uniformity in Signal 2 - see comments in
  `signal_2_stylometric.py` for the debugging that led to this.
