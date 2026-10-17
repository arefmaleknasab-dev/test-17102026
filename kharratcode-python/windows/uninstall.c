#define UNICODE
#define _UNICODE
#define WIN32_LEAN_AND_MEAN

#include <windows.h>
#include <shellapi.h>
#include <shlobj.h>
#include <wchar.h>

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR commandLine, int showCommand) {
    (void)instance;
    (void)previous;
    (void)commandLine;
    (void)showCommand;

    int ans = MessageBoxW(
        NULL,
        L"آیا مطمئن هستید که می‌خواهید نرم‌افزار خراط‌کد (KharratCode) را از ویندوز حذف کنید؟",
        L"حذف نرم‌افزار خراط‌کد (Uninstall KharratCode)",
        MB_YESNO | MB_ICONQUESTION | MB_RIGHT | MB_RTLREADING
    );
    if (ans != IDYES) {
        return 0;
    }

    /* حذف میانبر دسکتاپ */
    wchar_t desktop[MAX_PATH];
    if (SHGetSpecialFolderPathW(NULL, desktop, CSIDL_DESKTOPDIRECTORY, FALSE)) {
        wchar_t lnk[MAX_PATH];
        swprintf(lnk, MAX_PATH, L"%ls\\KharratCode.lnk", desktop);
        DeleteFileW(lnk);
    }

    /* حذف میانبر منوی استارت */
    wchar_t programs[MAX_PATH];
    if (SHGetSpecialFolderPathW(NULL, programs, CSIDL_PROGRAMS, FALSE)) {
        wchar_t start_lnk[MAX_PATH];
        swprintf(start_lnk, MAX_PATH, L"%ls\\KharratCode.lnk", programs);
        DeleteFileW(start_lnk);
    }

    /* حذف کلید رجیستری Add/Remove Programs */
    RegDeleteKeyW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\KharratCode");

    MessageBoxW(
        NULL,
        L"میانبرها و ثبت‌نام برنامه با موفقیت حذف شدند.\nپوشه برنامه در مسیر نصب قابل حذف است.",
        L"خراط‌کد (KharratCode)",
        MB_OK | MB_ICONINFORMATION | MB_RIGHT | MB_RTLREADING
    );
    return 0;
}
