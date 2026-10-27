"""post.py — حاوية نتيجة بناء منشور واحد (فيديو + نصوص النشر)."""
from dataclasses import dataclass, field


@dataclass
class Post:
    video: str
    title: str               # عنوان YouTube
    description: str         # وصف YouTube (طويل)
    caption: str             # نص Facebook / Instagram (أقصر)
    tags: list = field(default_factory=list)
    label: str = ""
