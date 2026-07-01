# Provenance Guard — planning.md

## 1. Detection Signals

Two signals, each normalized to a **0.0–1.0 float**, where **1.0 = strongly AI-like** and **0.0 = strongly human-like**. Raw, unnormalized scores are never shown to users or combined directly — normalization keeps both signals on the same scale before they're combined.

### Signal 1 — Perplexity Score
- **Measures:** how statistically predictable the text's word choices are under a reference language model (e.g. GPT-2 small via `transformers`, chosen for being small enough to run without a GPU).
- **Raw output:** average per-token log-probability (a negative float, less negative = more predictable).
- **Normalization:** raw perplexity is min-max scaled against a fixed calibration corpus (50 known-human / 50 known-AI samples collected up front) into `perplexity_score ∈ [0, 1]`, where 1.0 = most predictable (AI-like) and 0.0 = least predictable (human-like).

### Signal 2 — Burstiness Score
- **Measures:** uniformity of sentence length and structure across the document.
- **Raw output:** coefficient of variation (stdev / mean) of sentence lengths, in tokens.
- **Normalization:** `burstiness_score = 1 - normalized_CV`, scaled against the same calibration corpus, so 1.0 = highly uniform sentences (AI-like) and 0.0 = highly varied sentence rhythm (human-like).

### Combining into a single confidence score
```
confidence_score = (w1 * perplexity_score) + (w2 * burstiness_score)
w1 = 0.5, w2 = 0.5   # equal weight by default; tunable constants, not hardcoded inline
```
`confidence_score` is a float in `[0, 1]`. It is **not** a calibrated probability in the statistical sense — it's a weighted blend of two heuristic signals — and the system must never present it to users as "there is an X% chance this is AI," only as a relative confidence level (see Section 3).

---

## 2. Uncertainty Representation

A `confidence_score` of **0.6** means: the blended signal evidence leans toward AI-generated, but not strongly enough to be conclusive — it sits in the band where the system should communicate doubt rather than a verdict.

**Thresholds** (tunable constants, not magic numbers scattered in code):
| Range | Meaning |
|---|---|
| `0.00 – 0.34` | Likely Human |
| `0.35 – 0.65` | Uncertain |
| `0.66 – 1.00` | Likely AI-Generated |

The band boundaries are deliberately **not** a binary split at 0.5 — the middle third of the range is reserved for "Uncertain" on purpose, because both signals have known blind spots (Section 4) and collapsing everything into a two-way AI/human split would overstate the system's certainty. Every response includes the raw `confidence_score` alongside the label, never the label alone, so a user (or downstream reviewer) can see how close to a boundary a given result sits.

---

## 3. Transparency Label Design

Exact label text, written now so the UI has a fixed contract to build against:

- **High-confidence AI** (`confidence_score` 0.66–1.00):
  `"⚠️ Likely AI-Generated (confidence: {score})"` — subtext: `"This text shows patterns consistent with AI generation: predictable word choices and uniform sentence structure."`

- **Uncertain** (`confidence_score` 0.35–0.65):
  `"❓ Uncertain (confidence: {score})"` — subtext: `"Signals are mixed. This text has some characteristics of both AI-generated and human-written content."`

- **High-confidence human** (`confidence_score` 0.00–0.34):
  `"✅ Likely Human-Written (confidence: {score})"` — subtext: `"This text shows patterns typical of human writing: varied sentence structure and less predictable word choices."`

Every label always renders with its numeric confidence score and its subtext — the label word alone is never shown without the supporting context, to avoid presenting a heuristic guess as a fact.

---

## 4. Appeals Workflow

- **Who can appeal:** the original submitter (`author_id` on the submission). No third party can appeal on someone else's behalf.
- **What they provide:** `submission_id`, a free-text `reason`, and an optional `evidence` field (e.g. links to other writing samples, an explanation of writing context/disability/non-native-speaker status).
- **What happens on receipt:**
  1. The original submission's `status` changes from `finalized` → `under_review`.
  2. A new entry is appended to that submission's audit log: `{ event_type: "appeal_filed", timestamp, reason, evidence }`. The original scoring entry is never edited or deleted — only appended to.
  3. The appeal enters a review queue for human resolution.
- **What a human reviewer sees when they open the appeal queue:** a list of pending appeals, each showing the original submitted text, the full signal breakdown (`perplexity_score`, `burstiness_score`, `confidence_score`), the original label, the appeal `reason` and `evidence`, and two actions: **Uphold label** or **Overturn label** (with a field to set a manually-corrected label).
- **On resolution:** submission `status` changes to `resolved`, the audit log gets a final entry `{ event_type: "appeal_resolved", timestamp, decision, reviewer_note }`, and if overturned, the *displayed* label is updated while the original automated label and score remain visible in the audit trail (full history is preserved, not overwritten).

---

## 5. Anticipated Edge Cases

1. **A poem or lyrical text with heavy repetition and simple, deliberate vocabulary.** Repetition and simple word choice lower both raw perplexity (predictable words) and raw sentence-length variance (repeated structure), driving both signals toward "AI-like" even though the repetition is an intentional artistic device. Expected result: false "Likely AI-Generated" or "Uncertain" label on a piece of human creative writing.

2. **AI-generated text that has been run through a paraphrasing/"humanizer" tool.** Paraphrasing tools deliberately introduce lexical variety and irregular sentence lengths, which pushes both `perplexity_score` and `burstiness_score` down toward "human-like," even though the underlying content originated from an AI model. Expected result: false "Likely Human" label — a false negative the two chosen signals cannot catch on their own.

3. **Very short submissions (under ~50 words / 2–3 sentences).** Burstiness in particular is a variance measure and is statistically unstable with only one or two sentences to compare — a single long sentence followed by a single short one produces a misleadingly extreme coefficient of variation. Expected result: unstable, low-confidence-in-a-different-sense scores that swing heavily based on a couple of sentences.

4. **Formal/technical human writing (legal boilerplate, academic abstracts, non-native-speaker technical reports).** This style is naturally low-perplexity (precise, conventional vocabulary) and low-burstiness (deliberately uniform, structured sentences) by professional convention, not because it's AI-generated. Expected result: false "Likely AI-Generated," which is the scenario this system's Uncertain band and appeals workflow are specifically designed to catch and correct (see Section 4 of the false-positive walkthrough from Milestone 1).

---

## 6. Architecture

```
Submission Flow:
  Client --POST /submit(raw text)--> Ingestion Layer
    --text--> Signal 1: Perplexity Scorer --perplexity_score-->
    --text--> Signal 2: Burstiness Analyzer --burstiness_score-->
  Confidence Scoring (weighted average) --confidence_score-->
  Transparency Label Generator --label + confidence + signals-->
    --> Audit Log (write)
    --> Response to Client

Appeal Flow:
  Client --POST /appeal(submission_id, reason)--> Appeal Handler
    --lookup + status update--> Audit Log (append)
    --> Response to Client (appeal status)
```

**Narrative:** A submission flows from ingestion through both detection signals in parallel, into a single weighted confidence score, which is mapped to one of three transparency labels and written to an immutable audit log before being returned to the client. Appeals reuse that same audit log — an appeal never overwrites the original automated decision, it appends a review trail on top of it, and only the reviewer's final resolution changes what label is displayed.

*(This diagram carries forward unchanged from Milestone 1 and is the reference diagram given to AI tools during Milestones 3–5.)*

---

## 7. AI Tool Plan

### M3 — Submission endpoint + first signal
- **Spec sections provided to the AI tool:** Section 1 (Perplexity Score subsection only) + Section 6 (Architecture diagram).
- **What I'll ask it to generate:** a Flask app skeleton with a `POST /submit` route (accepting `text`, returning `submission_id` + placeholder response), and the standalone `perplexity_score(text)` function.
- **How I'll verify:** call `perplexity_score()` directly against 3–4 known-human and known-AI text samples *before* wiring it into the endpoint, and confirm the ordering makes sense (known-AI samples score meaningfully higher than known-human samples) before trusting it inside the route.

### M4 — Second signal + confidence scoring
- **Spec sections provided:** Section 1 (both signals, full) + Section 2 (Uncertainty Representation) + Section 6 (Architecture diagram).
- **What I'll ask it to generate:** the standalone `burstiness_score(text)` function, plus the `confidence_score(perplexity_score, burstiness_score)` combination function using the documented `w1=0.5, w2=0.5` weights.
- **How I'll verify:** run the combined pipeline against the same known-human/known-AI sample set from M3 and confirm scores separate meaningfully between the two groups (not clustered together), and check for edge-case failures (e.g. single-sentence input causing a divide-by-zero in the burstiness calculation).

### M5 — Production layer
- **Spec sections provided:** Section 3 (Transparency Label Design) + Section 4 (Appeals Workflow) + Section 6 (Architecture diagram).
- **What I'll ask it to generate:** the `generate_label(confidence_score)` function implementing the exact threshold bands and label text from Section 3, and the `POST /appeal` endpoint plus audit log persistence per Section 4.
- **How I'll verify:** feed `confidence_score` values that straddle each threshold boundary (e.g. `0.20`, `0.34`, `0.35`, `0.50`, `0.65`, `0.66`, `0.90`) and confirm all three label variants are reachable at the correct boundaries; submit a test appeal and confirm the submission's `status` flips to `under_review` and the audit log gets a new appended entry (not an overwrite) via `GET /audit-log/{submission_id}`.