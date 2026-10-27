"""
audio_pick.py — اختيار مقطع تلاوة عشوائي من assets/audio وربطه بالآية.
اسم الملف يحدد الآية:  002_255.mp3  أو  2-255.mp3  أو  002255.mp3  أو  002_255-257.mp3  (سورة_آية[-آخر آية])
أو ملف assets/audio/manifest.json:  {"أي_اسم.mp3": "2:255"}  أو  {"x.mp3": {"ref": "2:255-257", "reciter": "اسم القارئ"}}
"""
import json
import os
import random
import re
import subprocess
import tempfile
import time

import requests

from .media import duration

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.environ.get("AUDIO_DIR") or os.path.join(BASE_DIR, "assets", "audio")
EXTS = (".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac", ".opus")


def parse_ref(text):
    """يرجع (سورة، آية_من، آية_إلى) أو None."""
    t = str(text).strip()
    m = re.fullmatch(r"\s*(\d{1,3})\s*[:_\-. ]\s*(\d{1,3})(?:\s*[-_–]\s*(\d{1,3}))?\s*", t)
    if m:
        s, a, b = int(m.group(1)), int(m.group(2)), int(m.group(3) or m.group(2))
    else:
        stem = os.path.splitext(os.path.basename(t))[0]
        six = re.findall(r"(?<!\d)(\d{6})(?!\d)", stem)
        if six:
            s, a, b = int(six[0][:3]), int(six[0][3:]), int(six[0][3:])
        else:
            nums = [int(x) for x in re.findall(r"\d+", stem)]
            if len(nums) == 2:
                s, a, b = nums[0], nums[1], nums[1]
            elif len(nums) == 3 and nums[2] >= nums[1]:
                s, a, b = nums
            else:
                return None
    if not (1 <= s <= 114 and 1 <= a <= 286 and b >= a):
        return None
    return s, a, b


def scan():
    """يرجع (clips, problems): clips = قائمة {file, path, surah, a1, a2, reciter}."""
    manifest = {}
    mp = os.path.join(AUDIO_DIR, "manifest.json")
    if os.path.exists(mp):
        with open(mp, encoding="utf-8") as f:
            manifest = json.load(f)
    clips, problems = [], []
    if not os.path.isdir(AUDIO_DIR):
        return clips, ["مجلد الصوت غير موجود: " + AUDIO_DIR]
    for name in sorted(os.listdir(AUDIO_DIR)):
        if not name.lower().endswith(EXTS):
            continue
        entry = manifest.get(name)
        reciter = ""
        if isinstance(entry, dict):
            reciter, entry = entry.get("reciter", ""), entry.get("ref")
        ref = parse_ref(entry) if entry else parse_ref(name)
        if not ref:
            problems.append(f"{name}: اسم غير مفهوم (استعمل 002_255.mp3 أو manifest.json)")
            continue
        path = os.path.join(AUDIO_DIR, name)
        try:
            dur = duration(path)
        except Exception as e:                                       # noqa: BLE001
            problems.append(f"{name}: ملف غير قابل للقراءة ({str(e)[:50]})")
            continue
        clips.append({"file": name, "path": path, "surah": ref[0], "a1": ref[1], "a2": ref[2], "dur": dur, "reciter": reciter})
    return clips, problems


def eligible(clips, min_dur, max_dur):
    return [c for c in clips if min_dur <= c["dur"] <= max_dur]


def choose(clips, used_files, forced=None):
    """مقطع عشوائي لم يُستعمل في الدورة الحالية؛ تُعاد الدورة عند نفاد المقاطع."""
    if forced:
        for c in clips:
            if c["file"] == forced:
                return c
        raise ValueError(f"المقطع غير موجود: {forced}")
    fresh = [c for c in clips if c["file"] not in set(used_files)]
    return random.choice(fresh or clips), not fresh


class AudioError(RuntimeError):
    """تعذّر تنزيل صوت الآية (شبكة/ملف غير موجود) — يختلف عن كون الآية أطول من الحد."""


def _urls(folder, num):
    return [f"https://everyayah.com/data/{folder}/{num}.mp3",
            f"https://mirrors.quranicaudio.com/everyayah/{folder}/{num}.mp3"]


def download_ayah(surah, ayah, reciter=None, retries=3):
    """ينزّل تلاوة آية واحدة. يرجع (مسار، مدة، اسم القارئ) أو يرفع AudioError."""
    from . import config
    folder, name = config.ONLINE_RECITERS.get(reciter or config.ONLINE_RECITER, config.ONLINE_RECITERS["sudais"])
    num = f"{surah:03d}{ayah:03d}"
    d = tempfile.mkdtemp(prefix="qa_")
    path = os.path.join(d, num + ".mp3")
    last = "?"
    for attempt in range(retries):
        for u in _urls(folder, num):
            try:
                r = requests.get(u, timeout=40)
                if r.status_code == 200 and len(r.content) > 2000:
                    with open(path, "wb") as f:
                        f.write(r.content)
                    dur = duration(path)
                    if dur > 0.5:
                        return path, dur, name
                    last = "ملف صوت فارغ"
                else:
                    last = f"HTTP {r.status_code}"
            except (requests.RequestException, OSError, ValueError, subprocess.CalledProcessError) as e:
                last = str(e)[:80]
        time.sleep(3 * (attempt + 1))
    raise AudioError(f"تعذّر تنزيل {surah}:{ayah} — {last}")


def online_candidate(used_keys, tried, forced_ref=None):
    """آية عشوائية (سورة عشوائية ثم آية عشوائية) لم تُستعمل حديثًا ولم نجرّبها الآن. يرجع (سورة، آية)."""
    from . import quran_api as qa
    if forced_ref:
        s, a = (int(x) for x in forced_ref.split(":")[:2])
        return s, a
    for _ in range(60):
        s = random.randint(1, 114)
        a = random.randint(1, qa.chapter(s)[1])
        key = f"{s}:{a}"
        if key not in tried and key not in used_keys:
            return s, a
    s = random.randint(1, 114)
    return s, random.randint(1, qa.chapter(s)[1])


def online_clip(surah, ayah, max_dur, min_dur=3.0, reciter=None):
    """clip لآية واحدة من الإنترنت ضمن حد المدة، أو None."""
    try:
        path, dur, name = download_ayah(surah, ayah, reciter)
    except AudioError as e:
        print("   ⚠", e)
        return None
    if not (min_dur <= dur <= max_dur):
        print(f"   ⏭ {surah}:{ayah} مدتها {dur:.1f}ث خارج الحد ({min_dur:.0f}-{max_dur:.0f})")
        return None
    return {"file": os.path.basename(path), "path": path, "surah": surah, "a1": ayah, "a2": ayah, "dur": dur, "reciter": name}
