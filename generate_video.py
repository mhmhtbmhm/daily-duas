"""
generate_video.py
يبدل صورة الدعاء العمودية (1080x1920) لفيديو قصير (YouTube Shorts / Reels):
حركة تكبير بطيئة وناعمة (Ken Burns effect)، مع مقطع صوتي (تلاوة آيات
قرآنية) يُستعمل كصوت للفيديو بالكامل. مدة الفيديو تُطابق مدة التلاوة
تلقائيا (ضمن حد أدنى وأقصى معقولين).

تحديث: الصوت لم يعد ملفا ثابتا واحدا — يُمرَّر الآن كمُعامل (audio_path)
من publish.py، الذي يختاره بالتناوب من مجموعة ملفات صوتية متعددة
(موجودة في assets/audio/) لتفادي تكرار نفس الصوت في كل منشور.
"""
import os
import subprocess
from generate_image import generate_dua_image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30

# مسار افتراضي يُستعمل فقط إذا استُدعيت الدالة بلا تمرير audio_path صراحة
# (مثلا عند تشغيل الملف مباشرة بـ __main__ للاختبار). الاستعمال الفعلي من
# publish.py يمرر دائما audio_path الصحيح المختار بالتناوب.
DEFAULT_AUDIO_PATH = os.path.join(BASE_DIR, "assets", "audio", "audio_001.mp3")

MIN_DURATION_SECONDS = 15
MAX_DURATION_SECONDS = 59


def _get_audio_duration(audio_path):
    """يستعمل ffprobe لمعرفة مدة الملف الصوتي بالثواني (float)."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def generate_dua_video(text, category="general", source="", output_path="output.mp4",
                        audio_path=None):
    """
    audio_path: مسار الملف الصوتي المستعمل لهذا الفيديو تحديدا. إذا تُرك
    None، يُستعمل DEFAULT_AUDIO_PATH (مفيد فقط للاختبار اليدوي المباشر).
    """
    if audio_path is None:
        audio_path = DEFAULT_AUDIO_PATH

    if not os.path.isfile(audio_path):
        raise FileNotFoundError(
            f"المقطع الصوتي غير موجود: {audio_path}\n"
            "تأكد من وجود الملف في المسار الصحيح داخل assets/audio/."
        )

    audio_duration = _get_audio_duration(audio_path)
    # مدة الفيديو = مدة التلاوة، مُقيَّدة بين الحد الأدنى والأقصى
    duration = max(MIN_DURATION_SECONDS, min(audio_duration, MAX_DURATION_SECONDS))

    # 1. نولّد صورة عمودية عالية الدقة (أكبر شوية من حجم الفيديو باش الزوم مايبانش مقطوع)
    tmp_image = output_path.replace(".mp4", "_source.png")
    upscale = 1.15
    generate_dua_image(
        text,
        category=category,
        source=source,
        output_path=tmp_image,
        width=int(VIDEO_WIDTH * upscale),
        height=int(VIDEO_HEIGHT * upscale),
    )

    total_frames = int(duration * FPS)
    # 2. ffmpeg zoompan: تكبير بطيء وناعم من 1.0 إلى 1.08
    zoompan_filter = (
        f"zoompan=z='min(zoom+0.0007,1.08)':"
        f"d={total_frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={FPS},"
        f"format=yuv420p"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", tmp_image,
        # -stream_loop -1 يكرر الصوت تلقائيا إن كانت مدة الفيديو (المقيَّدة
        # بـ MIN/MAX) أطول من التلاوة نفسها؛ و-t تحته يقص الزائد إن كانت
        # التلاوة أطول من MAX_DURATION_SECONDS. نفس السطر يغطي الحالتين.
        "-stream_loop", "-1",
        "-i", audio_path,
        "-vf", zoompan_filter,
        "-t", str(duration),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    os.remove(tmp_image)
    return output_path


if __name__ == "__main__":
    generate_dua_video(
        "اللَّهُمَّ بِكَ أَصْبَحْنَا، وَبِكَ أَمْسَيْنَا، وَبِكَ نَحْيَا، وَبِكَ نَمُوتُ، وَإِلَيْكَ النُّشُورُ",
        category="morning",
        source="حديث صحيح",
        output_path=os.path.join(BASE_DIR, "test_video.mp4"),
    )
    print("saved test_video.mp4")
