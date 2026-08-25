# نشر الأدعية اليومية تلقائيا (Facebook + Instagram)

سكريبت كيولد صورة دعاء بالعربية 3 مرات فاليوم (صباح، ظهر، مسا) وينشرها أوتوماتيكيا فصفحة الفيسبوك وحساب انستغرام Business، بلا أي تدخل يدوي، عبر **GitHub Actions** (مجاني 100%).

---

## 1. الملفات

```
daily-duas/
├── duas.json              # قائمة الأدعية (زيد فيها لي بغيتي)
├── generate_image.py      # يولد صورة الدعاء
├── publish.py              # يختار الدعاء، يولد الصورة، ينشرها
├── requirements.txt
├── assets/
│   └── NotoNaskhArabic-Bold.ttf
└── .github/workflows/
    └── daily-duas.yml      # الجدولة (cron)
```

---

## 2. الخطوات الأساسية (مرة وحدة، تقريبا 20 دقيقة)

### أ) حضّر صفحة الفيسبوك وحساب انستغرام
1. خاص يكون عندك **صفحة Facebook** (Page).
2. خاص حساب **Instagram Business أو Creator**، ومربوط بصفحة الفيسبوك ديالك (من إعدادات الصفحة → Linked Accounts).

### ب) دير Meta App باش تجيب Access Token
1. سير لـ https://developers.facebook.com/apps وسنيّ App جديد، نوع "Business".
2. زيد المنتجات: **Facebook Login** و **Instagram Graph API**.
3. من [Graph API Explorer](https://developers.facebook.com/tools/explorer/):
   - ختار الـ App ديالك.
   - عطي الصلاحيات: `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`, `instagram_content_publish`.
   - جيب "User Access Token" قصير المدى.
4. بدّل الـ Token القصير لـ **Token طويل المدى (60 يوم)** بهاد الرابط (بدّل القيم):
   ```
   https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=SHORT_TOKEN
   ```
5. من بعد جيب **Page Access Token** (هوما ما كيتجدّدوش وما عندهمش تاريخ صلاحية إلا كان الـ App فـ Live mode):
   ```
   https://graph.facebook.com/v21.0/me/accounts?access_token=LONG_LIVED_USER_TOKEN
   ```
   غادي يرجع ليك `id` (الصفحة) و`access_token` (Page Token) — احتفظ بيهم.

6. جيب الـ Instagram Business Account ID:
   ```
   https://graph.facebook.com/v21.0/PAGE_ID?fields=instagram_business_account&access_token=PAGE_TOKEN
   ```

⚠️ باش الـ Page Token يبقى خدام على المدى الطويل بلا انتهاء، خاص الـ App ديالك يكون فـ **Live Mode** (Review) — إلا بقا فـ Development Mode، التوكن غادي ينتهي بعد شي مدة وتضطر تجدده يدويا.

### ج) دير الريبو فـ GitHub
1. حمّل هاد المجلد كامل، ودير منو ريبو جديد فـ GitHub (public أو private، الاثنين خدامين).
2. من إعدادات الريبو → **Settings → Secrets and variables → Actions**، زيد:
   - `FB_PAGE_ID`
   - `FB_PAGE_TOKEN`
   - `IG_USER_ID`
3. تأكد بلي **Settings → Actions → General → Workflow permissions** مضبوط على "Read and write permissions" (باش السكريبت يقدر يدفع الصور للريبو).

### د) جرب يدويا
من تبويب **Actions** فالريبو → ختار "Daily Duas Auto-Publish" → **Run workflow** → دخل slot (مثلا `morning`) → Run.

إلا خدمة، غادي تلقى صورة جديدة فـ `posts/` وبوست جديد فالصفحة والانستغرام.

---

## 3. الجدولة

الملف `.github/workflows/daily-duas.yml` فيه 3 أوقات (بتوقيت UTC):
- `0 6 * * *` → صباح
- `0 12 * * *` → الظهر
- `0 17 * * *` → المسا

المغرب عادة UTC+1 (وUTC+0 خلال رمضان)، بدّل الأرقام إلا بغيتي وقت مضبوط بزاف.

> ملاحظة: GitHub Actions cron ماشي دقيق 100% (ممكن يتأخر بضع دقائق فساعات الذروة)، عادي بالنسبة لنشر يومي.

---

## 4. زيادة أدعية

زيد فـ `duas.json` بهاد الشكل:
```json
{"category": "morning", "text": "...", "source": "..."}
```
`category` خاصها تكون: `morning` / `afternoon` / `evening`. السكريبت كيدور عليهم بالتناوب بلا تكرار.

---

## 5. حدود مهمة

- Instagram Graph API: أقصى حد **25 منشور فكل 24 ساعة** لكل حساب — أنت بعيد بزاف (3 فقط).
- الصورة خاصها تكون عمومية (public URL) باش IG يقدر يقراها، ولهذا كنستعملو `raw.githubusercontent.com`.
- الطريقة قانونية ومجانية 100%: كتستعمل الـ APIs الرسمية ديال Meta بلا أي bot أو scraping.

---

## 6. اليوتيوب (اختياري، مرحلة جاية)

يوتيوب ما كيقبلش صور ثابتة كـ "منشور" مثل فيسبوك/انستغرام — خاص فيديو أو Community Post (والـ Community Post API محدود بزاف). الحل الأنسب: نبدلو الصورة لفيديو قصير (Ken Burns effect + تلاوة صوتية بـ edge-tts) وننشروه كـ YouTube Short بـ OAuth2، بحال كنت داير مع القناة ديالك. نقدر نبنيوه فمرحلة ثانية إلا حبيت.
