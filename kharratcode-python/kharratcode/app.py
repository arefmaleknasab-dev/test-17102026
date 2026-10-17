"""
اجراکننده دسکتاپ و خط فرمان خراط‌کد (KharratCode Desktop Application)
پشتیبانی از:
۱) پنجره بومی دسکتاپ با pywebview (در صورت نصب بودن)
۲) پنجره بومی دسکتاپ ویندوز با Microsoft Edge App Mode (--app) بدون نیاز به پیش‌نیاز اضافه
۳) اجرای سرور محلی و مرورگر پیش‌فرض
۴) تولید جی‌کد و DXF از خط فرمان (CLI)
"""

from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import List, Optional

from . import __version__
from .dxf import build_dxf
from .lathe import PRESETS, STRATEGIES, generate, make_ops, normalize_params, preset_points
from .server import KharratCodeRequestHandler, ThreadingHTTPServer, start_background_server
from .sketch import (
    SPoint,
    branch_path_points,
    branch_points,
    chain_polyline,
    order_chain,
    sketch_from_points,
    sketch_from_wall,
    split_chain_at,
)

APP_TITLE = "خراط‌کد — شبیه‌ساز و جی‌کدساز خراطی دومحور CNC"


def _find_windows_app_browser() -> Optional[str]:
    """یافتن مرورگر Edge یا Chrome روی ویندوز برای باز کردن پنجره دسکتاپ مستقل (--app)."""
    if sys.platform != "win32":
        return None
    candidates: List[str] = []
    for env_key in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env_key)
        if not base:
            continue
        candidates.extend(
            [
                os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
            ]
        )
    for c in candidates:
        if os.path.isfile(c):
            return c
    for cmd in ("msedge", "chrome"):
        found = shutil.which(cmd)
        if found:
            return found
    return None


def launch_desktop_window(url: str) -> None:
    """باز کردن رابط کاربری در پنجره دسکتاپ ویندوز."""
    # ۱. تلاش برای استفاده از pywebview در صورت نصب بودن
    try:
        import webview  # type: ignore

        webview.create_window(
            APP_TITLE,
            url,
            width=1440,
            height=900,
            min_size=(1024, 680),
            text_select=True,
        )
        webview.start()
        return
    except ImportError:
        pass

    # ۲. در ویندوز: استفاده از حالت اپلیکیشن دسکتاپ Edge/Chrome (--app)
    browser_exe = _find_windows_app_browser()
    if browser_exe:
        proc = subprocess.Popen(
            [
                browser_exe,
                f"--app={url}",
                "--window-size=1440,900",
                "--disable-extensions",
            ]
        )
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
        return

    # ۳. بازگشتی: مرورگر پیش‌فرض سیستم
    webbrowser.open(url)
    print(f"KharratCode is running at {url} (Press Ctrl+C to stop)")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass


def run_cli_preset(preset_id: str, output_gcode: Optional[str], output_dxf: Optional[str], fmt: str = "modal") -> int:
    """تولید مستقیم جی‌کد و DXF برای یکی از پیش‌تنظیم‌ها از طریق موتور پایتون."""
    preset = next((p for p in PRESETS if p["id"] == preset_id), None)
    if preset is None:
        valid = ", ".join(p["id"] for p in PRESETS)
        print(f"Error: Preset '{preset_id}' not found. Valid presets: {valid}", file=sys.stderr)
        return 1

    strat_id = preset.get("strategy", "g71")
    strat = next((s for s in STRATEGIES if s["id"] == strat_id), STRATEGIES[0])
    params = normalize_params(
        {
            "blankD": preset["blankD"],
            "blankL": preset["blankL"],
            "blankShape": preset["shape"],
            "format": fmt,
            "ops": [o.to_dict() for o in make_ops(strat["types"])],
            "split": {
                "enabled": bool(preset.get("split")),
                "z": preset["split"]["z"] if preset.get("split") else 90.0,
                "r": preset["split"]["r"] if preset.get("split") else 68.0,
            },
        }
    )

    pts = preset_points(preset)
    inner_pts = None
    outer_finish_pts = None
    if preset.get("wall") and preset.get("split"):
        wall_dicts = [{"z": w[0], "r": w[1], "smooth": w[2]} for w in preset["wall"]]
        segs = sketch_from_wall(wall_dicts)
        chain = order_chain(segs)
        poly = chain_polyline(chain)
        sp = split_chain_at(poly, SPoint(z=float(preset["split"]["z"]), r=float(preset["split"]["r"])))
        blank_r = params.blankD / 2.0
        from .lathe import PPoint

        pts = [PPoint.from_dict(p) for p in branch_points(sp.outer, blank_r, params.blankL, "max")]
        outer_finish_pts = [PPoint.from_dict(p) for p in branch_path_points(sp.outer, blank_r, params.blankL)]
        inner_pts = [PPoint.from_dict(p) for p in branch_path_points(sp.inner, blank_r, params.blankL)]

    res = generate(pts, params, inner_pts, outer_finish_pts)
    if output_gcode:
        Path(output_gcode).write_text("\n".join(res.lines) + "\n", encoding="utf-8")
        print(f"Generated G-Code ({len(res.lines)} lines) -> {output_gcode}")
    else:
        print("\n".join(res.lines[:25]))
        if len(res.lines) > 25:
            print(f"... ({len(res.lines)} total lines)")

    if output_dxf:
        dxf_res = build_dxf(res.segs, params.ops, params.blankL, params.blankD / 2.0)
        Path(output_dxf).write_text(dxf_res.text + "\n", encoding="utf-8")
        print(f"Generated DXF ({dxf_res.vertexCount} vertices, {dxf_res.opCount} ops) -> {output_dxf}")

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--server", action="store_true", help="اجرای سرور وب بدون باز کردن پنجره دسکتاپ")
    parser.add_argument("--host", default="127.0.0.1", help="آدرس هاست سرور (پیش‌فرض: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=0, help="پورت سرور (۰ = انتخاب خودکار پورت آزاد)")
    parser.add_argument("--preset", help="تولید مستقیم جی‌کد از پیش‌تنظیم (مثلاً leg, vase, bowl-both)")
    parser.add_argument("--format", choices=["modal", "std"], default="modal", help="فرمت خروجی جی‌کد")
    parser.add_argument("--out-gcode", help="مسیر ذخیره فایل G-Code")
    parser.add_argument("--out-dxf", help="مسیر ذخیره فایل DXF")
    parser.add_argument("--version", action="store_true", help="نمایش نسخه نرم‌افزار")
    args = parser.parse_args(argv)

    if args.version:
        print(f"KharratCode Python v{__version__}")
        return 0

    if args.preset:
        return run_cli_preset(args.preset, args.out_gcode, args.out_dxf, args.format)

    if args.server:
        port = args.port or 8765
        server = ThreadingHTTPServer((args.host, port), KharratCodeRequestHandler)
        print(f"KharratCode Python Server listening on http://{args.host}:{port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        return 0

    server, port = start_background_server(host=args.host, port=args.port)
    url = f"http://127.0.0.1:{port}/"
    launch_desktop_window(url)
    server.shutdown()
    return 0
