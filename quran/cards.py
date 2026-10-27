"""cards.py — ثلاث بطاقات 1080x1920 بخط مصحفي (Amiri Quran) وتشكيل سليم عبر raqm: الكلمة ← الشرح ← الآية مع إبراز الكلمة."""
import math
import os

from PIL import Image, ImageDraw, ImageFont, features

from . import config
from . import quran_api as qa

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(BASE_DIR, "assets", "fonts")
W, H = config.W, config.H
GOLD, CREAM, DEEP = (222, 184, 98), (250, 244, 228), (6, 44, 40)
KW = {"direction": "rtl", "language": "ar"}


def require_raqm():
    if not features.check("raqm"):
        raise RuntimeError("Pillow بلا raqm: رسم التشكيل القرآني سيكون خاطئًا. ثبّت libraqm0 (sudo apt-get install libraqm0).")


def _font(names, size):
    cands = [os.path.join(FONT_DIR, n) for n in names] + [
        "/usr/share/fonts/truetype/fonts-hosny-amiri/AmiriQuran.ttf", "/usr/share/fonts/truetype/fonts-hosny-amiri/Amiri-Regular.ttf"]
    for p in cands:
        if os.path.exists(p):
            return ImageFont.truetype(p, size, layout_engine=ImageFont.Layout.RAQM)
    raise RuntimeError("الخطوط غير موجودة في assets/fonts (AmiriQuran-Regular.ttf, Amiri-Bold.ttf, Amiri-Regular.ttf)")


def quran_font(size):
    return _font(["AmiriQuran-Regular.ttf"], size)


def bold(size):
    return _font(["Amiri-Bold.ttf"], size)


def regular(size):
    return _font(["Amiri-Regular.ttf"], size)


def tw(d, text, f):
    return d.textlength(text, font=f, **KW)


def put_center(d, y, text, f, fill, cx=W / 2):
    d.text((cx - tw(d, text, f) / 2, y), text, font=f, fill=fill, **KW)


def fit_font(d, text, maker, max_w, start, minimum):
    for s in range(start, minimum - 1, -4):
        f = maker(s)
        if tw(d, text, f) <= max_w:
            return f
    return maker(minimum)


def wrap(d, tokens, f, max_w):
    space = tw(d, " ", f) or f.size * 0.25
    lines, cur, cur_w = [], [], 0.0
    for t in tokens:
        w = tw(d, t, f)
        add = w + (space if cur else 0)
        if cur and cur_w + add > max_w:
            lines.append((cur, cur_w))
            cur, cur_w = [t], w
        else:
            cur.append(t)
            cur_w += add
    if cur:
        lines.append((cur, cur_w))
    return lines, space


def background():
    top, bottom = (9, 66, 58), (3, 22, 28)
    img = Image.new("RGB", (W, H))
    px = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        px.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    img = img.convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    s = 150
    for gy in range(-1, H // s + 2):
        for gx in range(-1, W // s + 2):
            cx, cy = gx * s + (s / 2 if gy % 2 else 0), gy * s
            r = s * 0.36
            for rot in (0, math.pi / 4):
                pts = [(cx + r * math.cos(rot + k * math.pi / 2 + math.pi / 4), cy + r * math.sin(rot + k * math.pi / 2 + math.pi / 4)) for k in range(4)]
                d.polygon(pts, outline=(222, 184, 98, 26))
            d.ellipse([cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55], outline=(222, 184, 98, 16))
    img = Image.alpha_composite(img, ov)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([46, 46, W - 46, H - 46], radius=36, outline=GOLD + (170,), width=3)
    d.rounded_rectangle([62, 62, W - 62, H - 62], radius=28, outline=GOLD + (70,), width=2)
    return img


def header(img, text="كلمة من القرآن"):
    d = ImageDraw.Draw(img)
    f = bold(66)
    w = tw(d, text, f)
    put_center(d, 150, text, f, GOLD)
    for sgn in (-1, 1):
        x0 = W / 2 + sgn * (w / 2 + 40)
        d.line([x0, 195, x0 + sgn * 150, 195], fill=GOLD + (150,), width=3)
        d.ellipse([x0 + sgn * 160 - 6, 189, x0 + sgn * 160 + 6, 201], fill=GOLD)


def footer(img, ctx):
    d = ImageDraw.Draw(img)
    ref = f"سورة {ctx['surah_name']} — الآية {qa.ar_num(ctx['ayah'])}"
    put_center(d, 1640, ref, fit_font(d, ref, bold, 900, 60, 36), CREAM)
    if ctx.get("range_note"):
        put_center(d, 1720, ctx["range_note"], regular(40), CREAM + (190,))
    if ctx.get("reciter"):
        put_center(d, 1780, f"التلاوة: {ctx['reciter']}", regular(40), GOLD)


def _card(img, box, alpha=26):
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.rounded_rectangle(box, radius=48, fill=(255, 255, 255, alpha), outline=GOLD + (200,), width=4)
    img.alpha_composite(ov)


def scene_word(ctx):
    img = background()
    header(img)
    _card(img, [90, 520, W - 90, 1120])
    d = ImageDraw.Draw(img)
    f = fit_font(d, ctx["token"], quran_font, W - 300, 230, 90)
    put_center(d, 820 - f.size * 0.62, ctx["token"], f, CREAM)
    put_center(d, 1240, "ما معناها؟", bold(86), GOLD)
    footer(img, ctx)
    return img


def scene_meaning(ctx):
    img = background()
    header(img)
    d = ImageDraw.Draw(img)
    put_center(d, 255, ctx["token"], fit_font(d, ctx["token"], quran_font, 700, 120, 70), GOLD)
    _card(img, [80, 520, W - 80, 1360])
    d = ImageDraw.Draw(img)
    toks = ctx["excerpt"].split()
    for size in range(68, 40, -2):
        f = regular(size)
        lines, space = wrap(d, toks, f, W - 260)
        if len(lines) * f.size * 1.75 <= 640:
            break
    block = len(lines) * f.size * 1.75
    y = 520 + (840 - block) / 2 - 20
    for line, lw in lines:
        x = W / 2 + lw / 2
        for t in line:
            w = tw(d, t, f)
            d.text((x - w, y), t, font=f, fill=CREAM, **KW)
            x -= w + space
        y += f.size * 1.75
    d.text((W - 200, 540), "”", font=bold(190), fill=GOLD + (150,), **KW)
    src = "— " + ctx["source_label"]
    put_center(d, 1400, src, fit_font(d, src, regular, W - 200, 46, 30), GOLD)
    footer(img, ctx)
    return img


def scene_verse(ctx):
    img = background()
    header(img, "الآية الكريمة")
    d = ImageDraw.Draw(img)
    toks, idx = ctx["verse"].split(), ctx["index"]
    prefix = suffix = False
    if len(toks) > 46:                                               # آية طويلة: نافذة حول الكلمة
        lo, hi = max(0, idx - 16), min(len(toks), idx + 17)
        prefix, suffix = lo > 0, hi < len(toks)
        idx -= lo
        toks = toks[lo:hi]
    items = ([("…", False)] if prefix else []) + [(t, i == idx) for i, t in enumerate(toks)] + ([("…", False)] if suffix else [])
    # دمج علامات الوقف المنفردة مع الكلمة السابقة
    merged = []
    for t, hl in items:
        if merged and not qa.has_letters(t) and t != "…":
            merged[-1] = (merged[-1][0] + " " + t, merged[-1][1])
        else:
            merged.append((t, hl))
    area_w, area_h = W - 200, 1000
    for size in range(124, 44, -2):
        f = quran_font(size)
        lines, space = wrap(d, [t for t, _ in merged], f, area_w)
        lh = f.size * 1.9
        if len(lines) * lh <= area_h:
            break
    lh = f.size * 1.9
    block = len(lines) * lh
    y = 330 + (area_h + 80 - block) / 2
    k = 0
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    pos = []
    for line, lw in lines:
        x = W / 2 + lw / 2
        for t in line:
            w = tw(d, t, f)
            hl = merged[k][1]
            pos.append((t, x - w, y, w, hl))
            if hl:
                asc, desc = f.getmetrics()
                od.rounded_rectangle([x - w - 16, y + asc * 0.02, x + 16, y + asc + desc * 0.55], radius=24, fill=GOLD + (60,), outline=GOLD + (230,), width=3)
            x -= w + space
            k += 1
        y += lh
    img.alpha_composite(ov)
    d = ImageDraw.Draw(img)
    for t, x, yy, w, hl in pos:
        d.text((x, yy), t, font=f, fill=GOLD if hl else CREAM, **KW)
    footer(img, ctx)
    d = ImageDraw.Draw(img)
    put_center(d, 1860, "المصدر: Quran.com", regular(30), CREAM + (150,))
    return img


def render(ctx, out_dir):
    require_raqm()
    paths = []
    for name, fn in (("a_word", scene_word), ("b_meaning", scene_meaning), ("c_verse", scene_verse)):
        p = os.path.join(out_dir, name + ".png")
        fn(ctx).convert("RGB").save(p)
        paths.append(p)
    return paths
