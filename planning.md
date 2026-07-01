Provenance Guard — Planning

Detection Signals

Signal 1 is a Groq LLM classifier (weight 0.60). It estimates P(AI-generated) holistically by reading the full passage and returning a float 0–1. It captures hedging language, uniform register, and over-explanation — things that are hard to hand-code. Blind spot: formal human writing triggers false positives.

Signal 2 is a statistical heuristic (weight 0.40) combining three sub-measures. Burstiness (0.45 of signal 2) measures coefficient of variation in sentence lengths — AI text is flat, human text varies. Type-token ratio (0.35) measures unique/total words — AI repeats high-probability tokens, so low TTR signals AI; meaningless under 50 words. Punctuation density (0.20) measures commas and semicolons per word — AI lands in 0.04–0.18/word, outside that range leans human. Blind spot: anaphoric poetry and careful non-native English prose both look flat to these measures.

Combined score: (llm × 0.60) + (heuristic × 0.40).


Uncertainty Representation

Confidence is separate from the combined score. It measures certainty about the verdict, not the direction.

    base = |combined - 0.5| × 2
    disagreement = |llm_score - heuristic_score|
    penalty = max(0, (disagreement - 0.15) / 0.85)
    confidence = base × (1 - penalty × 0.5)

A confidence of 0.6 means the combined score is around 0.80 AI with reasonable signal alignment, but not certain enough to make an accusation. It lands in the uncertain band.

Thresholds: confidence ≥ 0.80 and combined ≥ 0.50 → AI. Confidence ≥ 0.75 and combined < 0.50 → HUMAN. Everything else → UNCERTAIN. The AI threshold is higher because a false positive (accusing a human) is the worse error.


Transparency Labels

High-confidence AI: "⚠️ Likely AI-Generated — Our system is [X]% confident this content was produced by an AI writing tool. It has been held for editorial review. If you wrote this yourself, see 'Appeal this decision' below."

High-confidence human: "✅ Likely Human-Written — Our system is [X]% confident this content was written by a person. No AI concerns detected. Cleared for publication."

Uncertain: "❓ Origin Uncertain — Our system could not confidently determine authorship ([X]% confidence). Queued for human review. If you wrote this yourself, see 'Appeal this decision' below."

[X] is round(confidence × 100). The uncertain label always shows the appeal path because borderline cases are the most likely false positives.


Appeals Workflow

Anyone with a submission_id can appeal by providing a reason (min 10 chars). On receipt: validate the submission exists and status is "decided" (409 if already under review), write to appeals table, update status to "under_review", write APPEAL event to audit log, return 202. A reviewer calls GET /log?event_type=APPEAL to see the queue and GET /submission/:id for the original decision. Resolution via POST /appeal/:id/resolve sets status to "reviewed" and writes a RESOLUTION log entry.


Anticipated Edge Cases

Anaphoric poetry uses heavy lexical repetition and parallel short lines. Both heuristic sub-signals fire toward AI. If the LLM also misreads the plain style, confidence may cross 0.80 and produce a high-confidence false positive on deliberate craft.

Text under 40 words: TTR is meaningless, burstiness can't be estimated from 2–3 sentences. Heuristics should be skipped entirely and confidence forced below the uncertain threshold. This is a known gap in the current implementation.


Architecture

SUBMISSION
POST /analyze --> Signal 1 (LLM) --> Confidence Scorer --> Label Builder --> Audit Log --> Response 201
              --> Signal 2 (stats) /

APPEAL
POST /appeal/:id --> Validate --> Status Update --> Audit Log --> Response 202

The audit log is the shared persistence layer. Every decision and appeal is a row with an event_type discriminator (DECISION, APPEAL, RESOLUTION).


AI Tool Plan

M3: Signal 1 spec + diagram → Flask skeleton + llm_signal(text) -> {score, reasoning}. Test on AI prose, a poem, and formal human writing before wiring into the route.

M4: Signal 2 spec + uncertainty formula + diagram → heuristic_signal(text) + compute_confidence(llm, heuristic). Check: llm=0.90/heuristic=0.40 should score below 0.60 confidence.

M5: Label strings + appeals workflow + diagram → build_label(result, confidence) + /appeal/:id + /appeal/:id/resolve. Check all three label variants are reachable and APPEAL/RESOLUTION entries appear in GET /log.