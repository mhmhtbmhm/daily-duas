"""
publish.py
- كيختار الدعاء المناسب (صباح/ظهر/مسا) بالتناوب بلا تكرار
- كيولد الصورة
- كيرفعها للريبو (باش يكون عندها رابط عمومي عبر jsdelivr CDN، مستعمل لـ Instagram)
- كينشرها فـ Facebook Page (رفع مباشر/binary) و Instagram Business Account (عبر رابط)
"""
import os
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests

from generate_image import generate_dua_image
from generate_video import generate_dua_video

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DUAS_PATH = os.path.join(BASE_DIR, "duas.json")
STATE_PATH = os.path.join(BASE_DIR, "state.json")
POSTS_DIR = os.path.join(BASE_DIR, "posts")

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# --- إعدادات تجي من GitHub Secrets (متغيرات البيئة) ---
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN")
IG_USER_ID = os.environ.get("IG_USER_ID")
# اسم الريبو بصيغة "username/repo" باش نبنيو رابط عمومي
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")

# أي فترة نحن فيها: يتعطى من GitHub Actions (morning/afternoon/evening)
SLOT = os.environ.get("DUA_SLOT", "general")


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def pick_next_dua(duas, state, category):
    """كيختار الدعاء التالي فالفئة المطلوبة بالتناوب (round-robin) بلا تكرار متتالي."""
    candidates = [d for d in duas if d["category"] == category]
    if not candidates:
        candidates = duas  # fallback

    key = f"index_{category}"
    idx = state.get(key, 0) % len(candidates)
    dua = candidates[idx]
    state[key] = (idx + 1) % len(candidates)
    return dua


def git_commit_and_push(filepaths, message):
    """يزيد الملفات للريبو ويدير commit + push (خدام فـ GitHub Actions runner)."""
    subprocess.run(["git", "config", "user.name", "daily-duas-bot"], check=True)
    subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=True)
    subprocess.run(["git", "add"] + filepaths, check=True)
    result = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True)
    if result.returncode != 0 and "nothing to commit" not in result.stdout:
        print(result.stdout, result.stderr)
    subprocess.run(["git", "push"], check=True)


def public_image_url(relative_path):
    """
    كنستعملو jsdelivr (CDN حقيقية) لأجل Instagram، اللي كيتطلب رابط عمومي
    (raw.githubusercontent.com عندو تأخر تزامن بين edges كيسبب مشاكل).
    """
    if not GITHUB_REPOSITORY:
        raise RuntimeError("GITHUB_REPOSITORY environment variable is missing")
    relative_path = relative_path.replace(os.sep, "/")
    return f"https://cdn.jsdelivr.net/gh/{GITHUB_REPOSITORY}@{GITHUB_BRANCH}/{relative_path}"


def purge_jsdelivr_cache(relative_path):
    """كنطلبو purge باش jsdelivr يجيب آخر نسخة ديال الملف بدل نسخة قديمة/غير موجودة."""
    relative_path = relative_path.replace(os.sep, "/")
    purge_url = f"https://purge.jsdelivr.net/gh/{GITHUB_REPOSITORY}@{GITHUB_BRANCH}/{relative_path}"
    try:
        requests.get(purge_url, timeout=15)
    except requests.RequestException as e:
        print(f"⚠️  ماقدرناش نديرو purge لـ jsdelivr cache: {e}")


def wait_until_url_is_live(url, retries=8, delay=5):
    """
    كنتأكدو بلي الرابط رد فعلا بصورة صحيحة (status 200 + content-type image/*)
    قبل ما نعطيوه لـ Instagram. كنستعملو GET (ماشي HEAD) باش نتأكدو من
    المحتوى الحقيقي.
    """
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=15)
            content_type = resp.headers.get("Content-Type", "")
            if resp.status_code == 200 and content_type.startswith("image/") and len(resp.content) > 0:
                print(f"✅ الرابط جاهز (محاولة {attempt}): {content_type}, {len(resp.content)} bytes")
                return True
            print(f"⏳ محاولة {attempt}/{retries}: status={resp.status_code} content-type={content_type}")
        except requests.RequestException as e:
            print(f"⏳ محاولة {attempt}/{retries}: خطأ فالوصول للرابط: {e}")
        time.sleep(delay)
    print("⚠️  الرابط مازال ماشي متجاوب صحيح بعد كل المحاولات، غادي نكملو بالرغم من ذلك.")
    return False


def _log_response_error(prefix, resp):
    """كيطبع تفاصيل الخطأ الكاملة اللي كترجعها Facebook Graph API (error.message, code, subcode)."""
    try:
        payload = resp.json()
    except ValueError:
        payload = resp.text
    print(f"❌ {prefix} — status={resp.status_code} body={payload}", file=sys.stderr)


def _upload_unpublished_photo(local_filepath, retries=3, delay=5):
    """
    كنرفعو الصورة كـ 'unpublished' (published=false) — كتبقى مرتبطة بالصفحة
    بلا ما تبان كبوست منفصل، وكنستافدو من الـ photo id ديالها باش نلحقوها
    بمنشور /feed من بعد. هاد الخطوة كتستعمل نفس endpoint /photos، فإلا كان
    خطأ 2069019 مرتبط فعلا بفحص "صلاحية الإعلان"، يمكن يبان هنا كيفكيف —
    وهذا سبب علاش زدنا مسار احتياطي كامل تاني تحت.
    """
    url = f"{GRAPH_BASE}/{FB_PAGE_ID}/photos"
    last_exception = None
    for attempt in range(1, retries + 1):
        with open(local_filepath, "rb") as f:
            files = {"source": (os.path.basename(local_filepath), f, "image/png")}
            data = {"published": "false", "access_token": FB_PAGE_TOKEN}
            resp = requests.post(url, data=data, files=files, timeout=30)
        if resp.ok:
            return resp.json()["id"]
        _log_response_error(f"Facebook unpublished /photos (محاولة {attempt}/{retries})", resp)
        try:
            is_transient = resp.json().get("error", {}).get("is_transient", False)
        except ValueError:
            is_transient = False
        last_exception = requests.HTTPError(f"{resp.status_code} error on unpublished /photos", response=resp)
        if not is_transient or attempt == retries:
            break
        time.sleep(delay * attempt)
    raise last_exception


def _post_feed_with_attached_photo(photo_id, caption):
    """المسار 1 (الأساسي): منشور /feed عادي ملحق بيه صورة unpublished."""
    url = f"{GRAPH_BASE}/{FB_PAGE_ID}/feed"
    resp = requests.post(url, data={
        "message": caption,
        "attached_media": json.dumps([{"media_fbid": photo_id}]),
        "access_token": FB_PAGE_TOKEN,
    })
    if not resp.ok:
        _log_response_error("Facebook /feed (attached_media)", resp)
    resp.raise_for_status()
    return resp.json()


def _post_feed_with_direct_photo(local_filepath, caption, retries=3, delay=5):
    """المسار 2 (احتياطي): /photos مباشرة (published=true) بالطريقة القديمة."""
    url = f"{GRAPH_BASE}/{FB_PAGE_ID}/photos"
    last_exception = None
    for attempt in range(1, retries + 1):
        with open(local_filepath, "rb") as f:
            files = {"source": (os.path.basename(local_filepath), f, "image/png")}
            data = {"caption": caption, "access_token": FB_PAGE_TOKEN}
            resp = requests.post(url, data=data, files=files, timeout=30)
        if resp.ok:
            return resp.json()
        _log_response_error(f"Facebook direct /photos (محاولة {attempt}/{retries})", resp)
        try:
            is_transient = resp.json().get("error", {}).get("is_transient", False)
        except ValueError:
            is_transient = False
        last_exception = requests.HTTPError(f"{resp.status_code} error on direct /photos", response=resp)
        if not is_transient or attempt == retries:
            break
        time.sleep(delay * attempt)
    raise last_exception


def _post_feed_with_link(image_url, caption):
    """المسار 3 (الضمان الأخير): منشور نصي عادي فـ /feed مع رابط الصورة كـ link
    preview. هادشي كيضمن خروج المنشور بأي حال، حتى لو الطرق الثلاثة الأخرى
    فشلات بسبب قيود على endpoint /photos بالذات."""
    url = f"{GRAPH_BASE}/{FB_PAGE_ID}/feed"
    resp = requests.post(url, data={
        "message": caption,
        "link": image_url,
        "access_token": FB_PAGE_TOKEN,
    })
    if not resp.ok:
        _log_response_error("Facebook /feed (link fallback)", resp)
    resp.raise_for_status()
    return resp.json()


def post_to_facebook(local_filepath, image_url, caption):
    """
    كنجربو 3 استراتيجيات بالترتيب، وكل وحدة عندها منطق retry ديالها:
    1) صورة unpublished + إلحاقها بـ /feed (الطريقة الموصى بها من Meta لبوست فيه نص وصورة)
    2) /photos مباشرة (الطريقة القديمة، احتياط إلا الأولى عندها نفس القيد)
    3) /feed برابط الصورة (ضمان: كيخرج المنشور بأي حال ولو بدون صورة مرفوعة فعليا)
    كنوقفو عند أول محاولة ناجحة.
    """
    errors = []

    try:
        photo_id = _upload_unpublished_photo(local_filepath)
        result = _post_feed_with_attached_photo(photo_id, caption)
        print("   → نجح عبر: unpublished photo + /feed")
        return result
    except Exception as e:
        errors.append(f"[unpublished+feed] {e}")

    try:
        result = _post_feed_with_direct_photo(local_filepath, caption)
        print("   → نجح عبر: /photos مباشرة")
        return result
    except Exception as e:
        errors.append(f"[direct /photos] {e}")

    try:
        result = _post_feed_with_link(image_url, caption)
        print("   → نجح عبر: /feed مع رابط (fallback أخير، بلا صورة مرفوعة)")
        return result
    except Exception as e:
        errors.append(f"[feed link] {e}")

    raise RuntimeError("فشلت الثلاث استراتيجيات ديال Facebook:\n" + "\n".join(errors))


def wait_for_ig_container_ready(creation_id, retries=10, delay=3):
    """
    Instagram كيطلب وقت باش يعالج الصورة قبل ما يقبل media_publish.
    خاصنا نـ poll على status_code حتى يولي FINISHED.
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
    print("⚠️  الـ container مازال IN_PROGRESS بعد كل المحاولات.")
    return False


def post_to_instagram(image_url, caption):
    # الخطوة 1: إنشاء container (Instagram كيتطلب رابط عمومي، ماشي binary upload)
    create_url = f"{GRAPH_BASE}/{IG_USER_ID}/media"
    resp = requests.post(create_url, data={
        "image_url": image_url,
        "caption": caption,
        "access_token": FB_PAGE_TOKEN,
    })
    if not resp.ok:
        _log_response_error("Instagram /media (create container)", resp)
    resp.raise_for_status()
    creation_id = resp.json()["id"]

    # الخطوة 2: كنستناو حتى الـ container يولي FINISHED قبل النشر
    wait_for_ig_container_ready(creation_id)

    # الخطوة 3: نشر container
    publish_url = f"{GRAPH_BASE}/{IG_USER_ID}/media_publish"
    resp2 = requests.post(publish_url, data={
        "creation_id": creation_id,
        "access_token": FB_PAGE_TOKEN,
    })
    if not resp2.ok:
        _log_response_error("Instagram /media_publish", resp2)
    resp2.raise_for_status()
    return resp2.json()


def post_to_youtube(video_path, dua_text, source):
    from youtube_upload import upload_short
    title = (dua_text[:80] + "…") if len(dua_text) > 80 else dua_text
    description = dua_text + (f"\n\n({source})" if source else "") + \
        "\n\n#دعاء #shorts #اذكار #إسلام"
    return upload_short(
        video_path,
        title=title,
        description=description,
        tags=["دعاء", "اذكار", "shorts", "اسلام"],
    )


def main():
    missing = [name for name in ["FB_PAGE_ID", "FB_PAGE_TOKEN", "IG_USER_ID", "GITHUB_REPOSITORY"]
               if not os.environ.get(name)]
    if missing:
        print(f"⚠️  متغيرات ناقصة: {missing}. غادي نولدو الصورة فقط بلا نشر.")

    duas = load_json(DUAS_PATH, [])
    state = load_json(STATE_PATH, {})

    dua = pick_next_dua(duas, state, SLOT)

    os.makedirs(POSTS_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"dua_{SLOT}_{timestamp}.png"
    filepath = os.path.join(POSTS_DIR, filename)
    relative_path = os.path.relpath(filepath, BASE_DIR)

    generate_dua_image(dua["text"], category=SLOT, source=dua.get("source", ""), output_path=filepath)
    print(f"✅ الصورة تولدات: {filepath}")

    save_json(STATE_PATH, state)

    # ندفعو الصورة للريبو باش يكون عندها رابط عمومي (لـ Instagram)
    git_commit_and_push([relative_path, os.path.relpath(STATE_PATH, BASE_DIR)],
                         f"Auto: dua image {filename}")

    # ملاحظة: هاد الدالة كتفترض أن جذر الريبو هو نفسه مجلد المشروع (BASE_DIR).
    # إلا كان المشروع فمجلد فرعي فالريبو، زيد اسم المجلد هنا، مثلا: f"daily-duas/{relative_path}"
    image_url = public_image_url(relative_path)
    caption = dua["text"] + (f"\n\n({dua['source']})" if dua.get("source") else "") + \
        "\n\n#دعاء #اذكار #إسلام #قرآن"

    print(f"🔗 رابط الصورة: {image_url}")

    if not missing:
        # لازم الرابط العمومي يكون جاهز قبل أي حاولة (يستافدو منو Instagram
        # وكذلك مسار fallback الأخير ديال Facebook)
        purge_jsdelivr_cache(relative_path)
        wait_until_url_is_live(image_url)

        # Facebook: 3 استراتيجيات بالتسلسل (شوف post_to_facebook فوق)
        try:
            fb_result = post_to_facebook(filepath, image_url, caption)
            print("✅ تنشر فـ Facebook:", fb_result)
        except Exception as e:
            print("❌ خطأ فـ Facebook (فشلت كل الاستراتيجيات):", e, file=sys.stderr)
        try:
            ig_result = post_to_instagram(image_url, caption)
            print("✅ تنشر فـ Instagram:", ig_result)
        except Exception as e:
            print("❌ خطأ فـ Instagram:", e, file=sys.stderr)
    else:
        print("⏭️  تخطينا النشر الفعلي (السكريبت خدام محليا/تجربة).")

    # --- YouTube Short (اختياري، غير كاين إلا كانت متغيرات YT_* موجودة) ---
    yt_missing = [name for name in ["YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"]
                  if not os.environ.get(name)]
    if not yt_missing:
        video_filename = f"dua_{SLOT}_{timestamp}.mp4"
        video_filepath = os.path.join(POSTS_DIR, video_filename)
        try:
            generate_dua_video(dua["text"], category=SLOT, source=dua.get("source", ""),
                                output_path=video_filepath)
            print(f"✅ الفيديو تولد: {video_filepath}")
            yt_result = post_to_youtube(video_filepath, dua["text"], dua.get("source", ""))
            print("✅ تنشر فـ YouTube:", yt_result.get("id"))
        except Exception as e:
            print("❌ خطأ فـ YouTube:", e, file=sys.stderr)
    else:
        print(f"⏭️  تخطينا YouTube (متغيرات ناقصة: {yt_missing})")


if __name__ == "__main__":
    main()
