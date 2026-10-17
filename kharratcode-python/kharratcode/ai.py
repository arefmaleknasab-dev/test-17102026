"""
واردکننده فایل‌های Adobe Illustrator (Legacy AI / EPS) به اسکچ خراط‌کد
بازنویسی کامل پایتون متناظر با src/lib/ai.ts
"""

from __future__ import annotations
import math
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from .sketch import SPoint, SketchSeg

PT_TO_MM = 25.4 / 72.0


@dataclass
class AiBounds:
    minX: float
    minY: float
    maxX: float
    maxY: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "minX": self.minX,
            "minY": self.minY,
            "maxX": self.maxX,
            "maxY": self.maxY,
        }


@dataclass
class AiDocument:
    segments: List[SketchSeg]
    bounds: AiBounds
    widthMm: float
    heightMm: float
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segments": [s.to_dict() for s in self.segments],
            "bounds": self.bounds.to_dict(),
            "widthMm": self.widthMm,
            "heightMm": self.heightMm,
            "warnings": self.warnings,
        }


def parse_illustrator(text: str) -> AiDocument:
    if "%PDF-" in text[:1024]:
        raise ValueError(
            "این فایل AI بر پایه PDF است. در Illustrator آن را با فرمت Illustrator 8 (Legacy/EPS) ذخیره و دوباره وارد کنید."
        )
    if "%!PS-Adobe" not in text and "Adobe Illustrator" not in text:
        raise ValueError("ساختار فایل AI شناسایی نشد. فایل باید AI قدیمی مبتنی بر EPS باشد.")

    clean = re.sub(r"%[^\r\n]*", " ", text)
    clean = re.sub(r"\([^)]*\)", " ", clean)
    tokens = re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|[A-Za-z*]+", clean)

    stack: List[float] = []
    segments: List[SketchSeg] = []
    warnings: List[str] = []
    seg_id = 700000
    current: Optional[SPoint] = None
    start: Optional[SPoint] = None

    def point(x: float, y: float) -> SPoint:
        return SPoint(z=x * PT_TO_MM, r=y * PT_TO_MM)

    def pop(n: int) -> List[float]:
        if len(stack) < n:
            res = list(stack)
            stack.clear()
            return res
        res = stack[-n:]
        del stack[-n:]
        return res

    for token in tokens:
        try:
            val = float(token)
            if math.isfinite(val):
                stack.append(val)
                continue
        except ValueError:
            pass

        op = token.lower()
        if op in ("m", "moveto"):
            a = pop(2)
            if len(a) == 2:
                current = point(a[0], a[1])
                start = current.copy()
        elif op in ("l", "lineto"):
            a = pop(2)
            if len(a) == 2 and current is not None:
                nxt = point(a[0], a[1])
                seg_id += 1
                segments.append(SketchSeg(id=seg_id, kind="line", a=current, b=nxt))
                current = nxt
        elif op in ("c", "curveto"):
            a = pop(6)
            if len(a) == 6 and current is not None:
                c1 = point(a[0], a[1])
                c2 = point(a[2], a[3])
                nxt = point(a[4], a[5])
                seg_id += 1
                segments.append(SketchSeg(id=seg_id, kind="cubic", a=current, b=nxt, c1=c1, c2=c2))
                current = nxt
        elif op == "v" and current is not None:
            a = pop(4)
            if len(a) == 4:
                c2 = point(a[0], a[1])
                nxt = point(a[2], a[3])
                seg_id += 1
                segments.append(SketchSeg(id=seg_id, kind="cubic", a=current, b=nxt, c1=current.copy(), c2=c2))
                current = nxt
        elif op == "y" and current is not None:
            a = pop(4)
            if len(a) == 4:
                c1 = point(a[0], a[1])
                nxt = point(a[2], a[3])
                seg_id += 1
                segments.append(SketchSeg(id=seg_id, kind="cubic", a=current, b=nxt, c1=c1, c2=nxt.copy()))
                current = nxt
        elif op in ("h", "closepath") and current is not None and start is not None:
            if math.hypot(current.z - start.z, current.r - start.r) > 1e-8:
                seg_id += 1
                segments.append(SketchSeg(id=seg_id, kind="line", a=current, b=start.copy()))
            current = start.copy()
        elif op in ("n", "s", "f", "b", "w", "j", "d", "g", "k", "rg", "re"):
            stack.clear()
        elif len(stack) > 64:
            del stack[: len(stack) - 16]

    if not segments:
        raise ValueError("هیچ مسیر برداری قابل ویرایشی در فایل پیدا نشد. متن، تصویر Raster، Mask و Effect قابل وارد کردن نیستند.")

    pts: List[SPoint] = []
    for s in segments:
        pts.append(s.a)
        pts.append(s.b)
        if s.c1:
            pts.append(s.c1)
        if s.c2:
            pts.append(s.c2)

    bounds = AiBounds(
        minX=min(p.z for p in pts),
        minY=min(p.r for p in pts),
        maxX=max(p.z for p in pts),
        maxY=max(p.r for p in pts),
    )
    if len(segments) > 4000:
        warnings.append("فایل دارای مسیرهای بسیار زیادی است و ممکن است ویرایش آن سنگین باشد.")
    return AiDocument(
        segments=segments,
        bounds=bounds,
        widthMm=bounds.maxX - bounds.minX,
        heightMm=bounds.maxY - bounds.minY,
        warnings=warnings,
    )


def transform_ai_segments(doc: AiDocument, scale_x: float, scale_y: Optional[float] = None) -> List[SketchSeg]:
    sy = scale_x if scale_y is None else scale_y

    def map_point(p: SPoint) -> SPoint:
        return SPoint(z=(p.z - doc.bounds.minX) * scale_x, r=(p.r - doc.bounds.minY) * sy)

    out: List[SketchSeg] = []
    for idx, s in enumerate(doc.segments):
        out.append(
            SketchSeg(
                id=800000 + idx,
                kind=s.kind,
                a=map_point(s.a),
                b=map_point(s.b),
                c1=map_point(s.c1) if s.c1 else None,
                c2=map_point(s.c2) if s.c2 else None,
                via=map_point(s.via) if s.via else None,
            )
        )
    return out
