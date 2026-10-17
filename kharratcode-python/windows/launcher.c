#define UNICODE
#define _UNICODE
#define WIN32_LEAN_AND_MEAN

#include <windows.h>
#include <shellapi.h>
#include <wchar.h>

static int file_exists(const wchar_t *path) {
    DWORD attr = GetFileAttributesW(path);
    return (attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY));
}

static void get_exe_dir(wchar_t *dir_out, size_t max_len) {
    DWORD len = GetModuleFileNameW(NULL, dir_out, (DWORD)max_len);
    if (len == 0 || len >= (DWORD)max_len) {
        dir_out[0] = L'\0';
        return;
    }
    wchar_t *slash = wcsrchr(dir_out, L'\\');
    if (slash) {
        slash[1] = L'\0';
    } else {
        dir_out[0] = L'\0';
    }
}

static int find_edge_exe(wchar_t *edge_out, size_t max_len) {
    const wchar_t *env_names[] = { L"ProgramFiles(x86)", L"ProgramFiles", L"LOCALAPPDATA" };
    for (int i = 0; i < 3; i++) {
        wchar_t base[MAX_PATH];
        DWORD n = GetEnvironmentVariableW(env_names[i], base, MAX_PATH);
        if (n > 0 && n < MAX_PATH) {
            swprintf(edge_out, max_len, L"%ls\\Microsoft\\Edge\\Application\\msedge.exe", base);
            if (file_exists(edge_out)) {
                return 1;
            }
        }
    }
    return 0;
}

static int try_launch_python_backend(const wchar_t *base_dir) {
    wchar_t main_py[4096];
    swprintf(main_py, 4096, L"%lskharratcode-python\\main.py", base_dir);
    if (!file_exists(main_py)) {
        swprintf(main_py, 4096, L"%lspython\\main.py", base_dir);
    }
    if (!file_exists(main_py)) {
        swprintf(main_py, 4096, L"%lsmain.py", base_dir);
    }
    if (!file_exists(main_py)) {
        return 0;
    }

    /* بررسی وجود pythonw.exe در مسیر سیستم */
    wchar_t pythonw_path[MAX_PATH];
    DWORD found = SearchPathW(NULL, L"pythonw.exe", NULL, MAX_PATH, pythonw_path, NULL);
    if (found == 0 || found >= MAX_PATH) {
        return 0;
    }

    wchar_t cmd[8192];
    swprintf(cmd, 8192, L"\"%ls\" \"%ls\"", pythonw_path, main_py);

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (CreateProcessW(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, base_dir, &si, &pi)) {
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return 1;
    }
    return 0;
}

static void path_to_file_url(const wchar_t *win_path, wchar_t *url_out, size_t max_len) {
    wcscpy(url_out, L"file:///");
    size_t pos = wcslen(url_out);
    for (size_t i = 0; win_path[i] != L'\0' && pos + 4 < max_len; i++) {
        if (win_path[i] == L'\\') {
            url_out[pos++] = L'/';
        } else if (win_path[i] == L' ') {
            url_out[pos++] = L'%';
            url_out[pos++] = L'2';
            url_out[pos++] = L'0';
        } else {
            url_out[pos++] = win_path[i];
        }
    }
    url_out[pos] = L'\0';
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR commandLine, int showCommand) {
    (void)instance;
    (void)previous;
    (void)commandLine;
    (void)showCommand;

    wchar_t base_dir[4096];
    get_exe_dir(base_dir, 4096);
    if (base_dir[0] == L'\0') {
        return 1;
    }

    /* ۱. اگر مفسر پایتون در سیستم موجود باشد، نسخه کامل پایتون اجرا می‌شود */
    if (try_launch_python_backend(base_dir)) {
        return 0;
    }

    /* ۲. اجرای ۱۰۰٪ آفلاین و بدون نیاز به پیش‌نیاز در پنجره دسکتاپ ویندوز */
    wchar_t html_path[4096];
    swprintf(html_path, 4096, L"%lsKharratCode.html", base_dir);
    if (!file_exists(html_path)) {
        swprintf(html_path, 4096, L"%lskharratcode\\ui\\KharratCode.html", base_dir);
    }
    if (!file_exists(html_path)) {
        swprintf(html_path, 4096, L"%lspython\\kharratcode\\ui\\KharratCode.html", base_dir);
    }

    if (!file_exists(html_path)) {
        MessageBoxW(
            NULL,
            L"فایل رابط کاربری KharratCode.html یافت نشد.\nلطفاً تمام فایل‌های برنامه را در کنار یکدیگر نگه دارید یا مجدداً فایل نصبی را اجرا کنید.",
            L"خراط‌کد (KharratCode)",
            MB_OK | MB_ICONERROR | MB_RIGHT | MB_RTLREADING
        );
        return 1;
    }

    /* باز کردن در پنجره اختصاصی دسکتاپ (App Mode) در صورت وجود Microsoft Edge */
    wchar_t edge_exe[MAX_PATH];
    if (find_edge_exe(edge_exe, MAX_PATH)) {
        wchar_t file_url[8192];
        path_to_file_url(html_path, file_url, 8192);
        wchar_t args[8500];
        swprintf(args, 8500, L"--app=\"%ls\" --window-size=1440,900", file_url);
        HINSTANCE r = ShellExecuteW(NULL, L"open", edge_exe, args, base_dir, SW_SHOWNORMAL);
        if ((INT_PTR)r > 32) {
            return 0;
        }
    }

    /* بازگشتی: باز کردن مستقیم در مرورگر پیش‌فرض ویندوز به صورت آفلاین */
    HINSTANCE result = ShellExecuteW(NULL, L"open", html_path, NULL, base_dir, SW_SHOWNORMAL);
    if ((INT_PTR)result <= 32) {
        MessageBoxW(
            NULL,
            L"ویندوز نتوانست پنجره برنامه را باز کند.",
            L"خراط‌کد (KharratCode)",
            MB_OK | MB_ICONERROR
        );
        return 1;
    }
    return 0;
}
