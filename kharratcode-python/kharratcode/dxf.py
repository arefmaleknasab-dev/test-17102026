"""
خروجی DXF — فقط مسیر عملیات تراش (حرکات برشی)، به ترتیب استراتژی
• لایهٔ CUTPATH: کل مسیر برشی به‌صورت یک خط یکپارچه
• لایهٔ مجزا برای هر عملیات: OP1-FACING ، OP2-ROUGH-D ، …
دستگاه مختصات مطابق جی‌کد: X = طول قطعه ، Y = قطر (صفحه XY)
بازنویسی کامل پایتون متناظر با src/lib/dxf.ts
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, List, Tuple, Any

ACI: Dict[str, int] = {
    "round": 134,
    "face": 2,
    "rough-d": 3,
    "rough-z": 5,
    "copy": 4,
    "offset": 1,
    "finish": 30,
    "inner-rough": 6,
    "inner-offset": 202,
    "inner-finish": 96,
    "bottom": 7,
}


@dataclass
class DxfLayer:
    name: str
    color: int
    runs: List[List[Tuple[float, float]]]
    closed: bool = False


@dataclass
class DxfResult:
    text: str
    vertexCount: int
    opCount: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "vertexCount": self.vertexCount,
            "opCount": self.opCount,
        }


def _fmt(v: float) -> str:
    return f"{round(v * 10000.0) / 10000.0:.4f}"


def build_dxf(segs: List[Any], ops: List[Any], blank_l: float, blank_r: float) -> DxfResult:
    cut: List[Tuple[float, float]] = []
    for s in segs:
        motion = s.motion if hasattr(s, "motion") else s["motion"]
        if motion != 1:
            continue
        z1 = s.z1 if hasattr(s, "z1") else s["z1"]
        x1 = s.x1 if hasattr(s, "x1") else s["x1"]
        z2 = s.z2 if hasattr(s, "z2") else s["z2"]
        x2 = s.x2 if hasattr(s, "x2") else s["x2"]
        if not cut:
            cut.append((float(z1), float(x1) / 2.0))
        cut.append((float(z2), float(x2) / 2.0))

    runs_by_op: Dict[int, List[List[Tuple[float, float]]]] = {}
    for o in ops:
        on = o.on if hasattr(o, "on") else o.get("on", True)
        oid = o.id if hasattr(o, "id") else o["id"]
        if on:
            runs_by_op[int(oid)] = []

    cur: List[Tuple[float, float]] | None = None
    cur_id = -1

    def flush() -> None:
        nonlocal cur
        if cur is not None and len(cur) > 1 and cur_id in runs_by_op:
            runs_by_op[cur_id].append(cur)
        cur = None

    for s in segs:
        motion = s.motion if hasattr(s, "motion") else s["motion"]
        op_id = int(s.opId if hasattr(s, "opId") else s["opId"])
        z1 = float(s.z1 if hasattr(s, "z1") else s["z1"])
        x1 = float(s.x1 if hasattr(s, "x1") else s["x1"])
        z2 = float(s.z2 if hasattr(s, "z2") else s["z2"])
        x2 = float(s.x2 if hasattr(s, "x2") else s["x2"])
        if motion == 1:
            if cur is None or cur_id != op_id:
                flush()
                cur_id = op_id
                cur = [(z1, x1 / 2.0)]
            cur.append((z2, x2 / 2.0))
        else:
            flush()
    flush()

    layers: List[DxfLayer] = []
    if len(cut) > 1:
        layers.append(DxfLayer(name="CUTPATH", color=7, runs=[cut], closed=False))

    idx = 0
    for o in ops:
        on = o.on if hasattr(o, "on") else o.get("on", True)
        if not on:
            continue
        oid = int(o.id if hasattr(o, "id") else o["id"])
        otype = str(o.type if hasattr(o, "type") else o["type"])
        holder = int(o.holder if hasattr(o, "holder") else o.get("holder", 1))
        runs = runs_by_op.get(oid, [])
        if not runs:
            continue
        idx += 1
        suffix = "-H2" if holder == 2 else ""
        layers.append(
            DxfLayer(
                name=f"OP{idx}-{otype.upper()}{suffix}",
                color=ACI.get(otype, 7),
                runs=runs,
                closed=False,
            )
        )

    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")
    for layer in layers:
        for run in layer.runs:
            for x, y in run:
                if x < min_x:
                    min_x = x
                if x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                if y > max_y:
                    max_y = y

    if not math.isfinite(min_x):
        min_x = 0.0
        min_y = -blank_r
        max_x = blank_l
        max_y = blank_r

    out: List[str] = []

    def w(code: int, val: Any) -> None:
        out.append(str(code))
        out.append(str(val))

    w(0, "SECTION")
    w(2, "HEADER")
    w(9, "$ACADVER")
    w(1, "AC1015")
    w(9, "$INSUNITS")
    w(70, 4)
    w(9, "$EXTMIN")
    w(10, _fmt(min_x))
    w(20, _fmt(min_y))
    w(30, 0)
    w(9, "$EXTMAX")
    w(10, _fmt(max_x))
    w(20, _fmt(max_y))
    w(30, 0)
    w(0, "ENDSEC")

    w(0, "SECTION")
    w(2, "TABLES")
    w(0, "TABLE")
    w(2, "LAYER")
    w(70, len(layers))
    for layer in layers:
        w(0, "LAYER")
        w(2, layer.name)
        w(70, 0)
        w(62, layer.color)
        w(6, "CONTINUOUS")
    w(0, "ENDTAB")
    w(0, "ENDSEC")

    w(0, "SECTION")
    w(2, "ENTITIES")
    for layer in layers:
        for run in layer.runs:
            if len(run) < 2:
                continue
            w(0, "LWPOLYLINE")
            w(8, layer.name)
            w(90, len(run))
            w(70, 1 if layer.closed else 0)
            w(62, layer.color)
            for x, y in run:
                w(10, _fmt(x))
                w(20, _fmt(y))
    w(0, "ENDSEC")
    w(0, "EOF")

    return DxfResult(text="\n".join(out), vertexCount=len(cut), opCount=idx)
