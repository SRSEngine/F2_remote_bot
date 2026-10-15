# F2 — ریموت و ربات SBC ایکس‌باکس

پروژه‌ی F2 چند کنسول ایکس‌باکس را هم‌زمان با **Xbox Remote Play** کنترل می‌کند و روی هر کدام یک ربات اجرا می‌کند
که چالش‌های **SBC** بازی EA FC (Ultimate Team) را خودکار پر و Submit می‌کند.

- **ریموت (xbrp):** تصویر کنسول را نشان می‌دهد و دکمه‌ها را از طریق Named Pipe به کنسول می‌فرستد.
- **ربات (Play.py):** صفحه را با تطبیق تصویر و OCR می‌خواند، بازیکن‌ها را از Club برمی‌دارد یا از Transfer Market می‌خرد و چالش را Submit می‌کند.
- **پنل (F2):** اکانت‌ها، ریموت‌ها، فهرست SBCها، قیمت‌ها و وضعیت ربات‌ها را از یک جا مدیریت می‌کند.

---

## ساختار کلی

```
               ┌────────────────────────── پنل F2 (Pannel\panel.py) ──────────────────────────┐
               │  Accounts · Monitor · SBCs · Status · Prices · Players                       │
               └──────┬───────────────────────┬──────────────────────────┬─────────────────────┘
                      │ اجرای ریموت            │ Start ربات                │ در پس‌زمینه
                      ▼                        ▼                           ▼
        CPU Decode\xbrp.exe  ◄── pipe ──  Play\run_bot.py → Play.py     Prices\sbc_prices.py --loop
        (تصویر + ورودی کنسول)              │                              (قیمت‌ها از FUT.GG)
                                           ├─ Controller\xbox.py  → remotectl.py   (فرستادن دکمه)
                                           ├─ Founder\founder.py  → remotectl.py   (تصویر، OCR)
                                           ├─ Play\report.py      → Report\<کنسول>.log
                                           └─ Pannel\core.py                       (اکانت‌ها و وضعیت)

        Watchdog\live.py : هر ۳ ثانیه ربات‌ها را چک می‌کند؛ اگر یکی pause شد، ایجنت Claude را برای درست کردنش اجرا می‌کند.
```

---

## پوشه‌ها

| پوشه | کار | راهنمای کامل |
|---|---|---|
| `CPU Decode\` | ریموت آماده (`xbrp.exe`، `xbrp-multi.exe`) با DLLهای FFmpeg و OpenH264 | `CPU Decode\CLAUDE.md` |
| `Controller\` | ارسال دکمه: `xbox.py` (توابع `A()`، `Down()`، `wait()`…)، `remotectl.py`، ابزار `xbpad.exe`، سورس Go در `src\` | `Controller\README-FA.md` |
| `Founder\` | پیدا کردن تصویر و خواندن متن روی ریموت: کلاس `Screen` در `founder.py`، ابزار مختصات `pick.py`، تصویرهای نمونه در `Templates\` | `Founder\README-FA.md` |
| `Play\` | ربات SBC: `Play.py`، اجرا از پنل با `run_bot.py`، گزارش با `report.py` | `Play\README-FA.md` و `Play\CLAUDE.md` |
| `Pannel\` | پنل F2 (PySide6): `panel.py`، منطق مشترک `core.py`، ورود مایکروسافت `mslogin.py`، داده‌ها در `data\` | `Pannel\README-FA.md` |
| `Prices\` | قیمت لحظه‌ای کارت‌ها از FUT.GG برای هر ردیف CSV (`sbc_prices.py`) | `Prices\CLAUDE.md` |
| `Screenshot\` | `RemoteShot.exe`: اسکرین‌شات از ریموت (Ctrl+Alt+S) با مختصات آماده‌ی کد | `Screenshot\README-FA.md` |
| `Watchdog\` | پایش ربات‌ها و درست کردن خودکار گیرها (`live.py`، `wd.py`، تسک ویندوز) | `Watchdog\README-FA.md` |
| `Report\` | گزارش هر کنسول (`<کنسول>.log`) و عکس لحظه‌ی خطا (`shots\`) | `Report\README.txt` |
| `Football\` | آزمایشی: بازیکن ساده‌ی فوتبال با رادار بازی (`football_ai.py`) | توضیح بالای فایل |
| ریشه | `Marquee Matchups 1..4.csv`: لیست بازیکن‌های هر چالش | — |

---

## نصب روی یک سیستم جدید

### ۱. مسیر پوشه
چند فایل مسیر کامل پروژه را **ثابت** نوشته‌اند:

```
C:\Users\Reach\Desktop\New Remote
```

ساده‌ترین راه: پروژه را دقیقاً در همین مسیر بگذارید. اگر ممکن نیست، این مسیر را در این فایل‌ها عوض کنید:

| فایل | کجا |
|---|---|
| `Play\Play.py` | خط‌های `sys.path.insert` (بالای فایل، و قبل از `from report import` و `import core`) و مسیر `templates` در `Screen(...)` |
| `Play\report.py` | متغیر `pan` (دو جا) |
| `Pannel\remoteio.py` | `_CTRL` و `_FND` |
| `Pannel\core.py`، `Founder\founder.py` | جستجو برای `New Remote` |
| `Pannel\data\sbcs.json` | آدرس CSV هر SBC (از تب SBCs پنل هم عوض می‌شود) |

### ۲. پایتون و کتابخانه‌ها
پایتون **3.13** روی ویندوز. کتابخانه‌های لازم:

```
pip install opencv-python numpy pytesseract PySide6 pywin32 requests pyotp playwright
pip install winrt-runtime winrt-Windows.Media.Ocr winrt-Windows.Graphics.Imaging winrt-Windows.Storage.Streams winrt-Windows.Globalization winrt-Windows.Foundation winrt-Windows.Foundation.Collections
```

`req.txt` فهرست کامل کتابخانه‌های سیستم اصلی است. خیلی از آن‌ها برای این پروژه لازم نیستند.

### ۳. برنامه‌های بیرونی
- **Tesseract-OCR** در مسیر `C:\Program Files\Tesseract-OCR\`.
  اگر جای دیگری نصب شد، فقط `TESSERACT_EXE` در `Founder\founder.py` را عوض کنید.
- **بسته‌ی زبان English (en-US)** در تنظیمات ویندوز، برای OCR خود ویندوز.
- **ViGEmBus**: فقط اگر از روش `xinput` (دسته‌ی مجازی) استفاده می‌کنید.
- فایل‌های `.exe` را از آنتی‌ویروس یا SmartScreen مستثنا کنید.

### ۴. ورود و اکانت‌ها
فایل‌های ورود عمداً در گیت **نیستند** و روی سیستم جدید باید دوباره ساخته شوند:
- `CPU Decode\xbrp_token.json`: ورود حساب مایکروسافت ریموت (با اولین اجرای `xbrp.exe`).
- `Pannel\data\accounts.json` و `Pannel\tokens\`: در پنل، CSV اکانت‌ها را وارد کنید (نمونه: `Pannel\accounts-template.csv`).

---

## اجرا

1. **پنل:** روی `Pannel\run.bat` دوبار کلیک کنید (یا `python panel.py`).
   پنل `Prices\sbc_prices.py --loop` و `Watchdog\live.py` را خودش در پس‌زمینه روشن می‌کند.
2. **ریموت:** از تب Monitor پنل برای هر کنسول ریموت بگیرید. پنجره‌ی `xbrp` باز می‌شود و در `Controller\remotes\<کنسول>.json` ثبت می‌شود.
3. **SBCها:** در تب SBCs، ست‌ها و چالش‌ها را با فایل CSV هر کدام اضافه کنید و تیک Do را بزنید.
4. **ربات:** دکمه‌ی Start روی تایل کنسول. `Play\run_bot.py` فایل `Play.py` را تا آخر سلول `# %% Main` اجرا می‌کند.
   اگر ربات جایی گیر کند، pause می‌شود؛ دستی درستش کنید و Resume بزنید.

اجرای دستی برای تست: `Play.py` را در VS Code سلول‌به‌سلول (`#%%`) اجرا کنید.

---

## فایل‌های CSV هر چالش
هر ردیف یک بازیکن است، با فیلترهای Rarity، Region، Position، Club، League و Price.
ربات اول بازیکن را در Club جستجو می‌کند. اگر نبود، از Transfer Market می‌خرد. قیمت شروع را از `Prices\sbc_prices.json` برمی‌دارد و
اگر آن فایل قدیمی بود، از قیمت CSV استفاده می‌کند.

---

## مختصات
همه‌ی عددهای `x, y, w, h` در کد نسبت به **تصویر ریموت با اندازه‌ی 1280×720** هستند (گوشه‌ی بالا-چپ = 0,0).
اندازه و جای پنجره‌ی ریموت اثری ندارد. برای گرفتن مختصات از `Founder\pick.py` یا `Screenshot\RemoteShot.exe` استفاده کنید.

خلاصه‌ی توابع صفحه (`scr.find`، `scr.read`، `scr.see`، `scr.wait`…) در بالای `Play\Play.py` و در `Founder\README-FA.md` آمده است.

---

## گزارش‌ها و عیب‌یابی

| کجا | چه چیزی |
|---|---|
| `Report\<کنسول>.log` و `Report\shots\` | هر خطا، توقف و ادامه‌ی ربات، با عکس صفحه |
| `Play\run_bot.log` | خروجی آخرین اجرای ربات از پنل |
| `CPU Decode\xbrp.log` | گزارش ریموت |
| `Prices\prices.log` | گزارش ابزار قیمت |
| `Watchdog\Fixes.md` و `Watchdog\logs\` | کارهایی که Watchdog برای درست کردن گیرها انجام داده |

اگر روی سیستم جدید اجرا نشد، به ترتیب بررسی کنید: مسیر پوشه، نصب کتابخانه‌ها، Tesseract، زبان English ویندوز،
اجرا شدن `xbrp.exe` و معتبر بودن ورود. متن خطا معمولاً در `Play\run_bot.log` یا ترمینال هست.

---

## امنیت
رمز اکانت‌ها، کدهای Gauth و توکن‌های مایکروسافت در `Pannel\data\accounts.json`، `Pannel\tokens\` و
`CPU Decode\xbrp_token.json` هستند. این فایل‌ها را به کسی ندهید و در گیت نگذارید (`.gitignore` آن‌ها را کنار می‌گذارد).
