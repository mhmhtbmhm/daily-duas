"""
generate_image.py
يولد صورة مربعة (1080x1080) لدعاء باللغة العربية، جاهزة للنشر فـ Instagram و Facebook.
يعتمد على محرك raqm المدمج فـ Pillow للتشكيل العربي الصحيح (بلا حاجة لـ arabic_reshaper).
"""
import os
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "assets", "NotoNaskhArabic-Bold.ttf")

SIZE = 1080

# ألوان حسب الفئة (صباح / ظهر / مسا)
THEMES = {
    "morning":   {"top": (255, 205, 112), "bottom": (255, 149, 90),  "label": "دعاء الصباح"},
    "afternoon": {"top": (110, 190, 210), "bottom": (43, 122, 154),  "label": "دعاء اليوم"},
    "evening":   {"top": (72, 61, 139),   "bottom": (25, 25, 60),    "label": "دعاء المساء"},
    "general":   {"top": (46, 125, 100),  "bottom": (18, 60, 50),    "label": "دعاء"},
}


def _vertical_gradient(size, top_color, bottom_color):
    img = Image.new("RGB", size, top_color)
    draw = ImageDraw.Draw(img)
    h = size[1]
    for y in range(h):
        ratio = y / h
        r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
        g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
        b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
        draw.line([(0, y), (size[0], y)], fill=(r, g, b))
    return img


def _wrap_arabic(draw, text, font, max_width):
    """يقسم النص العربي لأسطر بحيث يدخل فـ max_width."""
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        trial = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), trial, font=font, direction="rtl")
        width = bbox[2] - bbox[0]
        if width <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def generate_dua_image(text, category="general", source="", output_path="output.png"):
    theme = THEMES.get(category, THEMES["general"])
    img = _vertical_gradient((SIZE, SIZE), theme["top"], theme["bottom"])
    draw = ImageDraw.Draw(img)

    # إطار زخرفي خفيف
    margin = 40
    draw.rectangle(
        [margin, margin, SIZE - margin, SIZE - margin],
        outline=(255, 255, 255, 180),
        width=3,
    )
    inner_margin = 55
    draw.rectangle(
        [inner_margin, inner_margin, SIZE - inner_margin, SIZE - inner_margin],
        outline=(255, 255, 255, 120),
        width=1,
    )

    # العنوان العلوي
    label_font = ImageFont.truetype(FONT_PATH, 46)
    label = theme["label"]
    bbox = draw.textbbox((0, 0), label, font=label_font, direction="rtl")
    lw = bbox[2] - bbox[0]
    draw.text(((SIZE - lw) / 2, 110), label, font=label_font, fill=(255, 255, 255), direction="rtl")

    # خط فاصل صغير
    draw.line([(SIZE / 2 - 60, 190), (SIZE / 2 + 60, 190)], fill=(255, 255, 255), width=3)

    # النص الرئيسي — نحسب أفضل حجم خط يدخل فالمساحة
    max_text_width = SIZE - 220
    max_text_height = 620
    font_size = 66
    while font_size > 30:
        font = ImageFont.truetype(FONT_PATH, font_size)
        lines = _wrap_arabic(draw, text, font, max_text_width)
        line_height = font.getbbox("العربية", direction="rtl")[3] + 22
        total_height = line_height * len(lines)
        if total_height <= max_text_height:
            break
        font_size -= 2

    start_y = 280 + (max_text_height - line_height * len(lines)) / 2
    y = start_y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, direction="rtl")
        lw = bbox[2] - bbox[0]
        draw.text(((SIZE - lw) / 2, y), line, font=font, fill=(255, 255, 255), direction="rtl")
        y += line_height

    # المصدر أسفل الصورة
    if source:
        source_font = ImageFont.truetype(FONT_PATH, 34)
        source_text = f"« {source} »"
        bbox = draw.textbbox((0, 0), source_text, font=source_font, direction="rtl")
        lw = bbox[2] - bbox[0]
        draw.text(((SIZE - lw) / 2, SIZE - 170), source_text, font=source_font, fill=(255, 255, 255), direction="rtl")

    img.save(output_path, "PNG")
    return output_path


if __name__ == "__main__":
    generate_dua_image(
        "اللَّهُمَّ بِكَ أَصْبَحْنَا، وَبِكَ أَمْسَيْنَا، وَبِكَ نَحْيَا، وَبِكَ نَمُوتُ، وَإِلَيْكَ النُّشُورُ",
        category="morning",
        source="حديث صحيح",
        output_path=os.path.join(BASE_DIR, "test_output.png"),
    )
    print("saved test_output.png")
