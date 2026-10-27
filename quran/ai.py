"""
ai.py — Groq يختار فقط (1) الكلمة المناسبة من الآية و(2) أي جملة من التفسير تشرحها.
لا يكتب أي نص من عنده: المقتطف يجب أن يكون جزءًا حرفيًا من التفسير المنقول من المصدر، وإلا يُرفض.
"""
import json
import os
import re
import time

import requests

from . import quran_api as qa

API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODELS = [m for m in [os.environ.get("GROQ_MODEL"), "openai/gpt-oss-120b", "openai/gpt-oss-20b"] if m]
STOP = {"من", "في", "علي", "الي", "عن", "ما", "لا", "ان", "قد", "ثم", "او", "هو", "هي", "هم", "ذلك", "التي", "الذي", "الذين",
        "هذا", "هذه", "كان", "كانوا", "انه", "انهم", "اذا", "الا", "بل", "ولا", "فلا", "وما", "فما", "ومن", "فمن", "لم", "لن",
        "كل", "ذلك", "اولئك", "هؤلاء", "الله", "لله", "بالله", "والله", "فالله", "تالله", "انا", "انت", "نحن", "عليهم", "عليه",
        "منهم", "منه", "فيها", "فيه", "بها", "به", "لهم", "له", "لها", "اليه", "اليهم", "ربنا", "ربك", "ربهم"}
MIN_EXCERPT, MAX_EXCERPT = 18, 190


class AIError(RuntimeError):
    pass


def _chat(messages, temperature=0.3, retries=3):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise AIError("GROQ_API_KEY غير موجود")
    last = None
    for model in MODELS:
        payload = {"model": model, "messages": messages, "temperature": temperature,
                   "response_format": {"type": "json_object"}, "max_completion_tokens": 1200}
        if model.startswith("openai/gpt-oss"):
            payload["reasoning_effort"] = "low"
        for attempt in range(retries):
            try:
                r = requests.post(API_URL, headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=90)
                if r.status_code in (400, 404) and "model" in r.text.lower():
                    last = f"{model}: {r.text[:150]}"
                    break
                if r.status_code == 429 or r.status_code >= 500:
                    last = f"{model}: HTTP {r.status_code}"
                    time.sleep(5 * (attempt + 1))
                    continue
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
                m = re.search(r"\{.*\}", content, re.S)
                return json.loads(m.group(0) if m else content)
            except (requests.RequestException, ValueError, KeyError) as e:
                last = e
                time.sleep(3)
    raise AIError(f"Groq: {last}")


def tokens_of(verse):
    return verse.split()


def selectable(tokens):
    """فهارس الكلمات التي يجوز اختيارها: ليست علامات وقف ولا أدوات شائعة ولا قصيرة جدًا."""
    out = []
    for i, t in enumerate(tokens):
        b = qa.bare(t)
        if len(b) >= 3 and b not in STOP:
            out.append(i)
    return out


def _norm_ws(s):
    return re.sub(r"\s+", " ", s).strip()


def pick_word(surah_name, surah, ayah, verse, tafsirs, avoid_idx=()):
    """يرجع {index, token, excerpt, source_id, source_label} بعد التحقق الحرفي، أو يرفع AIError."""
    toks = tokens_of(verse)
    cand = [i for i in selectable(toks) if i not in set(avoid_idx)]
    if not cand:
        raise AIError("لا كلمة صالحة في هذه الآية")
    listing = "\n".join(f"[{i}] {toks[i]}" for i in cand)
    srcs = "\n\n".join(f"SOURCE {n + 1} ({label}):\n{text[:1800]}" for n, (_, label, text) in enumerate(tafsirs))
    d = _chat([
        {"role": "system", "content": "You are a careful Quran-studies assistant. You never invent or paraphrase religious text. One JSON object only."},
        {"role": "user", "content": f"""Surah {surah_name}, ayah {ayah}.
Ayah (Uthmani): {verse}
Selectable words:
{listing}

Tafsir sources (verbatim, Arabic):
{srcs}

Task: choose ONE selectable word that is a meaningful content word worth learning (a noun, verb or adjective whose meaning a learner would benefit from), AND whose meaning or context is actually explained in one of the sources.
Then copy from the source an EXACT contiguous excerpt (character for character, {MIN_EXCERPT}-{MAX_EXCERPT} characters, a clause or sentence) that explains that word's meaning in this ayah. Do NOT paraphrase, add, or fix anything. If no source explains any selectable word, answer {{"index": null}}.
JSON: {{"index": <number or null>, "source": <1 or 2>, "excerpt": "<exact copy>"}}"""}])
    idx = d.get("index")
    if idx is None:
        raise AIError("لا شرح مناسب للكلمات في التفسير")
    try:
        idx, n = int(idx), int(d.get("source") or 1)
        sid, label, text = tafsirs[n - 1]
    except (ValueError, IndexError, TypeError):
        raise AIError("اختيار غير صالح من Groq")
    if idx not in cand:
        raise AIError(f"فهرس غير مسموح: {idx}")
    excerpt = _norm_ws(str(d.get("excerpt") or "")).strip(" «»\"")
    if not MIN_EXCERPT <= len(excerpt) <= MAX_EXCERPT:
        raise AIError(f"طول المقتطف غير مقبول ({len(excerpt)})")
    if excerpt not in text:
        # قد يكون Groq غيّر الفراغات فقط؛ نقبل المقارنة بعد توحيدها لا غير
        if excerpt not in _norm_ws(text):
            raise AIError("المقتطف ليس حرفيًا من التفسير — مرفوض")
    return {"index": idx, "token": toks[idx], "excerpt": excerpt, "source_id": sid, "source_label": label}


def review(word, excerpt, verse, label):
    d = _chat([
        {"role": "system", "content": "You are a strict Arabic and Quran reviewer. One JSON object only."},
        {"role": "user", "content": f"""Word: {word}
Ayah: {verse}
Excerpt from {label}: {excerpt}
Does this excerpt genuinely explain the meaning of THIS word (or its direct meaning in this ayah) - not merely the general topic of the ayah? Be strict.
JSON: {{"ok": true|false, "reason": "short"}}"""}], temperature=0)
    return bool(d.get("ok")), str(d.get("reason") or "")
