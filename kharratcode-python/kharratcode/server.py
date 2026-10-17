"""
سرور محلی پایتون خراط‌کد (KharratCode Python Backend & Offline UI Server)
بدون وابستگی خارجی (Pure Python Standard Library) — اجرا به صورت ۱۰۰٪ آفلاین روی ویندوز و لینوکس
"""

from __future__ import annotations
import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from . import __version__
from .ai import parse_illustrator, transform_ai_segments
from .dxf import build_dxf
from .lathe import (
    PRESETS,
    STRATEGIES,
    PPoint,
    apply_gcode_ovr,
    generate,
    normalize_params,
    preset_points,
)
from .sketch import (
    SPoint,
    branch_path_points,
    branch_points,
    chain_polyline,
    flatten_sketch,
    normalize_sketch,
    order_chain,
    sketch_from_points,
    sketch_from_wall,
    split_chain_at,
)


def get_ui_html_path() -> Path:
    """مسیر فایل رابط کاربری آفلاین باندل‌شده را برمی‌گرداند."""
    here = Path(__file__).resolve().parent
    candidates = [
        here / "ui" / "KharratCode.html",
        here.parent / "ui" / "KharratCode.html",
        here.parent.parent / "KharratCode.html",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0]


def get_user_data_file() -> Path:
    """مسیر ذخیره دائمی پروژه و تنظیمات کاربر روی دیسک."""
    appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata) / "KharratCode"
    else:
        base = Path.home() / ".kharratcode"
    base.mkdir(parents=True, exist_ok=True)
    return base / "project_state.json"


def generate_from_sketch_or_points(payload: Dict[str, Any]) -> Dict[str, Any]:
    """اجرای کامل موتور تراش پایتون از روی اسکچ یا نقاط پروفیل."""
    params = normalize_params(payload.get("params"), bool(payload.get("legacy", False)))
    sketch_raw = payload.get("sketch")
    pts_raw = payload.get("points")
    inner_raw = payload.get("innerPoints")
    outer_finish_raw = payload.get("outerFinishPoints")
    gcode_ovr = payload.get("gcodeOvr") or {}

    blank_r = params.blankD / 2.0
    blank_l = params.blankL

    pts = [PPoint.from_dict(p) for p in pts_raw] if isinstance(pts_raw, list) and pts_raw else []
    inner_pts = [PPoint.from_dict(p) for p in inner_raw] if isinstance(inner_raw, list) and inner_raw else None
    outer_finish_pts = (
        [PPoint.from_dict(p) for p in outer_finish_raw]
        if isinstance(outer_finish_raw, list) and outer_finish_raw
        else None
    )

    if not pts and sketch_raw:
        segs = normalize_sketch(sketch_raw) or []
        if segs:
            if params.split.enabled:
                chain = order_chain(segs)
                poly = chain_polyline(chain)
                if len(poly) >= 2:
                    sp = split_chain_at(poly, SPoint(z=params.split.z, r=params.split.r))
                    outer_br = sp.inner if params.split.swapped else sp.outer
                    inner_br = sp.outer if params.split.swapped else sp.inner
                    pts = [PPoint.from_dict(p) for p in branch_points(outer_br, blank_r, blank_l, "max")]
                    outer_finish_pts = [PPoint.from_dict(p) for p in branch_path_points(outer_br, blank_r, blank_l)]
                    inner_pts = [PPoint.from_dict(p) for p in branch_path_points(inner_br, blank_r, blank_l)]
            if not pts:
                flat = flatten_sketch(segs, blank_r, blank_l)
                pts = [PPoint.from_dict(p) for p in flat]

    base_res = generate(pts, params, inner_pts, outer_finish_pts)
    final_res = apply_gcode_ovr(base_res, gcode_ovr, params) if gcode_ovr else base_res
    return final_res.to_dict()


class KharratCodeRequestHandler(BaseHTTPRequestHandler):
    """پردازشگر درخواست‌های HTTP برای رابط کاربری آفلاین و API موتور پایتون."""

    def log_message(self, format: str, *args: Any) -> None:
        # جلوگیری از شلوغی کنسول در حالت دسکتاپ
        if os.environ.get("KHARRATCODE_DEBUG"):
            super().log_message(format, *args)

    def _send_json(self, data: Any, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html", "/KharratCode.html"):
            ui_path = get_ui_html_path()
            if ui_path.is_file():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(ui_path.stat().st_size))
                self.end_headers()
                return
        self.send_response(200)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            self._send_json(
                {
                    "status": "ok",
                    "engine": "python",
                    "version": __version__,
                    "offline": True,
                    "presetsCount": len(PRESETS),
                    "strategiesCount": len(STRATEGIES),
                }
            )
            return

        if path == "/api/presets":
            self._send_json({"presets": PRESETS, "strategies": STRATEGIES})
            return

        if path == "/api/project/load":
            state_file = get_user_data_file()
            if state_file.is_file():
                try:
                    data = json.loads(state_file.read_text(encoding="utf-8"))
                    self._send_json({"ok": True, "state": data})
                    return
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=500)
                    return
            self._send_json({"ok": True, "state": None})
            return

        # سرو کردن رابط کاربری آفلاین
        if path in ("/", "/index.html", "/KharratCode.html"):
            ui_path = get_ui_html_path()
            if ui_path.is_file():
                content = ui_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                try:
                    self.wfile.write(content)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            self._send_json({"error": "UI bundle not found"}, status=404)
            return

        self._send_json({"error": f"Not found: {path}"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            payload = self._read_json()
        except Exception as exc:
            self._send_json({"error": f"Invalid JSON: {exc}"}, status=400)
            return

        try:
            if path == "/api/generate":
                result = generate_from_sketch_or_points(payload)
                self._send_json(result)
                return

            if path == "/api/dxf":
                segs = payload.get("segs", [])
                ops = payload.get("ops", [])
                blank_l = float(payload.get("blankL", 200.0))
                blank_r = float(payload.get("blankR", 30.0))
                res = build_dxf(segs, ops, blank_l, blank_r)
                self._send_json(res.to_dict())
                return

            if path == "/api/ai/parse":
                text = str(payload.get("text", ""))
                doc = parse_illustrator(text)
                scale_x = payload.get("scaleX")
                scale_y = payload.get("scaleY")
                out = doc.to_dict()
                if isinstance(scale_x, (int, float)):
                    sy = float(scale_y) if isinstance(scale_y, (int, float)) else float(scale_x)
                    out["transformed"] = [s.to_dict() for s in transform_ai_segments(doc, float(scale_x), sy)]
                self._send_json(out)
                return

            if path == "/api/sketch/flatten":
                segs = normalize_sketch(payload.get("sketch", [])) or []
                blank_r = float(payload.get("blankR", 30.0))
                blank_l = float(payload.get("blankL", 200.0))
                self._send_json({"points": flatten_sketch(segs, blank_r, blank_l)})
                return

            if path == "/api/project/save":
                state_file = get_user_data_file()
                state_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                self._send_json({"ok": True, "path": str(state_file)})
                return

            self._send_json({"error": f"Unknown endpoint: {path}"}, status=404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=400)


def start_background_server(host: str = "127.0.0.1", port: int = 0) -> Tuple[ThreadingHTTPServer, int]:
    """راه‌اندازی سرور HTTP پایتون در یک ترد پس‌زمینه و بازگرداندن پورت."""
    server = ThreadingHTTPServer((host, port), KharratCodeRequestHandler)
    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, name="KharratCodeServer", daemon=True)
    thread.start()
    return server, actual_port
