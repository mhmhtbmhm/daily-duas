"""
publish.py
- كيختار الدعاء المناسب (صباح/ظهر/مسا) بالتناوب بلا تكرار
- كيولد الصورة
- كيرفعها للريبو (باش يكون عندها رابط عمومي عبر raw.githubusercontent.com)
- كينشرها فـ Facebook Page و Instagram Business Account
"""
import os
import json
import subprocess
import sys
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
# اسم الريبو بصيغة "username/repo" باش نبنيو رابط raw.githubusercontent.com
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


def public_raw_url(relative_path):
    if not GITHUB_REPOSITORY:
        raise RuntimeError("GITHUB_REPOSITORY environment variable is missing")
    return f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/{GITHUB_BRANCH}/{relative_path}"


def post_to_facebook(image_url, caption):
    url = f"{GRAPH_BASE}/{FB_PAGE_ID}/photos"
    resp = requests.post(url, data={
        "url": image_url,
        "caption": caption,
        "access_token": FB_PAGE_TOKEN,
    })
    resp.raise_for_status()
    return resp.json()


def post_to_instagram(image_url, caption):
    # الخطوة 1: إنشاء container
    create_url = f"{GRAPH_BASE}/{IG_USER_ID}/media"
    resp = requests.post(create_url, data={
        "image_url": image_url,
        "caption": caption,
        "access_token": FB_PAGE_TOKEN,
    })
    resp.raise_for_status()
    creation_id = resp.json()["id"]

    # الخطوة 2: نشر container
    publish_url = f"{GRAPH_BASE}/{IG_USER_ID}/media_publish"
    resp2 = requests.post(publish_url, data={
        "creation_id": creation_id,
        "access_token": FB_PAGE_TOKEN,
    })
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

    # ندفعو الصورة للريبو باش يكون عندها رابط عمومي
    git_commit_and_push([relative_path, os.path.relpath(STATE_PATH, BASE_DIR)],
                         f"Auto: dua image {filename}")

    # ملاحظة: هاد الدالة كتفترض أن جذر الريبو هو نفسه مجلد المشروع (BASE_DIR).
    # إلا كان المشروع فمجلد فرعي فالريبو، زيد اسم المجلد هنا، مثلا: f"daily-duas/{relative_path}"
    image_url = public_raw_url(relative_path)
    caption = dua["text"] + (f"\n\n({dua['source']})" if dua.get("source") else "") + \
        "\n\n#دعاء #اذكار #إسلام #قرآن"

    print(f"🔗 رابط الصورة: {image_url}")

    if not missing:
        try:
            fb_result = post_to_facebook(image_url, caption)
            print("✅ تنشر فـ Facebook:", fb_result)
        except Exception as e:
            print("❌ خطأ فـ Facebook:", e, file=sys.stderr)

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
