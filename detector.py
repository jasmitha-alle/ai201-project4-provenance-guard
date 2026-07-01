import os
import re
import math
import json
from groq import Groq

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


_PROMPT = """You are an expert at detecting AI-generated text.

Analyse the passage below and estimate the probability it was produced by an AI writing system (GPT, Claude, Gemini, etc.).

Respond with ONLY valid JSON in this exact format, nothing else:
{{"ai_probability": <float 0.00-1.00>, "reasoning": "<one sentence>"}}

Passage:
\"\"\"
{text}
\"\"\"
"""


def llm_signal(text: str) -> dict:
    """
    Signal 1: Groq LLM classifier.
    Returns {"score": float, "reasoning": str} where score is P(AI-generated), 0–1.
    Falls back to {"score": 0.5, "reasoning": "unavailable"} on any error.
    """
    word_count = len(text.split())
    if word_count < 40:
        return {"score": 0.5, "reasoning": "Text too short for reliable LLM signal."}

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": _PROMPT.format(text=text[:3000])}],
            temperature=0.1,
            max_tokens=100,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        if "```" in raw:
            raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

        data = json.loads(raw)
        score = float(data["ai_probability"])
        score = max(0.0, min(1.0, score))
        return {"score": round(score, 3), "reasoning": str(data.get("reasoning", ""))}

    except Exception as e:
        return {"score": 0.5, "reasoning": f"unavailable: {e}"}

def heuristic_signal(text: str) -> dict:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    words = re.findall(r'\b\w+\b', text)

    # Burstiness: coefficient of variation of sentence lengths
    lengths = [len(s.split()) for s in sentences if s.strip()]
    if len(lengths) >= 2:
        mean = sum(lengths) / len(lengths)
        std = math.sqrt(sum((l - mean) ** 2 for l in lengths) / len(lengths))
        cv = std / mean if mean > 0 else 0
        burstiness_ai = max(0.0, min(1.0, 1.0 - (cv / 0.8)))
    else:
        burstiness_ai = 0.5

    # Type-token ratio
    if len(words) >= 50:
        ttr = len(set(w.lower() for w in words)) / len(words)
        ttr_ai = max(0.0, min(1.0, 1.0 - ((ttr - 0.40) / 0.45)))
    else:
        ttr_ai = 0.5

    # Punctuation density
    punct = len(re.findall(r'[,;:]', text))
    density = punct / len(words) if words else 0
    punct_ai = 0.65 if 0.04 <= density <= 0.18 else 0.35

    score = (burstiness_ai * 0.45) + (ttr_ai * 0.35) + (punct_ai * 0.20)

    return {
        "score": round(score, 3),
        "details": {
            "burstiness_ai": round(burstiness_ai, 3),
            "ttr_ai": round(ttr_ai, 3),
            "punct_ai": round(punct_ai, 3),
        }
    }

def compute_confidence(llm_score: float, heuristic_score: float) -> float:
    combined = (llm_score * 0.60) + (heuristic_score * 0.40)
    base = abs(combined - 0.5) * 2
    disagreement = abs(llm_score - heuristic_score)
    penalty = max(0.0, (disagreement - 0.15) / 0.85)
    confidence = base * (1.0 - penalty * 0.5)
    return round(max(0.0, min(1.0, confidence)), 3)

def build_label(attribution: str, confidence: float) -> str:
    pct = round(confidence * 100)
    if attribution == "likely_ai" and confidence >= 0.80:
        return f"⚠️ Likely AI-Generated — Our system is {pct}% confident this content was produced by an AI writing tool. It has been held for editorial review. If you wrote this yourself, see 'Appeal this decision' below."
    elif attribution == "likely_human" and confidence >= 0.75:
        return f"✅ Likely Human-Written — Our system is {pct}% confident this content was written by a person. No AI concerns detected. Cleared for publication."
    else:
        return f"❓ Origin Uncertain — Our system could not confidently determine authorship ({pct}% confidence). Queued for human review. If you wrote this yourself, see 'Appeal this decision' below."
