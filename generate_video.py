"""
generate_video.py
يبدل صورة الدعاء العمودية (1080x1920) لفيديو قصير (YouTube Shorts):
حركة تكبير بطيئة وناعمة (Ken Burns effect)، بلا صوت وبلا تلاوة —
النص فقط هو المعروض، بلا أي إضافة صوتية للدعاء نفسو.
"""
import os
import subprocess

from generate_image import generate_dua_image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
DURATION_SECONDS = 10
FPS = 30


def generate_dua_video(text, category="general", source="", output_path="output.mp4"):
    # 1. نولدو صورة عمودية عالية الدقة (أكبر شوية من حجم الفيديو باش الزوم مايبانش مقطوع)
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

    total_frames = DURATION_SECONDS * FPS

    # 2. ffmpeg zoompan: تكبير بطيء وناعم من 1.0 إلى 1.08، بلا صوت
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
        "-vf", zoompan_filter,
        "-t", str(DURATION_SECONDS),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-an",  # بلا صوت نهائيا
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
