"""
quran_api.py — مصادر موثوقة فقط: نص الآية (Quran.com ثم alquran.cloud)، اسم السورة، والتفسير المنقول حرفيًا.
لا يُولَّد أي نص قرآني أو تفسيري بالذكاء الاصطناعي في هذا المشروع.
"""
import html
import re
import time

import requests

from . import config

QCOM = "https://api.quran.com/api/v4"
CLOUD = "https://api.alquran.cloud/v1"
BASMALA_TOKENS = 4


class QuranError(RuntimeError):
    pass


def _get(url, params=None, retries=3):
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params, timeout=30, headers={"Accept": "application/json"})
            if r.status_code == 429 or r.status_code >= 500:
                last = f"HTTP {r.status_code}"
                time.sleep(3 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last = str(e)[:100]
            time.sleep(2)
    raise QuranError(f"{url}: {last}")


def clean(text):
    t = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", t).strip()


def chapter(surah):
    """(اسم السورة بالعربية، عدد آياتها)."""
    try:
        c = _get(f"{QCOM}/chapters/{surah}", {"language": "ar"})["chapter"]
        return c["name_arabic"], int(c["verses_count"])
    except (QuranError, KeyError, TypeError, ValueError):
        d = _get(f"{CLOUD}/surah/{surah}/quran-uthmani")["data"]
        return re.sub(r"^سُورَةُ\s*", "", d["name"]).strip(), int(d["numberOfAyahs"])


def verse_text(surah, ayah):
    """نص الآية بالرسم العثماني."""
    try:
        t = _get(f"{QCOM}/verses/by_key/{surah}:{ayah}", {"fields": "text_uthmani"})["verse"]["text_uthmani"]
        if t and t.strip():
            return t.strip()
    except (QuranError, KeyError, TypeError):
        pass
    t = _get(f"{CLOUD}/ayah/{surah}:{ayah}/quran-uthmani")["data"]["text"].strip()
    if ayah == 1 and surah not in (1, 9):                 # alquran.cloud يضيف البسملة لأول آية
        parts = t.split()
        if len(parts) > BASMALA_TOKENS and "بِسْمِ" in parts[0]:
            t = " ".join(parts[BASMALA_TOKENS:])
    return t


def tafsirs(surah, ayah):
    """قائمة (معرّف، اسم المصدر، النص) بحسب الأفضلية؛ النص كما ورد دون تعديل سوى إزالة الوسوم."""
    out = []
    for ed in ("ar.muyassar", "ar.jalalayn"):
        try:
            d = _get(f"{CLOUD}/ayah/{surah}:{ayah}/{ed}")["data"]
            text = clean(d.get("text", ""))
            if len(text) >= 15:
                out.append((ed, config.SOURCES[ed], text))
        except (QuranError, KeyError, TypeError):
            continue
    return out


# ------------------------------------------------------------ أدوات النص العربي
_MARKS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭ࣓-ࣿـ]")
_AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def bare(s):
    s = _MARKS.sub("", s).replace("ٱ", "ا").replace("ى", "ي").replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    return re.sub(r"[^ء-ي]", "", s)


def has_letters(token):
    return bool(bare(token))


def ar_num(n):
    return str(n).translate(_AR_DIGITS)
