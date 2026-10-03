# Last- — USB HDMI Realtime AI Coach

نسخة تطوير للاختبار المحلي/الأوفلاين على PS5 عبر **USB HDMI Capture Card**.

## البنية

نفس البنية الأصلية محفوظة:

`ScreenReader → GameStateAnalyzer → TacticalAdvisor → CoachingOverlay → RealtimeAICoach`

الفرق الرئيسي أن `ScreenReader` يقرأ الصورة مباشرة من USB Capture بدل `ImageGrab`.

## المميزات

- Auto-detect لأول USB video capture صالح.
- طلب 1920×1080 / 120 FPS مع استخدام MJPG عند دعم القطعة له.
- قياس FPS الفعلي داخل البرنامج بدل الاعتماد على الرقم المكتوب على الكرت.
- تتبع اللون `#FF00FF`.
- فلترة عناصر HUD البنفسجية عبر مناطق استبعاد قابلة للتعطيل.
- فلترة blobs حسب المساحة، الطول/العرض، extent، solidity، ونسبة اللون داخل الجسم.
- Preview يرسم boxes فقط حول الأجسام التي اجتازت فلتر الجسم.
- OCR للسلاح throttled إلى مرة تقريبًا كل ثانية حتى لا يوقف حلقة الكابتشر.
- إصلاح حساب الصحة: يعتمد على نسبة pixels بدل جمع قيم mask ذات 255.
- Overlay منفصل للمعلومات والنصائح أثناء الاختبار المحلي/الأوفلاين.

## التشغيل السريع على Windows

1. وصل PS5 إلى HDMI Capture.
2. وصل الـCapture إلى USB في الكمبيوتر.
3. تأكد أن الصورة تظهر في Windows Camera أو OBS.
4. شغّل:

```text
run_coach.bat
```

سيحاول البرنامج اكتشاف الجهاز تلقائيًا.

## التشغيل اليدوي

```bash
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python realtime_ai_coach.py --device auto --width 1920 --height 1080 --fps 120 --preview
```

إذا اختار كاميرا خاطئة:

```bash
python realtime_ai_coach.py --device 1 --preview
```

جرّب `0`, ثم `1`, ثم `2` حسب ترتيب الأجهزة في Windows.

## خيارات مهمة

```text
--device auto       اكتشاف تلقائي
--device 0          اختيار الجهاز يدويًا
--fps 120           FPS المطلوب من الكرت
--preview           عرض صورة الكابتشر مع detection boxes
--no-overlay        تعطيل نافذة AI Coach
--no-hud-mask       تعطيل استبعاد مناطق HUD
```

## لون الخصم

اللون الافتراضي مضبوط على:

```text
#FF00FF
```

ويتم تحويله إلى HSV داخليًا مع tolerance ضيق لتقليل التقاط درجات البنفسجي الأخرى.

## ملاحظات FPS

الرقم المكتوب على HDMI/Capture ليس ضمانًا أن Windows/OpenCV سيستقبل نفس المعدل. البرنامج يطلب 120 FPS ويعرض **Vision FPS الفعلي**. معدل الالتقاط النهائي يعتمد على USB mode، دقة الكرت، codec، driver، ومنفذ USB المستخدم.

## Tesseract

`pytesseract` موجود في المتطلبات، لكن OCR يحتاج Tesseract executable مثبتًا على Windows. إذا لم يكن مثبتًا، البرنامج يستمر في العمل ويترك Weapon OCR على آخر قيمة معروفة/Unknown.

## الإيقاف

في نافذة Preview اضغط:

- `Q`
- أو `ESC`

