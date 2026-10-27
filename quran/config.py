"""config.py — إعدادات قناة «كلمة من القرآن»."""
import os

W, H, FPS = 1080, 1920, 30
HARD_LIMIT = 58.5                                        # سقف صارم: الفيديو لا يتجاوز 59 ثانية أبدًا (لا يمكن رفعه بمتغير)
MAX_CLIP = min(float(os.environ.get("MAX_CLIP", "56")), 56.0)   # التلاوة + 0.45 بداية + 1.4 نهاية ≤ HARD_LIMIT
MIN_CLIP = 3.0
MAX_TOTAL = HARD_LIMIT
RECITER = os.environ.get("RECITER", "").strip()          # اسم القارئ يظهر في الفيديو والوصف (يُنصح به)
UPLOAD_LANGUAGE = "ar"
HASHTAGS = "#القرآن_الكريم #معاني_القرآن #تفسير #كلمة_من_القرآن #shorts"
BASE_TAGS = ["القرآن الكريم", "معاني القرآن", "تفسير القرآن", "كلمة من القرآن", "غريب القرآن", "تدبر", "shorts"]
SOURCES = {   # معرّف الإصدار في alquran.cloud → اسم يظهر للمشاهد
    "ar.muyassar": "التفسير الميسر — مجمع الملك فهد لطباعة المصحف الشريف",
    "ar.jalalayn": "تفسير الجلالين",
}
DISCLAIMER = "الشرح منقول حرفيًا من كتب التفسير المعتمدة المذكورة، وللتوسع يُرجى الرجوع إليها."

# مصدر الصوت: auto (assets/audio إن وُجدت مقاطع، وإلا الإنترنت) | local | online
AUDIO_SOURCE = os.environ.get("AUDIO_SOURCE", "auto").strip().lower()
ONLINE_RECITERS = {   # مفتاح → (مجلد everyayah.com، الاسم الظاهر)
    "sudais": ("Abdurrahmaan_As-Sudais_192kbps", "الشيخ عبد الرحمن السديس"),
    "husary": ("Husary_128kbps", "الشيخ محمود خليل الحصري"),
    "minshawi": ("Minshawy_Murattal_128kbps", "الشيخ محمد صديق المنشاوي"),
    "alafasy": ("Alafasy_128kbps", "الشيخ مشاري العفاسي"),
    "shuraym": ("Saood_ash-Shuraym_128kbps", "الشيخ سعود الشريم"),
}
ONLINE_RECITER = os.environ.get("ONLINE_RECITER", "sudais").strip().lower()
