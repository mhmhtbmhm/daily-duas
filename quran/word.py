"""word.py — «كلمة من القرآن»: آية عشوائية بصوت قارئ ← Groq يختار الكلمة وجملة شرح حرفية من التفسير ← فيديو."""
import os
import random
import tempfile
from types import SimpleNamespace

from . import ai
from . import audio_pick as ap
from . import cards
from . import config
from . import quran_api as qa
from . import video
from .post import Post

RECITER = os.environ.get("WORD_RECITER", "alafasy").strip().lower()
MAX_TRIES = 10


def _context(clip, used):
    surah_name, n_verses = qa.chapter(clip["surah"])
    if clip["a2"] > n_verses:
        raise ai.AIError(f"الآية {clip['a2']} خارج السورة ({n_verses})")
    key = f"{clip['surah']}:{clip['a1']}"
    verse = qa.verse_text(clip["surah"], clip["a1"])
    tafs = qa.tafsirs(clip["surah"], clip["a1"])
    if not tafs:
        raise ai.AIError(f"لا تفسير متاح لـ {key}")
    taken = [int(u.rsplit(":", 1)[1]) for u in used if u.startswith(key + ":")]
    w = ai.pick_word(surah_name, clip["surah"], clip["a1"], verse, tafs, avoid_idx=taken)
    ok, why = ai.review(w["token"], w["excerpt"], verse, w["source_label"])
    if not ok:
        raise ai.AIError(f"المراجعة رفضت الشرح ({why})")
    return {"surah": clip["surah"], "ayah": clip["a1"], "surah_name": surah_name, "verse": verse, "index": w["index"],
            "token": w["token"], "excerpt": w["excerpt"], "source_label": w["source_label"],
            "reciter": clip["reciter"], "range_note": ""}


def _meta(ctx):
    ref = f"سورة {ctx['surah_name']} — الآية {qa.ar_num(ctx['ayah'])}"
    title = f"معنى «{ctx['token']}» في القرآن | {ctx['surah_name']} {qa.ar_num(ctx['ayah'])} #shorts"
    if len(title) > 100:
        title = f"معنى «{ctx['token']}» في القرآن #shorts"
    short = (f"📖 كلمة «{ctx['token']}»\n\n💡 {ctx['excerpt']}\n— {ctx['source_label']}\n\n﴿ {ctx['verse']} ﴾\n({ref})\n"
             f"🎙️ {ctx['reciter']}\n\n#القرآن_الكريم #معاني_القرآن #تفسير #كلمة_من_القرآن #shorts")
    desc = short + f"\n\n{config.DISCLAIMER}\n📚 نص الآية: Quran.com — 🔊 الصوت: everyayah.com"
    return title, desc, short


def build(st, out_dir):
    cards.require_raqm()
    used = st.setdefault("qw_used", [])
    recent = {u.rsplit(":", 1)[0] for u in used[-3000:]}
    tried, last = set(), "لا محاولات"
    os.makedirs(out_dir, exist_ok=True)
    for _ in range(MAX_TRIES):
        s, a = ap.online_candidate(recent, tried)
        tried.add(f"{s}:{a}")
        clip = ap.online_clip(s, a, config.MAX_CLIP, config.MIN_CLIP, reciter=RECITER)
        if not clip:
            continue
        print(f"   الآية: {s}:{a} ({clip['dur']:.1f}s)")
        try:
            ctx = _context(clip, used)
        except (ai.AIError, qa.QuranError) as e:
            last = f"{s}:{a}: {e}"
            print("   ↺", last)
            continue
        print(f"   الكلمة: {ctx['token']} — {ctx['source_label']}\n   الشرح: {ctx['excerpt']}")
        out = os.path.join(out_dir, f"qword_{s}_{a}.mp4")
        with tempfile.TemporaryDirectory(prefix="qw_") as tmp:
            images = cards.render(ctx, tmp)
            plan = video.build(images, clip["path"], out, len(ctx["excerpt"]))
        used.append(f"{s}:{a}:{ctx['index']}")
        del used[:-3000]
        title, desc, short = _meta(ctx)
        print(f"   ✓ فيديو {plan['total']:.1f}ث")
        return Post(out, title, desc, short, config.BASE_TAGS + [ctx["surah_name"], ctx["token"]], label=f"word {ctx['token']}")
    raise RuntimeError(f"لم تنجح كلمة القرآن بعد {MAX_TRIES} محاولات: {last}")
