# Watchdog — ایجنت لوکال برای ریموت‌ها

هر ۱۰ دقیقه Task Scheduler ویندوز (تسک «F2 Watchdog») فایل run_hidden.vbs را بی‌پنجره اجرا می‌کند:

1. `python wd.py need` همه‌ی ریموت‌های باز را چک می‌کند (بدون هزینه). اگر همه سالم‌اند تمام.
2. اگر ریموتی pause شده یا ربات‌ش مرده (خطای کد، قطع ریموت) Claude (مدل Opus، بدون پنجره) با دستورهای AGENT.md:
   عکس می‌گیرد، نگاه می‌کند، چند دکمه می‌زند تا صفحه درست شود، Resume/Start می‌زند و نتیجه را ثبت می‌کند.
3. اگر مطمئن نباشد دست نمی‌زند و «NEEDS HUMAN» ثبت می‌کند؛ تا وقتی گزارش آن ریموت تغییر نکند دوباره سراغش نمی‌رود.

ریموت‌هایی که دست نمی‌خورند: «Stop» زده‌شده توسط شما، همه‌چیز تمام‌شده، منتظر Start (wait).

## فایل‌ها
- Fixes.md — مشکلات و کارهایی که ایجنت کرد (برای خواندن شما)
- fixes.jsonl — همان، برای ایجنت (از راه‌حل‌های قبلی یاد می‌گیرد)
- logs\watchdog.log — هر ۱۰ دقیقه یک خط؛ logs\run_*.md — گزارش کامل هر بار که ایجنت کار کرد
- snaps\ — عکس‌هایی که ایجنت گرفت
- AGENT.md — دستورالعمل ایجنت (دانسته‌های صفحه‌ها را این‌جا اضافه کنید)

## دستورها
    python wd.py status        وضعیت همه
    python wd.py snap D13      عکس
    python wd.py press D13 b a دکمه‌ها
    python wd.py resume D13    مثل Start/Resume پنل

## خاموش / روشن
    schtasks /Change /TN "F2 Watchdog" /DISABLE
    schtasks /Change /TN "F2 Watchdog" /ENABLE
    schtasks /Delete /TN "F2 Watchdog" /F
