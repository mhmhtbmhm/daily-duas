# ترقية Daily Duas — 3 فترات + استمرارية

| الفترة | المحتوى | احتياطي عند الفشل |
|---|---|---|
| morning | دعاء/حديث (كما هو) | — |
| afternoon | «كلمة من القرآن» (Groq + تفسير حرفي + تلاوة) | دعاء الظهر |
| evening | تلاوة متتابعة من أول المصحف بصوت السديس، آية/فيديو، ثم ختمة جديدة | دعاء المساء |

## التركيب (استبدل/أضف في المستودع)
- استبدل: `publish.py`, `generate_video.py`, `requirements.txt`, `.github/workflows/daily-duas.yml`
- أضف مجلد: `quran/` كاملًا (فيه الخطوط)
- أضف سرًّا: `GROQ_API_KEY`  (الباقي موجود عندك)
- `state.json` لا يُمسّ: يُضاف إليه `qseq` و`qw_used` و`last_run` تلقائيًا.

## cron-job.org (3 مهام، POST إلى .../actions/workflows/daily-duas.yml/dispatches)
Body: {"ref":"main","inputs":{"slot":"morning"}}  ← ثم "afternoon" ثم "evening"
(إن حذفت inputs تُستنتج الفترة من ساعة UTC: <10 صباح، <16 ظهر، وإلا مساء)

## متغيرات اختيارية (Settings ▸ Variables)
MORNING_MODE / AFTERNOON_MODE / EVENING_MODE = dua | word | seq
WORD_RECITER (افتراضي alafasy) — SEQ_RECITER (افتراضي sudais): sudais|husary|minshawi|alafasy|shuraym — PRIVACY

## الاستمرارية
- مشغّلان مستقلان: cron-job.org + جدولة GitHub الاحتياطية (40 دقيقة بعد الساعات 6/12/18 UTC — عدّلها أو احذفها). لا تكرار: فترة نُشرت اليوم تُتخطّى.
- 3 محاولات للتشغيل كله، وإعادة محاولة لكل منصة، وفشل مسار المحتوى يعني الدعاء الاحتياطي.
- لا يتحرك مؤشر (آية/كلمة/دعاء) إلا بعد نجاح منصة واحدة على الأقل.
- كل فيديو يُفحص: أكثر من 59ث لا يُنشر (السقف الفعلي 58.5ث؛ التلاوة ≤ 56ث، والآية الأطول تُتخطّى نهائيًا وتُسجَّل في state.json ▸ qseq ▸ skipped_list).
- فشل التشغيل يصلك على بريد GitHub تلقائيًا.

تجربة محلية بلا نشر:  python publish.py --slot evening --dry --save-state
