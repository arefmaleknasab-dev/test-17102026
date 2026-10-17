# خراط‌کد (KharratCode Python Edition)

بازنویسی کامل نرم‌افزار شبیه‌ساز و جی‌کدساز خراطی دومحور CNC به زبان پایتون با حفظ ۱۰۰٪ دقیق رابط کاربری و قابلیت اجرا به صورت کاملاً آفلاین در ویندوز.

## اجرای برنامه

```bash
# اجرای پنجره دسکتاپ
python main.py

# اجرای سرور روی پورت مشخص
python main.py --server --port 8765

# تولید جی‌کد و DXF از خط فرمان
python main.py --preset leg --out-gcode leg.nc --out-dxf leg.dxf
```

## بازسازی فایل نصبی ویندوز (`KharratCode-Windows-Setup.exe`)

```bash
python scripts/build_windows_installer.py
```
