"""
publish.py — منسّق النشر اليومي (3 فترات) على Facebook / Instagram / YouTube.

  morning   : دعاء/حديث (state: index_morning) — صوت من assets/audio بالتناوب
  afternoon : «كلمة من القرآن» (Groq + تفسير موثّق + تلاوة)         ← احتياطيًا: دعاء الظهر
  evening   : التلاوة المتتابعة من أول المصحف بصوت السديس (آية/فيديو) ← احتياطيًا: دعاء المساء

ضمانات الاستمرارية:
  • لا يتحرك أي مؤشر (دعاء/آية/كلمة) إلا بعد نجاح النشر على منصة واحدة على الأقل.
  • فشل مسار المحتوى الأساسي يعني تلقائيًا الدعاء الاحتياطي، فلا تمرّ فترة بلا منشور.
  • حماية من التكرار: فترة نُشرت اليوم تُتخطّى (cron-job.org + جدولة GitHub الاحتياطية لا يتعارضان).
  • كل فيديو يُفحص بـ ffprobe: لا يُنشر ما يتجاوز 59 ثانية.
  • دفع state.json يعيد المحاولة مع pull --rebase.
تجربة محلية:  python publish.py --slot evening --dry --save-state
"""
import glob
import os
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

from generate_video import generate_dua_video

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DUAS_PATH = os.path.join(BASE_DIR, "duas.json")
STATE_PATH = os.path.join(BASE_DIR, "state.json")
POSTS_DIR = os.path.join(BASE_DIR, "posts")

# مجلد الملفات الصوتية المتعددة. أي عدد من الملفات يعمل (ليس شرطا 100) —
# يُقرأ المجلد تلقائيا في كل تشغيل، فإضافة/حذف ملف لا يحتاج أي تعديل كود.
# صيغ مقبولة: mp3, m4a, wav, ogg.
AUDIO_DIR = os.path.join(BASE_DIR, "assets", "audio")
AUDIO_EXTENSIONS = ("*.mp3", "*.m4a", "*.wav", "*.ogg")

# اسم الـ tag الثابت للـ Release المستعمل كمخزن مؤقت للفيديوهات.
# نستعمل Release واحد دائم (بدل واحد جديد كل مرة) ونحذف منه الـ assets
# القديمة تلقائيا، بدل ما ننشئ عشرات الـ Releases بمرور الوقت.
MEDIA_RELEASE_TAG = "media-storage"

# عدد الأيام التي يبقى فيها الفيديو متاحا كـ Release asset قبل حذفه تلقائيا.
ASSET_RETENTION_DAYS = int(os.environ.get("VIDEO_RETENTION_DAYS", "3"))

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# --- إعدادات تُقرأ من GitHub Secrets (متغيرات البيئة) ---
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN")
IG_USER_ID = os.environ.get("IG_USER_ID")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
# التوكن المستعمل لنداءات GitHub REST API (رفع/حذف release assets).
# نفس secrets.GITHUB_TOKEN الافتراضي الذي يمرره الـ workflow يكفي، بشرط أن
# يكون عند الـ workflow صلاحية "contents: write" (موجودة أصلا في ملف الـ yml).
GITHUB_API_TOKEN = os.environ.get("GITHUB_TOKEN")

# الفترة الحالية: تُمرَّر من GitHub Actions (morning/afternoon/evening)
SLOT = os.environ.get("DUA_SLOT", "general")

GH_API_BASE = "https://api.github.com"


def _gh_headers():
    if not GITHUB_API_TOKEN:
        raise RuntimeError("GITHUB_TOKEN environment variable is missing (مطلوب لرفع الفيديو كـ Release asset)")
    return {
        "Authorization": f"Bearer {GITHUB_API_TOKEN}",
        "Accept": "application/vnd.github+json",
    }


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def pick_next_dua(duas, state, category):
    """يختار الدعاء التالي في الفئة المطلوبة بالتناوب (round-robin) بلا تكرار متتالي."""
    candidates = [d for d in duas if d["category"] == category]
    if not candidates:
        candidates = duas  # fallback

    key = f"index_{category}"
    idx = state.get(key, 0) % len(candidates)
    dua = candidates[idx]
    state[key] = (idx + 1) % len(candidates)
    return dua


def pick_next_audio(state):
    """
    يختار الملف الصوتي التالي بالتناوب (round-robin) من مجلد assets/audio/،
    بنفس منطق pick_next_dua بالضبط. يدعم أي عدد من الملفات (10، 50، 100،
    200...) بلا أي تعديل كود — فقط أضف/احذف ملفات من المجلد.

    الترتيب يعتمد على الترتيب الأبجدي لأسماء الملفات، لذا يُفضَّل تسميتها
    بأرقام مرتبة (audio_001.mp3, audio_002.mp3, ...) لضمان تناوب متوقع
    وثابت عبر التشغيلات.
    """
    audio_files = []
    for pattern in AUDIO_EXTENSIONS:
        audio_files.extend(glob.glob(os.path.join(AUDIO_DIR, pattern)))
    audio_files = sorted(audio_files)

    if not audio_files:
        raise FileNotFoundError(
            f"لا توجد أي ملفات صوتية في {AUDIO_DIR}. "
            "أضف ملفا واحدا على الأقل (mp3/m4a/wav/ogg)."
        )

    key = "index_audio"
    idx = state.get(key, 0) % len(audio_files)
    chosen = audio_files[idx]
    state[key] = (idx + 1) % len(audio_files)
    return chosen


def _git(*args, check=False):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=check)


def git_commit_and_push(filepaths, message, tries=5):
    """commit + push مع إعادة محاولة (pull --rebase) عند تعارض الدفع. يرجع True عند النجاح، ولا يرفع استثناءً."""
    _git("config", "user.name", "daily-duas-bot")
    _git("config", "user.email", "bot@users.noreply.github.com")
    _git("add", *filepaths)
    r = _git("commit", "-m", message)
    if r.returncode != 0:
        if "nothing to commit" in (r.stdout + r.stderr):
            return True
        print("⚠️  git commit:", r.stdout, r.stderr)
        return False
    for i in range(1, tries + 1):
        if _git("push").returncode == 0:
            return True
        print(f"⚠️  git push فشل (محاولة {i}/{tries}) — نعيد المزامنة")
        _git("pull", "--rebase", "--autostash")
        time.sleep(4 * i)
    print("❌ تعذّر دفع state.json — الخطوة الأخيرة في الـ workflow ستعيد المحاولة", file=sys.stderr)
    return False


def _log_response_error(prefix, resp):
    """يطبع تفاصيل الخطأ الكاملة (error.message, code, subcode إن وُجدت)."""
    try:
        payload = resp.json()
    except ValueError:
        payload = resp.text
    print(f"❌ {prefix} — status={resp.status_code} body={payload}", file=sys.stderr)


# ==================== GitHub Releases كمخزن دائم ومجاني للفيديو ====================

def get_or_create_media_release():
    """
    يجيب الـ Release الثابت (media-storage) إن كان موجودا، أو ينشئه أول مرة.
    هذا الـ Release ليس إصدارا برمجيا حقيقيا للمشروع — هو فقط حاوية تقنية
    لتخزين الفيديوهات المؤقتة والحصول على رابط عمومي لها بلا أي تأثير على
    تاريخ Git أو حجم الريبو.
    """
    url = f"{GH_API_BASE}/repos/{GITHUB_REPOSITORY}/releases/tags/{MEDIA_RELEASE_TAG}"
    resp = requests.get(url, headers=_gh_headers(), timeout=15)
    if resp.status_code == 200:
        return resp.json()

    if resp.status_code != 404:
        _log_response_error("GitHub get release", resp)
        resp.raise_for_status()

    create_url = f"{GH_API_BASE}/repos/{GITHUB_REPOSITORY}/releases"
    resp2 = requests.post(create_url, headers=_gh_headers(), json={
        "tag_name": MEDIA_RELEASE_TAG,
        "name": "Media Storage (auto-managed, do not edit)",
        "body": "مخزن مؤقت وتلقائي لفيديوهات الأدعية. يُدار بالكامل عبر publish.py.",
        "draft": False,
        "prerelease": True,
    }, timeout=15)
    if not resp2.ok:
        _log_response_error("GitHub create release", resp2)
    resp2.raise_for_status()
    return resp2.json()


def upload_video_asset(release, local_video_path):
    """يرفع الفيديو كـ asset مرفق بالـ Release، ويرجع رابطه العمومي المباشر."""
    filename = os.path.basename(local_video_path)
    upload_url = release["upload_url"].split("{")[0]  # إزالة query template {?name,label}
    headers = _gh_headers()
    headers["Content-Type"] = "video/mp4"

    with open(local_video_path, "rb") as f:
        resp = requests.post(
            upload_url,
            headers=headers,
            params={"name": filename},
            data=f,
            timeout=120,
        )
    if not resp.ok:
        _log_response_error("GitHub upload release asset", resp)
    resp.raise_for_status()
    asset = resp.json()
    return asset["browser_download_url"], asset["id"]


def cleanup_old_release_assets(release_id, retention_days=ASSET_RETENTION_DAYS):
    """
    يحذف الـ assets الأقدم من retention_days من الـ Release. هذا يبقي حجم
    الـ Release صغيرا للأبد، بلا أي تأثير على تاريخ Git أو حجم الريبو نفسه
    (الـ Release assets مخزنة بشكل منفصل تماما عن الـ git objects).
    """
    url = f"{GH_API_BASE}/repos/{GITHUB_REPOSITORY}/releases/{release_id}/assets"
    resp = requests.get(url, headers=_gh_headers(), timeout=15)
    if not resp.ok:
        _log_response_error("GitHub list release assets", resp)
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted_count = 0
    for asset in resp.json():
        created_at = datetime.strptime(asset["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if created_at < cutoff:
            del_url = f"{GH_API_BASE}/repos/{GITHUB_REPOSITORY}/releases/assets/{asset['id']}"
            del_resp = requests.delete(del_url, headers=_gh_headers(), timeout=15)
            if del_resp.ok:
                deleted_count += 1
            else:
                _log_response_error(f"GitHub delete asset {asset['name']}", del_resp)

    if deleted_count:
        print(f"🧹 تم حذف {deleted_count} فيديو(هات) قديمة من مخزن الـ Release (أقدم من {retention_days} أيام)")


def wait_until_url_is_live(url, expected_content_prefix="video/", retries=10, delay=5):
    """نتأكد أن رابط الفيديو أصبح فعليا قابلا للوصول قبل إعطائه لـ Instagram."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=20, stream=True, allow_redirects=True)
            content_type = resp.headers.get("Content-Type", "")
            content_length = resp.headers.get("Content-Length", "0")
            ok_type = content_type.startswith(expected_content_prefix) or content_type == "application/octet-stream"
            if resp.status_code == 200 and ok_type and int(content_length) > 0:
                print(f"✅ الرابط جاهز (محاولة {attempt}): {content_type}, {content_length} bytes")
                return True
            print(f"⏳ محاولة {attempt}/{retries}: status={resp.status_code} content-type={content_type}")
        except requests.RequestException as e:
            print(f"⏳ محاولة {attempt}/{retries}: خطأ في الوصول للرابط: {e}")
        time.sleep(delay)
    print("⚠️  الرابط ما زال غير متجاوب بشكل صحيح بعد كل المحاولات، سنكمل رغم ذلك.")
    return False


# ==================== Facebook Reels ====================

def post_reel_to_facebook(local_video_path, caption, retries=3, delay=8):
    """
    نشر Reel على صفحة Facebook عبر endpoint /video_reels (3 خطوات رسمية من Meta):
    1) start  → الحصول على video_id ورابط الرفع (upload_url)
    2) رفع الفيديو (binary) لرابط الرفع
    3) finish → نشر الفيديو كـ Reel مع الوصف
    """
    last_exception = None
    for attempt in range(1, retries + 1):
        try:
            start_resp = requests.post(
                f"{GRAPH_BASE}/{FB_PAGE_ID}/video_reels",
                data={"upload_phase": "start", "access_token": FB_PAGE_TOKEN},
                timeout=30,
            )
            if not start_resp.ok:
                _log_response_error(f"Facebook video_reels start (محاولة {attempt}/{retries})", start_resp)
                start_resp.raise_for_status()
            start_data = start_resp.json()
            video_id = start_data["video_id"]
            upload_url = start_data["upload_url"]

            file_size = os.path.getsize(local_video_path)
            with open(local_video_path, "rb") as f:
                upload_resp = requests.post(
                    upload_url,
                    headers={
                        "Authorization": f"OAuth {FB_PAGE_TOKEN}",
                        "offset": "0",
                        "file_size": str(file_size),
                    },
                    data=f,
                    timeout=120,
                )
            if not upload_resp.ok:
                _log_response_error(f"Facebook video_reels upload (محاولة {attempt}/{retries})", upload_resp)
                upload_resp.raise_for_status()

            finish_resp = requests.post(
                f"{GRAPH_BASE}/{FB_PAGE_ID}/video_reels",
                data={
                    "upload_phase": "finish",
                    "video_id": video_id,
                    "video_state": "PUBLISHED",
                    "description": caption,
                    "access_token": FB_PAGE_TOKEN,
                },
                timeout=30,
            )
            if not finish_resp.ok:
                _log_response_error(f"Facebook video_reels finish (محاولة {attempt}/{retries})", finish_resp)
                finish_resp.raise_for_status()

            return finish_resp.json()

        except requests.HTTPError as e:
            last_exception = e
            if attempt < retries:
                time.sleep(delay * attempt)
                continue
            break

    raise last_exception


def post_video_to_facebook_fallback(local_video_path, caption, retries=3, delay=8):
    """
    مسار احتياطي: نشر كفيديو عادي على /{page-id}/videos (وليس Reel) إذا فشل
    /video_reels — على الأقل يخرج المحتوى بشكل ما بدل ما يفشل النشر كليا.
    """
    url = f"{GRAPH_BASE}/{FB_PAGE_ID}/videos"
    last_exception = None
    for attempt in range(1, retries + 1):
        with open(local_video_path, "rb") as f:
            files = {"source": (os.path.basename(local_video_path), f, "video/mp4")}
            data = {"description": caption, "access_token": FB_PAGE_TOKEN}
            resp = requests.post(url, data=data, files=files, timeout=120)
        if resp.ok:
            return resp.json()
        _log_response_error(f"Facebook /videos fallback (محاولة {attempt}/{retries})", resp)
        last_exception = requests.HTTPError(f"{resp.status_code} error on /videos", response=resp)
        if attempt < retries:
            time.sleep(delay * attempt)
    raise last_exception


def post_to_facebook(local_video_path, caption):
    """يجرب Reel أولا، وإذا فشل يجرب فيديو عادي كحل احتياطي."""
    try:
        result = post_reel_to_facebook(local_video_path, caption)
        print("   → نجح عبر: Facebook Reel")
        return result
    except Exception as e1:
        print(f"   ⚠️  فشل مسار Reel: {e1}")
        try:
            result = post_video_to_facebook_fallback(local_video_path, caption)
            print("   → نجح عبر: فيديو عادي (fallback)")
            return result
        except Exception as e2:
            raise RuntimeError(f"فشل النشر على Facebook (Reel و fallback):\n[Reel] {e1}\n[Video] {e2}")


# ==================== Instagram Reels ====================

def wait_for_ig_container_ready(creation_id, retries=20, delay=5):
    """
    Instagram يحتاج وقتا أطول لمعالجة الفيديو (مقارنة بالصورة) قبل قبول
    media_publish. نراقب status_code حتى يصبح FINISHED.
    """
    status_url = f"{GRAPH_BASE}/{creation_id}"
    for attempt in range(1, retries + 1):
        resp = requests.get(status_url, params={
            "fields": "status_code",
            "access_token": FB_PAGE_TOKEN,
        })
        if resp.ok:
            status = resp.json().get("status_code")
            print(f"⏳ Instagram container status (محاولة {attempt}/{retries}): {status}")
            if status == "FINISHED":
                return True
            if status == "ERROR":
                print("❌ Instagram container status = ERROR", file=sys.stderr)
                return False
        else:
            _log_response_error("Instagram status check", resp)
        time.sleep(delay)
    print("⚠️  الـ container ما زال IN_PROGRESS بعد كل المحاولات.")
    return False


def post_to_instagram(video_url, caption):
    """نشر Reel على Instagram عبر media_type=REELS."""
    create_url = f"{GRAPH_BASE}/{IG_USER_ID}/media"
    resp = requests.post(create_url, data={
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": FB_PAGE_TOKEN,
    })
    if not resp.ok:
        _log_response_error("Instagram /media (create REELS container)", resp)
    resp.raise_for_status()
    creation_id = resp.json()["id"]

    ready = wait_for_ig_container_ready(creation_id)
    if not ready:
        raise RuntimeError("Instagram container لم يصبح جاهزا (FINISHED) في الوقت المحدد")

    publish_url = f"{GRAPH_BASE}/{IG_USER_ID}/media_publish"
    resp2 = requests.post(publish_url, data={
        "creation_id": creation_id,
        "access_token": FB_PAGE_TOKEN,
    })
    if not resp2.ok:
        _log_response_error("Instagram /media_publish", resp2)
    resp2.raise_for_status()
    return resp2.json()



STATE_PATH = os.environ.get("STATE_PATH") or STATE_PATH
POSTS_DIR = os.environ.get("POSTS_DIR") or POSTS_DIR


# ==================== YouTube ====================

def post_to_youtube(post):
    import inspect
    from youtube_upload import upload_short
    kw = {"tags": post.tags}
    params = inspect.signature(upload_short).parameters         # نمرّر فقط ما يدعمه youtube_upload.py الحالي
    for k, v in (("privacy", os.environ.get("PRIVACY", "public")), ("language", "ar"), ("audio_language", "ar"),
                 ("made_for_kids", False)):
        if k in params:
            kw[k] = v
    return upload_short(post.video, title=post.title[:100], description=post.description[:4900], **kw)


# ==================== أدوات الاستمرارية ====================

MAX_SECONDS = 59.0           # سقف صارم لأي فيديو يُنشر


def retry(fn, tries=3, delay=20, what=""):
    last = None
    for i in range(1, tries + 1):
        try:
            return fn()
        except Exception as e:                                   # noqa: BLE001
            last = e
            print(f"   ↻ {what} فشل (محاولة {i}/{tries}): {str(e)[:200]}")
            if i < tries:
                time.sleep(delay * i)
    raise last


def assert_short(path):
    """يمنع نشر أي فيديو يتجاوز 59 ثانية أو لا يُقرأ."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=noprint_wrappers=1:nokey=1", path], capture_output=True, text=True, check=True).stdout
    dur = float(out.strip())
    if dur > MAX_SECONDS:
        raise RuntimeError(f"الفيديو {dur:.1f}ث يتجاوز {MAX_SECONDS:.0f}ث")
    if dur < 3:
        raise RuntimeError(f"الفيديو قصير جدًا ({dur:.1f}ث)")
    return dur


VALID_SLOTS = ("morning", "afternoon", "evening")


def resolve_slot(raw):
    raw = (raw or "").strip().lower()
    if raw in VALID_SLOTS:
        return raw
    h = datetime.now(timezone.utc).hour                          # استنتاج الفترة من ساعة UTC عند غياب المُدخل
    return "morning" if h < 10 else "afternoon" if h < 16 else "evening"


# نوع المحتوى لكل فترة (يمكن تغييره من متغيرات المستودع): dua | word | seq
DEFAULT_MODES = {"morning": "dua", "afternoon": "word", "evening": "seq"}


def mode_for(slot):
    m = os.environ.get(f"{slot.upper()}_MODE", "").strip().lower()
    return m if m in ("dua", "word", "seq") else DEFAULT_MODES[slot]


# ==================== بناة المنشورات ====================

def build_dua(st, slot, duas):
    from quran.post import Post
    dua = pick_next_dua(duas, st, slot)
    audio_path = pick_next_audio(st)
    print(f"🎵 الصوت: {os.path.basename(audio_path)}")
    os.makedirs(POSTS_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = os.path.join(POSTS_DIR, f"dua_{slot}_{stamp}.mp4")
    generate_dua_video(dua["text"], category=slot, source=dua.get("source", ""), output_path=out, audio_path=audio_path)
    src = dua.get("source", "")
    title = (dua["text"][:80] + "…") if len(dua["text"]) > 80 else dua["text"]
    caption = dua["text"] + (f"\n\n({src})" if src else "") + "\n\n#دعاء #اذكار #إسلام #قرآن #shorts"
    desc = dua["text"] + (f"\n\n({src})" if src else "") + "\n\n#دعاء #shorts #اذكار #إسلام"
    return Post(out, title, desc, caption, ["دعاء", "اذكار", "shorts", "اسلام"], f"dua {slot}")


def build_word(st, slot, duas):
    from quran import word
    return word.build(st, POSTS_DIR)


def build_seq(st, slot, duas):
    from quran import seq
    return seq.build(st, POSTS_DIR)


BUILDERS = {"dua": build_dua, "word": build_word, "seq": build_seq}


def build_with_fallback(state, slot, duas):
    """يجرّب نوع الفترة الأساسي، ثم دعاء الفترة احتياطًا. يرجع (post, state_جديدة). لا يعدّل state الأصلية إلا بالنجاح."""
    import copy
    order = [mode_for(slot)] + ([] if mode_for(slot) == "dua" else ["dua"])
    errors = []
    for mode in order:
        st = copy.deepcopy(state)
        try:
            print(f"🛠️  بناء ({mode}) للفترة {slot}")
            post = BUILDERS[mode](st, slot, duas)
            dur = assert_short(post.video)
            print(f"✅ الفيديو جاهز: {post.video} ({dur:.1f}ث)")
            return post, st
        except Exception as e:                                   # noqa: BLE001
            errors.append(f"{mode}: {e}")
            print(f"❌ فشل بناء ({mode}): {e}", file=sys.stderr)
    raise RuntimeError("فشلت كل المسارات — " + " | ".join(errors))


# ==================== النشر ====================

def publish_everywhere(post):
    """ينشر على كل المنصات المتاحة بشكل مستقل. يرجع (قاموس نتائج، هل أي منصة مفعّلة)."""
    results = {}
    fb_ok = all(os.environ.get(n) for n in ("FB_PAGE_ID", "FB_PAGE_TOKEN", "IG_USER_ID", "GITHUB_REPOSITORY", "GITHUB_TOKEN"))
    yt_ok = all(os.environ.get(n) for n in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))
    if fb_ok:
        video_url = None
        try:
            release = retry(get_or_create_media_release, 3, 10, "GitHub release")
            video_url, _ = retry(lambda: upload_video_asset(release, post.video), 3, 15, "رفع Release")
            print(f"🔗 {video_url}")
            try:
                cleanup_old_release_assets(release["id"])
            except Exception as e:                               # noqa: BLE001
                print("⚠️  تنظيف Release:", e)
            wait_until_url_is_live(video_url, expected_content_prefix="video/")
        except Exception as e:                                   # noqa: BLE001
            print("❌ تخزين الفيديو عبر Release:", e, file=sys.stderr)
        try:
            r = post_to_facebook(post.video, post.caption)
            print("✅ Facebook:", r)
            results["facebook"] = True
        except Exception as e:                                   # noqa: BLE001
            print("❌ Facebook:", e, file=sys.stderr)
            results["facebook"] = False
        if video_url:
            try:
                r = retry(lambda: post_to_instagram(video_url, post.caption), 3, 30, "Instagram")
                print("✅ Instagram:", r)
                results["instagram"] = True
            except Exception as e:                               # noqa: BLE001
                print("❌ Instagram:", e, file=sys.stderr)
                results["instagram"] = False
        else:
            results["instagram"] = False
    else:
        print("⏭️  Facebook/Instagram: متغيرات ناقصة — تخطّي")
    if yt_ok:
        try:
            r = retry(lambda: post_to_youtube(post), 3, 30, "YouTube")
            print("✅ YouTube:", r.get("id") if isinstance(r, dict) else r)
            results["youtube"] = True
        except Exception as e:                                   # noqa: BLE001
            print("❌ YouTube:", e, file=sys.stderr)
            results["youtube"] = False
    else:
        print("⏭️  YouTube: متغيرات ناقصة — تخطّي")
    return results, bool(fb_ok or yt_ok)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", default=os.environ.get("DUA_SLOT", ""))
    ap.add_argument("--dry", action="store_true", help="يبني الفيديو فقط: بلا نشر ولا git")
    ap.add_argument("--save-state", action="store_true", help="مع --dry: يحفظ state.json محليًا")
    ap.add_argument("--force", action="store_true", default=os.environ.get("FORCE", "").lower() == "true",
                    help="ينشر حتى لو نُشرت هذه الفترة اليوم")
    args = ap.parse_args(argv)

    slot = resolve_slot(args.slot)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    duas = load_json(DUAS_PATH, [])
    state = load_json(STATE_PATH, {})
    print(f"▶ الفترة: {slot} — النوع: {mode_for(slot)} — {today}")

    if not args.force and not args.dry and state.get("last_run", {}).get(slot) == today:
        print(f"⏭️  فترة {slot} نُشرت اليوم أصلًا — لا شيء لفعله (حماية من التكرار).")
        return 0

    try:
        post, new_state = build_with_fallback(state, slot, duas)
    except Exception as e:                                       # noqa: BLE001
        print("::error::", e, file=sys.stderr)
        return 1

    if args.dry:
        print("🧪 --dry: لا نشر. الفيديو:", post.video)
        if args.save_state:
            new_state.setdefault("last_run", {})[slot] = today
            save_json(STATE_PATH, new_state)
        return 0

    results, configured = publish_everywhere(post)
    if not configured:
        print("⏭️  لا توجد منصات مضبوطة — لم تُحفظ الحالة.")
        return 0
    if not any(results.values()):
        print("::error::فشل النشر على كل المنصات", file=sys.stderr)
        return 1

    new_state.setdefault("last_run", {})[slot] = today
    save_json(STATE_PATH, new_state)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    git_commit_and_push([os.path.relpath(STATE_PATH, BASE_DIR)], f"Auto: state update {stamp} ({post.label})")
    try:
        os.remove(post.video)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
