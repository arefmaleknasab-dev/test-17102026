#!/usr/bin/env python3
"""
اسکریپت ساخت فایل نصبی مستقل ویندوز (KharratCode-Windows-Setup.exe) و نسخه پرتابل (KharratCode-Windows10-Portable.zip)
"""

from __future__ import annotations
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import List, Tuple


def lz4_compress_block(src: bytes) -> bytes:
    """فشرده‌ساز استاندارد بلوک LZ4 با دیکشنری جدول هش (تضمین ۱۰۰٪ سازگاری با دی‌کامپرسور C)."""
    n = len(src)
    if n == 0:
        return b""
    out = bytearray()
    ht = [-1] * 65536
    anchor = 0
    ip = 0
    limit = n - 12  # حاشیه امن انتهای بلوک طبق استاندارد LZ4

    def emit_len(val: int) -> None:
        while val >= 255:
            out.append(255)
            val -= 255
        out.append(val)

    while ip < limit:
        seq = struct.unpack_from("<I", src, ip)[0]
        h = ((seq * 2654435761) >> 16) & 0xFFFF
        ref = ht[h]
        ht[h] = ip

        if ref < 0 or (ip - ref) > 65535 or (ip - ref) == 0 or src[ref : ref + 4] != src[ip : ip + 4]:
            ip += 1
            continue

        # تطابق ۴ بایتی پیدا شد
        lit_len = ip - anchor
        offset = ip - ref
        match_len = 4
        while ip + match_len < n - 5 and src[ref + match_len] == src[ip + match_len]:
            match_len += 1

        ml_token = min(match_len - 4, 15)
        ll_token = min(lit_len, 15)
        out.append((ll_token << 4) | ml_token)

        if lit_len >= 15:
            emit_len(lit_len - 15)
        out.extend(src[anchor : anchor + lit_len])

        out.append(offset & 0xFF)
        out.append((offset >> 8) & 0xFF)

        if match_len - 4 >= 15:
            emit_len(match_len - 4 - 15)

        ip += match_len
        anchor = ip

    # لیترال‌های پایانی
    lit_len = n - anchor
    ll_token = min(lit_len, 15)
    out.append(ll_token << 4)
    if lit_len >= 15:
        emit_len(lit_len - 15)
    out.extend(src[anchor:])
    return bytes(out)


def lz4_decompress_block_py(src: bytes, orig_size: int) -> bytes:
    """دی‌کامپرسور مرجع پایتون برای تست صحت بایت‌به‌بایت قبل از کامپایل."""
    dst = bytearray()
    sp = 0
    src_len = len(src)
    while sp < src_len:
        token = src[sp]
        sp += 1
        lit_len = token >> 4
        if lit_len == 15:
            while True:
                s = src[sp]
                sp += 1
                lit_len += s
                if s != 255:
                    break
        dst.extend(src[sp : sp + lit_len])
        sp += lit_len
        if sp >= src_len:
            break
        offset = src[sp] | (src[sp + 1] << 8)
        sp += 2
        match_len = (token & 0x0F) + 4
        if (token & 0x0F) == 15:
            while True:
                s = src[sp]
                sp += 1
                match_len += s
                if s != 255:
                    break
        start = len(dst) - offset
        for i in range(match_len):
            dst.append(dst[start + i])
    assert len(dst) == orig_size, f"Size mismatch: {len(dst)} != {orig_size}"
    return bytes(dst)


def find_zig_cc() -> List[str]:
    if Path("/tmp/zig-env/bin/python").is_file():
        return ["/tmp/zig-env/bin/python", "-m", "ziglang", "cc"]
    zig = shutil.which("zig")
    if zig:
        return [zig, "cc"]
    return [sys.executable, "-m", "ziglang", "cc"]


def normalize_pe_timestamp(exe_path: Path) -> None:
    data = bytearray(exe_path.read_bytes())
    if data[:2] != b"MZ":
        return
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_offset : pe_offset + 4] == b"PE\x00\x00":
        struct.pack_into("<I", data, pe_offset + 8, 0)
        exe_path.write_bytes(bytes(data))


def build_all() -> None:
    py_root = Path(__file__).resolve().parent.parent
    repo_root = py_root.parent
    sub_repo = repo_root / "test-arena-01a10cb3-test" / "test-arena-01a10cb3-test"
    web_app_dir = sub_repo / "cnc-lathe-simulation-software"

    ui_html = py_root / "kharratcode" / "ui" / "KharratCode.html"
    dist_html = web_app_dir / "dist" / "index.html"
    if dist_html.is_file():
        ui_html.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dist_html, ui_html)

    if not ui_html.is_file():
        raise FileNotFoundError(f"Offline UI bundle not found at {ui_html}")

    zig_cc = find_zig_cc()
    win_src = py_root / "windows"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        launcher_exe = tmp_dir / "KharratCode.exe"
        uninstall_exe = tmp_dir / "Uninstall-KharratCode.exe"

        print("Compiling KharratCode.exe (Windows Launcher)...")
        subprocess.run(
            zig_cc
            + [
                "-target",
                "x86_64-windows-gnu",
                "-Os",
                "-s",
                "-Wl,--subsystem,windows",
                "-o",
                str(launcher_exe),
                str(win_src / "launcher.c"),
                "-lshell32",
                "-luser32",
            ],
            check=True,
        )
        normalize_pe_timestamp(launcher_exe)

        print("Compiling Uninstall-KharratCode.exe...")
        subprocess.run(
            zig_cc
            + [
                "-target",
                "x86_64-windows-gnu",
                "-Os",
                "-s",
                "-Wl,--subsystem,windows",
                "-o",
                str(uninstall_exe),
                str(win_src / "uninstall.c"),
                "-lshell32",
                "-luser32",
                "-ladvapi32",
            ],
            check=True,
        )
        normalize_pe_timestamp(uninstall_exe)

        run_python_bat = (
            "@echo off\r\n"
            "chcp 65001 >nul\r\n"
            "cd /d \"%~dp0\"\r\n"
            "where pythonw >nul 2>nul\r\n"
            "if %ERRORLEVEL% EQU 0 (\r\n"
            "    start \"\" pythonw \"%~dp0python\\main.py\"\r\n"
            ") else (\r\n"
            "    start \"\" \"%~dp0KharratCode.exe\"\r\n"
            ")\r\n"
        ).encode("utf-8")

        readme_txt = (
            "KharratCode v1.0.0 — Python Edition (Windows Offline Desktop & Installer)\r\n"
            "=========================================================================\r\n\r\n"
            "فارسی:\r\n"
            "------\r\n"
            "۱. برای نصب کامل در ویندوز (همراه با میانبر دسکتاپ و منوی استارت):\r\n"
            "   فایل KharratCode-Windows-Setup.exe را اجرا کنید.\r\n\r\n"
            "۲. برای اجرای پرتابل (بدون نصب):\r\n"
            "   فایل KharratCode.exe را اجرا کنید.\r\n\r\n"
            "۳. برای اجرا مستقیم با مفسر پایتون:\r\n"
            "   فایل run-python.bat یا دستور python python\\main.py را اجرا کنید.\r\n\r\n"
            "نرم‌افزار به صورت ۱۰۰٪ آفلاین کار می‌کند و تمام فونت‌های فارسی و موتور محاسباتی\r\n"
            "درون بسته تعبیه شده‌اند.\r\n"
        ).encode("utf-8")

        # لیست فایل‌های نصبی (مسیر نسبی در پوشه نصب ویندوز -> بایت‌های فایل)
        files_to_pack: List[Tuple[str, bytes]] = [
            ("KharratCode.exe", launcher_exe.read_bytes()),
            ("Uninstall-KharratCode.exe", uninstall_exe.read_bytes()),
            ("KharratCode.html", ui_html.read_bytes()),
            ("run-python.bat", run_python_bat),
            ("README.txt", readme_txt),
            ("python\\main.py", (py_root / "main.py").read_bytes()),
            ("python\\pyproject.toml", (py_root / "pyproject.toml").read_bytes()),
            ("python\\requirements.txt", (py_root / "requirements.txt").read_bytes()),
            ("python\\KharratCode.spec", (py_root / "KharratCode.spec").read_bytes()),
            ("python\\kharratcode\\__init__.py", (py_root / "kharratcode" / "__init__.py").read_bytes()),
            ("python\\kharratcode\\lathe.py", (py_root / "kharratcode" / "lathe.py").read_bytes()),
            ("python\\kharratcode\\sketch.py", (py_root / "kharratcode" / "sketch.py").read_bytes()),
            ("python\\kharratcode\\dxf.py", (py_root / "kharratcode" / "dxf.py").read_bytes()),
            ("python\\kharratcode\\ai.py", (py_root / "kharratcode" / "ai.py").read_bytes()),
            ("python\\kharratcode\\server.py", (py_root / "kharratcode" / "server.py").read_bytes()),
            ("python\\kharratcode\\app.py", (py_root / "kharratcode" / "app.py").read_bytes()),
        ]

        header_path = tmp_dir / "payload_data.h"
        with header_path.open("w", encoding="utf-8") as hf:
            hf.write("#pragma once\n#include <stdint.h>\n#include <stddef.h>\n\n")
            hf.write("typedef struct {\n")
            hf.write("    const wchar_t *rel_path;\n")
            hf.write("    const uint8_t *data;\n")
            hf.write("    size_t comp_size;\n")
            hf.write("    size_t orig_size;\n")
            hf.write("} PayloadFile;\n\n")

            meta_rows: List[Tuple[str, str, int, int]] = []
            total_orig = 0
            total_comp = 0
            for idx, (rel_path, raw_bytes) in enumerate(files_to_pack):
                comp = lz4_compress_block(raw_bytes)
                # تست صحت بازگشایی
                check = lz4_decompress_block_py(comp, len(raw_bytes))
                assert check == raw_bytes, f"Verification failed for {rel_path}"
                total_orig += len(raw_bytes)
                total_comp += len(comp)

                arr_name = f"FILE_DATA_{idx}"
                hex_items = ", ".join(f"0x{b:02x}" for b in comp)
                hf.write(f"static const uint8_t {arr_name}[] = {{ {hex_items} }};\n\n")
                c_rel = rel_path.replace("\\", "\\\\")
                meta_rows.append((c_rel, arr_name, len(comp), len(raw_bytes)))

            hf.write(f"#define PAYLOAD_FILES_COUNT {len(meta_rows)}\n")
            hf.write("static const PayloadFile PAYLOAD_FILES[PAYLOAD_FILES_COUNT] = {\n")
            for c_rel, arr_name, c_len, o_len in meta_rows:
                hf.write(f'    {{ L"{c_rel}", {arr_name}, {c_len}ULL, {o_len}ULL }},\n')
            hf.write("};\n")

        print(f"Packed {len(files_to_pack)} files: {total_orig:,} bytes -> {total_comp:,} bytes compressed")

        setup_exe = repo_root / "KharratCode-Windows-Setup.exe"
        print("Compiling KharratCode-Windows-Setup.exe...")
        subprocess.run(
            zig_cc
            + [
                "-target",
                "x86_64-windows-gnu",
                "-Os",
                "-s",
                f"-I{tmp_dir}",
                "-Wl,--subsystem,windows",
                "-o",
                str(setup_exe),
                str(win_src / "setup.c"),
                "-luser32",
                "-lshell32",
                "-lole32",
                "-luuid",
                "-ladvapi32",
            ],
            check=True,
        )
        normalize_pe_timestamp(setup_exe)

        # کپی فایل نصبی در پوشه پروژه اصلی نیز برای دسترسی راحت‌تر
        if sub_repo.is_dir():
            shutil.copy2(setup_exe, sub_repo / "KharratCode-Windows-Setup.exe")

        # بروزرسانی فایل ZIP پرتابل ویندوز
        portable_zip = sub_repo / "KharratCode-Windows10-Portable.zip"
        pkg_name = "KharratCode-Windows10-Portable"
        with zipfile.ZipFile(portable_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for rel_path, raw_bytes in files_to_pack:
                arcname = f"{pkg_name}/{rel_path.replace(chr(92), '/')}"
                zi = zipfile.ZipInfo(arcname, date_time=(2026, 10, 17, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = 0o644 << 16
                zf.writestr(zi, raw_bytes)
            # قرار دادن خود Setup.exe نیز درون ZIP پرتابل
            zi_setup = zipfile.ZipInfo(f"{pkg_name}/KharratCode-Windows-Setup.exe", date_time=(2026, 10, 17, 0, 0, 0))
            zi_setup.compress_type = zipfile.ZIP_DEFLATED
            zi_setup.external_attr = 0o755 << 16
            zf.writestr(zi_setup, setup_exe.read_bytes())

        print(f"Created installer: {setup_exe} ({setup_exe.stat().st_size:,} bytes)")
        print(f"Updated portable archive: {portable_zip} ({portable_zip.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build_all()
