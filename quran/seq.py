"""
seq.py — «التلاوة المتتابعة»: آية واحدة في كل فيديو، من أول المصحف إلى آخره ثم تبدأ ختمة جديدة.
  • الصوت: تلاوة الشيخ عبد الرحمن السديس (everyayah.com) — آية بآية، فالنص والصوت متطابقان دائمًا.
  • آية تتجاوز الحد الأقصى للمدة تُتخطّى نهائيًا وننتقل إلى التالية (تُسجَّل في state["qseq"]["skipped_list"]).
  • فشل التنزيل (شبكة) لا يُعدّ تخطيًا: يُرفع خطأ فيحلّ المنشور الاحتياطي ولا يتحرك المؤشر.
  • المؤشر يُحفظ في state["qseq"] ولا يتقدّم إلا بعد نجاح النشر (المنسّق يحفظ الحالة بعده).
"""
import os
import subprocess

from PIL import Image, ImageDraw

from . import audio_pick as ap
from . import cards as C
from . import config
from . import quran_api as qa
from .media import duration
from .post import Post

# عدد آيات كل سورة (بنية ثابتة للمصحف، لا محتوى) — يُتحقق من المجموع 6236 عند الاستيراد
COUNTS = [7, 286, 200, 176, 120, 165, 206, 75, 129, 109, 123, 111, 43, 52, 99, 128, 111, 110, 98, 135, 112, 78, 118, 64, 77,
          227, 93, 88, 69, 60, 34, 30, 73, 54, 45, 83, 182, 88, 75, 85, 54, 53, 89, 59, 37, 35, 38, 29, 18, 45, 60, 49, 62,
          55, 78, 96, 29, 22, 24, 13, 14, 11, 11, 18, 12, 12, 30, 52, 52, 44, 28, 28, 20, 56, 40, 31, 50, 40, 46, 42, 29,
          19, 36, 25, 22, 17, 19, 26, 30, 20, 15, 21, 11, 8, 8, 19, 5, 8, 8, 11, 11, 8, 3, 9, 5, 4, 7, 3, 6, 3, 5, 4, 5, 6]
assert len(COUNTS) == 114 and sum(COUNTS) == 6236, "جدول عدد الآيات غير صحيح"

HARD_LIMIT = config.HARD_LIMIT          # 58.5 ثانية — لا يُتجاوز أبدًا
LEAD, TAIL, MIN_TOTAL = 0.45, 1.4, 9.0
MAX_SKIPS = 12
RECITER = os.environ.get("SEQ_RECITER", "sudais").strip().lower()


def advance(s, a):
    """الآية التالية (سورة، آية، هل لففنا حول المصحف؟)."""
    if a < COUNTS[s - 1]:
        return s, a + 1, False
    if s < 114:
        return s + 1, 1, False
    return 1, 1, True


def position(s, a):
    """ترتيب الآية في المصحف (1..6236)."""
    return sum(COUNTS[:s - 1]) + a


def _draw_verse(img, text, top, bottom):
    d = ImageDraw.Draw(img)
    toks, merged = text.split(), []
    for t in toks:                                         # دمج علامات الوقف المنفردة مع ما قبلها
        if merged and not qa.has_letters(t):
            merged[-1] += " " + t
        else:
            merged.append(t)
    area_w, area_h = C.W - 190, bottom - top
    for size in range(120, 33, -2):
        f = C.quran_font(size)
        lines, space = C.wrap(d, merged, f, area_w)
        lh = f.size * 1.85
        if len(lines) * lh <= area_h:
            break
    block = len(lines) * lh
    y = top + (area_h - block) / 2
    for line, lw in lines:
        x = C.W / 2 + lw / 2
        for t in line:
            w = C.tw(d, t, f)
            d.text((x - w, y), t, font=f, fill=C.CREAM, **C.KW)
            x -= w + space
        y += lh


def scene(ctx):
    img = C.background()
    C.header(img, "القرآن الكريم")
    d = ImageDraw.Draw(img)
    name = "سورة " + ctx["surah_name"]
    C.put_center(d, 255, name, C.fit_font(d, name, C.bold, 820, 100, 56), C.GOLD)
    C._card(img, [70, 430, C.W - 70, 1590], alpha=20)
    _draw_verse(img, ctx["verse"], 490, 1515)
    d = ImageDraw.Draw(img)
    ref = f"الآية {qa.ar_num(ctx['ayah'])} من {qa.ar_num(ctx['n_ayahs'])}"
    C.put_center(d, 1630, ref, C.bold(54), C.CREAM)
    C.put_center(d, 1710, f"التلاوة: {ctx['reciter']}", C.regular(42), C.GOLD)
    # شريط التقدم في المصحف
    x0, x1, y = 190, C.W - 190, 1786
    frac = ctx["pos"] / 6236
    d.rounded_rectangle([x0, y, x1, y + 12], radius=6, fill=(52, 84, 76))
    d.rounded_rectangle([x0, y, x0 + max(14, (x1 - x0) * frac), y + 12], radius=6, fill=C.GOLD)
    label = f"التقدم في المصحف {qa.ar_num(int(frac * 100))}٪" + (f" — الختمة {qa.ar_num(ctx['cycle'])}" if ctx["cycle"] > 1 else "")
    C.put_center(d, 1806, label, C.regular(30), C.CREAM + (170,))
    return img


def _build_video(image, clip_path, out_path):
    dur = duration(clip_path)
    total = min(max(dur + LEAD + TAIL, MIN_TOTAL), HARD_LIMIT)
    ms = int(LEAD * 1000)
    fo = max(0.5, min(1.2, dur - 0.5))
    zoom = (f"scale=1620:2880,zoompan=z='1+0.035*on/{int(total * config.FPS)}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:"
            f"s={config.W}x{config.H}:fps={config.FPS},format=yuv420p,fade=t=in:st=0:d=0.5,fade=t=out:st={total - 0.7:.3f}:d=0.7[v]")
    g = [f"[0:v]{zoom}",
         f"[1:a]aresample=44100,aformat=channel_layouts=stereo,loudnorm=I=-16:TP=-1.5:LRA=9,"
         f"afade=t=in:d=0.35,afade=t=out:st={max(0.0, dur - fo):.3f}:d={fo:.3f},adelay={ms}|{ms},apad=whole_dur={total:.3f}[a]"]
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(config.FPS), "-loop", "1", "-t", f"{total:.3f}", "-i", image,
           "-i", clip_path, "-filter_complex", ";".join(g), "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-movflags", "+faststart", out_path]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed:\n{e.stderr[-1200:]}") from e
    return total


def build(st, out_dir):
    """يبني منشور الآية التالية في التتابع ويحرّك المؤشر داخل st (الذي يحفظه المنسّق بعد النجاح فقط)."""
    C.require_raqm()
    q = st.setdefault("qseq", {})
    q.setdefault("surah", 1), q.setdefault("ayah", 1), q.setdefault("cycle", 1)
    q.setdefault("done", 0), q.setdefault("skipped", 0), q.setdefault("skipped_list", [])
    s, a = q["surah"], q["ayah"]
    if not (1 <= s <= 114 and 1 <= a <= COUNTS[s - 1]):          # حالة تالفة → نبدأ من أول المصحف
        s, a = 1, 1
    cycle, skipped = q["cycle"], []
    clip = None
    for _ in range(MAX_SKIPS + 1):
        path, dur, rname = ap.download_ayah(s, a, RECITER)         # AudioError ← يتحول لمنشور احتياطي
        if dur <= config.MAX_CLIP:
            clip = (path, dur, rname)
            break
        print(f"   ⏭ {s}:{a} مدتها {dur:.1f}ث > {config.MAX_CLIP:.0f}ث — نتخطاها")
        skipped.append(f"{s}:{a}")
        s, a, wrapped = advance(s, a)
        cycle += wrapped
    if not clip:
        raise RuntimeError(f"تجاوزنا {MAX_SKIPS} آيات طويلة متتالية — غير متوقع")
    path, dur, rname = clip
    surah_name, _ = qa.chapter(s)
    verse = qa.verse_text(s, a)
    ctx = {"surah": s, "ayah": a, "surah_name": surah_name, "verse": verse, "n_ayahs": COUNTS[s - 1],
           "reciter": rname, "pos": position(s, a), "cycle": cycle}
    os.makedirs(out_dir, exist_ok=True)
    img_path = os.path.join(out_dir, f"qseq_{s}_{a}.png")
    scene(ctx).convert("RGB").save(img_path)
    out = os.path.join(out_dir, f"qseq_{s:03d}_{a:03d}.mp4")
    total = _build_video(img_path, path, out)
    os.remove(img_path)
    ns, na, wrapped = advance(s, a)
    q.update({"surah": ns, "ayah": na, "cycle": cycle + wrapped, "done": q["done"] + 1,
              "skipped": q["skipped"] + len(skipped), "skipped_list": (q["skipped_list"] + skipped)[-200:]})
    ref = f"سورة {surah_name} — الآية {qa.ar_num(a)}"
    title = f"{surah_name} — الآية {qa.ar_num(a)} | تلاوة {rname.replace('الشيخ ', '')} #shorts"
    if len(title) > 100:
        title = f"{surah_name} {qa.ar_num(a)} #shorts"
    caption = f"﴿ {verse} ﴾\n({ref})\n\n🎙️ {rname}\n\n#القرآن_الكريم #تلاوة #قرآن #shorts"
    desc = (caption + f"\n\n📖 تلاوة متتابعة من أول المصحف آيةً بآية (الآية {qa.ar_num(position(s, a))} من ٦٢٣٦).\n"
            "📚 نص الآية: Quran.com — 🔊 الصوت: everyayah.com")
    print(f"   ✓ {s}:{a} — {total:.1f}ث — التالي {ns}:{na}" + (f" — متخطّاة {skipped}" if skipped else ""))
    return Post(out, title, desc, caption, ["القرآن الكريم", "تلاوة", surah_name, "shorts"], label=f"seq {s}:{a}")
