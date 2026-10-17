#define UNICODE
#define _UNICODE
#define COBJMACROS

#include <windows.h>
#include <shellapi.h>
#include <shlobj.h>
#include <objbase.h>
#include <shobjidl.h>
#include <shlguid.h>
#include <wchar.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "payload_data.h"

/* بازگشایی فشرده‌سازی بلوک LZ4 استاندارد */
static int lz4_decompress_block(const uint8_t *src, size_t src_len, uint8_t *dst, size_t dst_cap) {
    size_t sp = 0;
    size_t dp = 0;
    while (sp < src_len) {
        uint8_t token = src[sp++];
        size_t lit_len = (size_t)(token >> 4);
        if (lit_len == 15) {
            uint8_t s;
            do {
                if (sp >= src_len) return -1;
                s = src[sp++];
                lit_len += s;
            } while (s == 255);
        }
        if (sp + lit_len > src_len || dp + lit_len > dst_cap) return -1;
        memcpy(dst + dp, src + sp, lit_len);
        sp += lit_len;
        dp += lit_len;
        if (sp >= src_len) break;

        if (sp + 2 > src_len) return -1;
        size_t offset = (size_t)src[sp] | ((size_t)src[sp + 1] << 8);
        sp += 2;
        if (offset == 0 || offset > dp) return -1;

        size_t match_len = (size_t)(token & 0x0F) + 4;
        if ((token & 0x0F) == 15) {
            uint8_t s;
            do {
                if (sp >= src_len) return -1;
                s = src[sp++];
                match_len += s;
            } while (s == 255);
        }
        if (dp + match_len > dst_cap) return -1;
        for (size_t i = 0; i < match_len; i++) {
            dst[dp + i] = dst[dp - offset + i];
        }
        dp += match_len;
    }
    return (dp == dst_cap) ? 0 : -1;
}

static void ensure_parent_dirs(const wchar_t *full_path) {
    wchar_t tmp[4096];
    wcscpy(tmp, full_path);
    for (wchar_t *p = tmp + 3; *p; p++) {
        if (*p == L'\\' || *p == L'/') {
            wchar_t ch = *p;
            *p = L'\0';
            CreateDirectoryW(tmp, NULL);
            *p = ch;
        }
    }
}

static int write_buffer_to_file(const wchar_t *path, const uint8_t *buf, size_t len) {
    ensure_parent_dirs(path);
    HANDLE h = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) {
        return 0;
    }
    size_t off = 0;
    while (off < len) {
        DWORD chunk = (len - off > 65536) ? 65536 : (DWORD)(len - off);
        DWORD written = 0;
        if (!WriteFile(h, buf + off, chunk, &written, NULL) || written != chunk) {
            CloseHandle(h);
            return 0;
        }
        off += written;
    }
    CloseHandle(h);
    return 1;
}

static void create_shortcut(const wchar_t *target_exe, const wchar_t *working_dir, const wchar_t *lnk_path, const wchar_t *desc) {
    IShellLinkW *psl = NULL;
    HRESULT hr = CoCreateInstance(&CLSID_ShellLink, NULL, CLSCTX_INPROC_SERVER, &IID_IShellLinkW, (LPVOID *)&psl);
    if (SUCCEEDED(hr) && psl != NULL) {
        psl->lpVtbl->SetPath(psl, target_exe);
        psl->lpVtbl->SetWorkingDirectory(psl, working_dir);
        psl->lpVtbl->SetDescription(psl, desc);
        psl->lpVtbl->SetIconLocation(psl, target_exe, 0);

        IPersistFile *ppf = NULL;
        hr = psl->lpVtbl->QueryInterface(psl, &IID_IPersistFile, (LPVOID *)&ppf);
        if (SUCCEEDED(hr) && ppf != NULL) {
            ppf->lpVtbl->Save(ppf, lnk_path, TRUE);
            ppf->lpVtbl->Release(ppf);
        }
        psl->lpVtbl->Release(psl);
    }
}

static void register_uninstaller(const wchar_t *install_dir, const wchar_t *exe_path, const wchar_t *uninst_path) {
    HKEY hKey;
    if (RegCreateKeyExW(
            HKEY_CURRENT_USER,
            L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\KharratCode",
            0, NULL, 0, KEY_WRITE, NULL, &hKey, NULL) == ERROR_SUCCESS) {
        const wchar_t *name = L"KharratCode — خراط‌کد (شبیه‌ساز خراطی CNC)";
        const wchar_t *ver = L"1.0.0";
        const wchar_t *pub = L"KharratCode Python Edition";
        RegSetValueExW(hKey, L"DisplayName", 0, REG_SZ, (const BYTE *)name, (DWORD)((wcslen(name) + 1) * sizeof(wchar_t)));
        RegSetValueExW(hKey, L"DisplayVersion", 0, REG_SZ, (const BYTE *)ver, (DWORD)((wcslen(ver) + 1) * sizeof(wchar_t)));
        RegSetValueExW(hKey, L"Publisher", 0, REG_SZ, (const BYTE *)pub, (DWORD)((wcslen(pub) + 1) * sizeof(wchar_t)));
        RegSetValueExW(hKey, L"InstallLocation", 0, REG_SZ, (const BYTE *)install_dir, (DWORD)((wcslen(install_dir) + 1) * sizeof(wchar_t)));
        RegSetValueExW(hKey, L"DisplayIcon", 0, REG_SZ, (const BYTE *)exe_path, (DWORD)((wcslen(exe_path) + 1) * sizeof(wchar_t)));
        RegSetValueExW(hKey, L"UninstallString", 0, REG_SZ, (const BYTE *)uninst_path, (DWORD)((wcslen(uninst_path) + 1) * sizeof(wchar_t)));
        DWORD no_mod = 1;
        RegSetValueExW(hKey, L"NoModify", 0, REG_DWORD, (const BYTE *)&no_mod, sizeof(DWORD));
        RegSetValueExW(hKey, L"NoRepair", 0, REG_DWORD, (const BYTE *)&no_mod, sizeof(DWORD));
        RegCloseKey(hKey);
    }
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR commandLine, int showCommand) {
    (void)instance;
    (void)previous;
    (void)showCommand;

    int silent = (commandLine && (strstr(commandLine, "/S") || strstr(commandLine, "/silent")));

    wchar_t local_appdata[MAX_PATH];
    if (!GetEnvironmentVariableW(L"LOCALAPPDATA", local_appdata, MAX_PATH)) {
        if (!SHGetSpecialFolderPathW(NULL, local_appdata, CSIDL_LOCAL_APPDATA, FALSE)) {
            wcscpy(local_appdata, L"C:\\KharratCode");
        }
    }

    wchar_t install_dir[MAX_PATH];
    swprintf(install_dir, MAX_PATH, L"%ls\\Programs\\KharratCode", local_appdata);

    if (!silent) {
        wchar_t prompt_msg[2048];
        swprintf(
            prompt_msg,
            2048,
            L"نصب نرم‌افزار خراط‌کد (KharratCode v1.0.0 — نسخه پایتون)\n"
            L"شبیه‌ساز و جی‌کدساز خراطی دومحور CNC (کاملاً آفلاین)\n\n"
            L"مسیر نصب:\n%ls\n\n"
            L"امکانات بسته نصبی:\n"
            L"• رابط کاربری دقیق با فونت‌های فارسی توکار (بدون نیاز به اینترنت)\n"
            L"• موتور کامل پایتون (lathe, sketch, dxf, ai, server)\n"
            L"• ایجاد میانبر روی دسکتاپ و منوی استارت ویندوز\n\n"
            L"آیا مایل به نصب برنامه هستید؟",
            install_dir
        );
        int ans = MessageBoxW(
            NULL,
            prompt_msg,
            L"نصب خراط‌کد — KharratCode Setup",
            MB_YESNO | MB_ICONINFORMATION | MB_RIGHT | MB_RTLREADING
        );
        if (ans != IDYES) {
            return 0;
        }
    }

    CreateDirectoryW(install_dir, NULL);

    for (size_t i = 0; i < PAYLOAD_FILES_COUNT; i++) {
        const PayloadFile *pf = &PAYLOAD_FILES[i];
        uint8_t *raw = (uint8_t *)malloc(pf->orig_size ? pf->orig_size : 1);
        if (!raw) {
            MessageBoxW(NULL, L"خطا در تخصیص حافظه هنگام نصب.", L"KharratCode Setup", MB_OK | MB_ICONERROR);
            return 1;
        }
        if (pf->orig_size > 0) {
            if (lz4_decompress_block(pf->data, pf->comp_size, raw, pf->orig_size) != 0) {
                free(raw);
                MessageBoxW(NULL, L"خطا در بازگشایی فایل‌های نصبی.", L"KharratCode Setup", MB_OK | MB_ICONERROR);
                return 1;
            }
        }
        wchar_t out_path[4096];
        swprintf(out_path, 4096, L"%ls\\%ls", install_dir, pf->rel_path);
        int ok = write_buffer_to_file(out_path, raw, pf->orig_size);
        free(raw);
        if (!ok) {
            wchar_t err[4200];
            swprintf(err, 4200, L"خطا در نوشتن فایل:\n%ls", out_path);
            MessageBoxW(NULL, err, L"KharratCode Setup", MB_OK | MB_ICONERROR);
            return 1;
        }
    }

    wchar_t exe_path[4096];
    swprintf(exe_path, 4096, L"%ls\\KharratCode.exe", install_dir);
    wchar_t uninst_path[4096];
    swprintf(uninst_path, 4096, L"%ls\\Uninstall-KharratCode.exe", install_dir);

    /* ایجاد میانبر روی دسکتاپ و منوی استارت */
    CoInitialize(NULL);
    wchar_t desktop[MAX_PATH];
    if (SHGetSpecialFolderPathW(NULL, desktop, CSIDL_DESKTOPDIRECTORY, FALSE)) {
        wchar_t lnk[MAX_PATH];
        swprintf(lnk, MAX_PATH, L"%ls\\KharratCode.lnk", desktop);
        create_shortcut(exe_path, install_dir, lnk, L"خراط‌کد — شبیه‌ساز و جی‌کدساز خراطی دومحور CNC");
    }
    wchar_t programs[MAX_PATH];
    if (SHGetSpecialFolderPathW(NULL, programs, CSIDL_PROGRAMS, FALSE)) {
        wchar_t start_lnk[MAX_PATH];
        swprintf(start_lnk, MAX_PATH, L"%ls\\KharratCode.lnk", programs);
        create_shortcut(exe_path, install_dir, start_lnk, L"خراط‌کد — شبیه‌ساز و جی‌کدساز خراطی دومحور CNC");
    }
    CoUninitialize();

    register_uninstaller(install_dir, exe_path, uninst_path);

    if (!silent) {
        int run_now = MessageBoxW(
            NULL,
            L"نصب نرم‌افزار خراط‌کد (KharratCode) با موفقیت به پایان رسید!\n"
            L"میانبر برنامه روی دسکتاپ و منوی استارت ایجاد شد.\n\n"
            L"آیا می‌خواهید نرم‌افزار همین حالا اجرا شود؟",
            L"پایان نصب — KharratCode Setup",
            MB_YESNO | MB_ICONINFORMATION | MB_RIGHT | MB_RTLREADING
        );
        if (run_now == IDYES) {
            ShellExecuteW(NULL, L"open", exe_path, NULL, install_dir, SW_SHOWNORMAL);
        }
    }

    return 0;
}
