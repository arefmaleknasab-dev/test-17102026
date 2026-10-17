# خراط‌کد (KharratCode) — نسخه پایتون و نصبی ویندوز

شبیه‌ساز و تولیدکننده جی‌کد (G-Code) برای خراطی دومحور CNC — بازنویسی‌شده با **پایتون (Python)** با حفظ ۱۰۰٪ دقیق رابط کاربری، فونت‌های فارسی توکار و اجرای کاملاً آفلاین روی ویندوز بدون نیاز به اینترنت.

---

## ۱. فایل‌های نصبی و اجرایی ویندوز (بدون نیاز به اینترنت و بدون نیاز به پیش‌نیاز)

در این ریپازیتوری فایل‌های نصبی و پرتابل ویندوز قرار داده شده‌اند:

1. **`KharratCode-Windows-Setup.exe`** (در ریشه مخزن و در پوشه پروژه):
   - **فایل نصبی مستقل ویندوز (Standalone Installer)** با حجم حدود ۱.۲ مگابایت.
   - بدون نیاز به اینترنت یا هیچ پیش‌نیاز نصبی روی ویندوز ۱۰ و ۱۱ اجرا می‌شود.
   - برنامه، رابط کاربری آفلاین (به همراه فونت‌های فارسی وزیرمتن، لاله‌زار و JetBrains Mono توکار) و سورس کامل موتور پایتون را در مسیر `%LOCALAPPDATA%\Programs\KharratCode` نصب می‌کند.
   - به صورت خودکار **میانبر دسکتاپ (Desktop Shortcut)** و **میانبر منوی استارت (Start Menu)** می‌سازد و در بخش برنامه‌های ویندوز (Add or Remove Programs) ثبت می‌شود.
2. **`test-arena-01a10cb3-test/test-arena-01a10cb3-test/KharratCode-Windows10-Portable.zip`**:
   - نسخه پرتابل ویندوز شامل `KharratCode.exe`، `KharratCode-Windows-Setup.exe`، `KharratCode.html`، `run-python.bat` و پوشه کامل `python/`.

---

## ۲. ساختار پروژه پایتون (`kharratcode-python/`)

تمامی ماژول‌های محاسباتی، هندسی و سرور برنامه به صورت کامل در پایتون بازنویسی شده‌اند:

- **`kharratcode/lathe.py`**: موتور کامل محاسبات مسیر ابزار و تولید جی‌کد خراطی دومحور (`generate`، استراتژی‌های `round`, `face`, `rough-d`, `rough-z`, `copy`, `offset`, `finish`, `bottom`, `inner-rough`, `inner-offset`, `inner-finish`، حالت‌های یک‌طرفه، زیگزاگ و ناحیه‌ای، محاسبات هلدر اول و دوم، پس‌پردازنده‌های `modal` و `std`، و ویرایشگر مسیر جی‌کد).
- **`kharratcode/sketch.py`**: موتور هندسی اسکچ دوبعدی (خط، منحنی درجه ۲ و ۳ بزیه، کمان سه‌نقطه‌ای، اسنپ هوشمند، تقاطع‌ها، زنجیره‌سازی پروفیل و تفکیک شاخه داخلی/خارجی کاسه `split_chain_at`).
- **`kharratcode/dxf.py`**: تولیدکننده خروجی استاندارد `DXF` (`AC1015` / `LWPOLYLINE`) به تفکیک لایه‌های عملیات و مسیر برش یکپارچه (`CUTPATH`).
- **`kharratcode/ai.py`**: پارسر و مبدل فایل‌های برداری Adobe Illustrator (`AI` / `EPS`) به المان‌های اسکچ.
- **`kharratcode/server.py`**: سرور محلی پایتون (بدون وابستگی خارجی و صرفاً با کتابخانه استاندارد پایتون) برای سرو رابط کاربری آفلاین و ارائه APIهای محاسباتی (`/api/generate`, `/api/dxf`, `/api/ai/parse`, `/api/sketch/flatten`, `/api/project/save`).
- **`kharratcode/app.py` و `main.py`**: اجراکننده دسکتاپ (پشتیبانی از پنجره بومی دسکتاپ با `pywebview` یا حالت اپلیکیشن دسکتاپ ویندوز `--app`) و رابط خط فرمان (CLI).
- **`windows/` و `scripts/build_windows_installer.py`**: سورس کد C لانچر، حذف‌کننده (Uninstaller) و نصاب گرافیکی ویندوز (`Setup.exe`) به همراه اسکریپت ساخت خودکار.

---

## ۳. نحوه اجرا با پایتون

```bash
cd kharratcode-python

# اجرای برنامه دسکتاپ
python main.py

# اجرای سرور محلی روی پورت دلخواه
python main.py --server --host 0.0.0.0 --port 5173

# تولید مستقیم جی‌کد و DXF از خط فرمان با موتور پایتون
python main.py --preset bowl-both --format modal --out-gcode bowl.nc --out-dxf bowl.dxf

# اجرای تست‌های واحد موتور پایتون
PYTHONPATH=. python -m unittest discover -s tests -v
```
