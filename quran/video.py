"""video.py — ثلاثة مشاهد بانتقال ناعم + تلاوة المقطع المختار (تطبيع الصوت وتلاشٍ في البداية والنهاية)."""
import os
import subprocess

from . import config
from .media import duration

A_DUR, FADE, LEAD = 3.4, 0.55, 0.45     # مدة بطاقة الكلمة، الانتقال، تأخير بدء التلاوة
TAIL = 1.4


def plan(clip_dur, excerpt_len):
    b = min(11.0, max(5.5, 3.2 + excerpt_len * 0.05))
    total = max(clip_dur + LEAD + TAIL, A_DUR + b + 5.5)
    return {"a": A_DUR, "b": b, "c": total - A_DUR - b, "total": total}


def build(images, clip_path, out_path, excerpt_len):
    clip_dur = duration(clip_path)
    p = plan(clip_dur, excerpt_len)
    if p["total"] > config.MAX_TOTAL:
        raise RuntimeError("الفيديو أطول من المسموح")
    lens = [p["a"] + FADE, p["b"] + FADE, p["c"]]
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for img, ln in zip(images, lens):
        cmd += ["-framerate", str(config.FPS), "-loop", "1", "-t", f"{ln:.3f}", "-i", img]
    cmd += ["-i", clip_path]
    g = [f"[{i}:v]scale={config.W}:{config.H},format=yuv420p,setsar=1[s{i}]" for i in range(3)]
    g.append(f"[s0][s1]xfade=transition=fade:duration={FADE}:offset={p['a']:.3f}[x1]")
    g.append(f"[x1][s2]xfade=transition=fade:duration={FADE}:offset={p['a'] + p['b']:.3f}[x2]")
    g.append(f"[x2]fade=t=in:st=0:d=0.4,fade=t=out:st={p['total'] - 0.7:.3f}:d=0.7[v]")
    ms = int(LEAD * 1000)
    fo = max(0.5, min(1.2, clip_dur - 0.5))
    g.append(f"[3:a]aresample=44100,aformat=channel_layouts=stereo,loudnorm=I=-16:TP=-1.5:LRA=9,"
             f"afade=t=in:d=0.35,afade=t=out:st={max(0.0, clip_dur - fo):.3f}:d={fo:.3f},adelay={ms}|{ms},"
             f"apad=whole_dur={p['total']:.3f}[a]")
    cmd += ["-filter_complex", ";".join(g), "-map", "[v]", "-map", "[a]", "-t", f"{p['total']:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_path]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed:\n{e.stderr[-1500:]}") from e
    real = duration(out_path)                       # فحص أخير على الملف الناتج نفسه
    if real > 59.0:

        os.remove(out_path)
        raise RuntimeError(f"الفيديو {real:.1f}ث يتجاوز 59 ثانية — حُذف")
    return p
