"""
خراط‌کد — موتور هندسه، مسیر ابزار و جی‌کد برای خراطی دومحور (X/Z)
بازنویسی کامل پایتون متناظر با src/lib/lathe.ts
"""

from __future__ import annotations
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple, Any

RoughMode = Literal["classic", "zigzag", "zone"]
BlankShape = Literal["circle", "square", "hex", "octagon"]
ToolType = Literal["angle", "round", "groove"]
ToolHand = Literal["center", "left", "right"]
CodeFormat = Literal["modal", "std"]
SegKind = Literal[
    "rapid",
    "round",
    "face",
    "rough",
    "roughz",
    "copy",
    "offset",
    "finish",
    "bore",
    "boreoff",
    "borefin",
    "bottom",
]
OpType = Literal[
    "round",
    "face",
    "rough-d",
    "rough-z",
    "copy",
    "offset",
    "finish",
    "inner-rough",
    "inner-offset",
    "inner-finish",
    "bottom",
]

ROUGH_MODES = [
    {"id": "classic", "name": "یک طرفه"},
    {"id": "zigzag", "name": "دو طرفه"},
    {"id": "zone", "name": "ناحیه‌ای دو طرفه"},
]

BLANK_SHAPES = [
    {"id": "circle", "name": "دایره‌ای", "sides": 0},
    {"id": "square", "name": "مربعی", "sides": 4},
    {"id": "hex", "name": "شش‌ضلعی", "sides": 6},
    {"id": "octagon", "name": "هشت‌ضلعی", "sides": 8},
]

HOLDER2_ROT = -90
MIN_HOLDER2_OFFSET = 50.0
INSERT_ANGLE = 35.0
NOSE_RADII = [0.2, 0.4, 0.8, 1.2, 1.6]
RAPID_RATE = 2500.0
BRIDGE_MIN_JUMP = 10.0

HAND_INFO: Dict[str, Dict[str, Any]] = {
    "center": {"name": "وسط‌تراش", "desc": "متقارن — زاویه ۹۰°", "k": 90},
    "right": {"name": "راست‌تراش", "desc": "لبهٔ اصلی راست — ۸۷°", "k": 87},
    "left": {"name": "چپ‌تراش", "desc": "لبهٔ اصلی چپ — ۹۳°", "k": 93},
}

OUTER_OPS: List[OpType] = ["round", "face", "rough-d", "rough-z", "copy", "offset", "finish"]
INNER_OPS: List[OpType] = ["inner-rough", "inner-offset", "inner-finish", "bottom"]
ALL_OP_TYPES: List[OpType] = [
    "round",
    "face",
    "rough-d",
    "rough-z",
    "copy",
    "offset",
    "finish",
    "inner-rough",
    "inner-offset",
    "inner-finish",
    "bottom",
]

DEFAULT_HOLDER: Dict[str, int] = {
    "round": 1,
    "face": 1,
    "rough-d": 1,
    "rough-z": 1,
    "copy": 1,
    "offset": 1,
    "finish": 1,
    "inner-rough": 2,
    "inner-offset": 2,
    "inner-finish": 2,
    "bottom": 2,
}

OP_INFO: Dict[str, Dict[str, str]] = {
    "round": {"name": "گرد کردن گوشه‌ها", "desc": "برداشت قسمت اضافی مقطع تا استوانهٔ قطر واقعی", "color": "#b48ee0"},
    "face": {"name": "پیشانی‌تراشی", "desc": "تراش سطح سر قطعه تا شعاع طرح", "color": "#e3a94e"},
    "rough-d": {"name": "خشن شعاعی G71", "desc": "لایه‌های قطری با حرکت طولی", "color": "#45b394"},
    "rough-z": {"name": "خشن محوری G72", "desc": "فرورفتن شعاعی در گام‌های طولی", "color": "#6ab0d8"},
    "copy": {"name": "کپی‌تراشی", "desc": "مسیرهای موازی با خط طرح", "color": "#a3c15c"},
    "offset": {"name": "آفست", "desc": "خط موازی با طرح — مرجع مراحل خشن", "color": "#f59a80"},
    "finish": {"name": "پرداخت نهایی", "desc": "حرکت دقیق روی خط اصلی طرح", "color": "#e0703c"},
    "inner-rough": {"name": "خشن داخل (کاسه)", "desc": "خالی‌کردن داخل کاسه با هلدر دوم", "color": "#4cc9f0"},
    "inner-offset": {"name": "افست داخل تراشی", "desc": "مسیر موازی دیواره داخلی پیش از پرداخت", "color": "#c77dff"},
    "inner-finish": {"name": "پرداخت داخل", "desc": "پرداخت دیواره داخلی با هلدر دوم", "color": "#f72585"},
    "bottom": {"name": "کف‌تراشی", "desc": "برداشت طول اضافی خام پشت صفحه دهانه با هلدر داخل‌تراشی", "color": "#ffd166"},
}

STRATEGIES: List[Dict[str, Any]] = [
    {"id": "g71", "name": "استاندارد شعاعی", "types": ["round", "rough-d", "offset", "finish"]},
    {"id": "g72", "name": "محوری پله‌ای", "types": ["round", "rough-z", "offset", "finish"]},
    {"id": "copy", "name": "کپی‌تراشی", "types": ["round", "copy", "offset", "finish"]},
    {
        "id": "bowl",
        "name": "کاسه داخل+خارج",
        "types": ["round", "face", "rough-d", "offset", "finish", "bottom", "inner-rough", "inner-offset", "inner-finish"],
    },
]

FINISH_KINDS = {"finish", "offset", "boreoff", "borefin"}

_op_uid = 1
_pt_uid = 1000


def _next_op_id() -> int:
    global _op_uid
    val = _op_uid
    _op_uid += 1
    return val


def next_id() -> int:
    global _pt_uid
    _pt_uid += 1
    return _pt_uid


def _f2(v: float) -> str:
    return f"{round(v * 100.0) / 100.0:.2f}"


def _f3(v: float) -> str:
    return f"{v:.3f}"


@dataclass
class PPoint:
    id: int
    z: float
    r: float
    smooth: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "z": float(self.z), "r": float(self.r), "smooth": bool(self.smooth)}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PPoint":
        return PPoint(
            id=int(d.get("id") or next_id()),
            z=float(d["z"]),
            r=float(d["r"]),
            smooth=bool(d.get("smooth", False)),
        )


@dataclass
class Sample:
    z: float
    r: float

    def copy(self) -> "Sample":
        return Sample(z=self.z, r=self.r)

    def to_dict(self) -> Dict[str, float]:
        return {"z": float(self.z), "r": float(self.r)}


@dataclass
class SplitState:
    enabled: bool = False
    z: float = 90.0
    r: float = 68.0
    swapped: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"enabled": self.enabled, "z": self.z, "r": self.r, "swapped": self.swapped}


@dataclass
class Holder2State:
    xOff: float = 50.0
    yOff: float = 50.0

    def to_dict(self) -> Dict[str, float]:
        return {"xOff": self.xOff, "yOff": self.yOff}


@dataclass
class ToolSpec:
    type: ToolType = "angle"
    hand: ToolHand = "center"
    angle: float = INSERT_ANGLE
    nose: float = 0.2
    size: float = 16.0
    radius: float = 6.0
    width: float = 3.0
    corner: float = 0.2
    shank: float = 12.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "hand": self.hand,
            "angle": self.angle,
            "nose": self.nose,
            "size": self.size,
            "radius": self.radius,
            "width": self.width,
            "corner": self.corner,
            "shank": self.shank,
        }


@dataclass
class Op:
    id: int
    type: OpType
    on: bool = True
    reverse: bool = False
    holder: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "on": self.on,
            "reverse": self.reverse,
            "holder": self.holder,
        }


@dataclass
class Params:
    blankD: float = 60.0
    blankL: float = 200.0
    blankShape: BlankShape = "square"
    doc: float = 3.0
    innerDoc: float = 3.0
    offsetDist: float = 0.5
    innerOffsetDist: float = 0.5
    innerStartClearance: float = 2.0
    innerEndTravel: float = 300.0
    bottomRoughOverlap: float = 3.0
    bottomOffsetClearance: float = 0.0
    feedRough: float = 220.0
    feedFinish: float = 110.0
    feedByKind: Optional[Dict[str, float]] = None
    rpm: float = 1500.0
    tool: ToolSpec = field(default_factory=ToolSpec)
    safety: float = 2.0
    roughMode: RoughMode = "zone"
    innerRoughMode: RoughMode = "classic"
    innerZoneOrder: List[int] = field(default_factory=list)
    innerZoneBounds: List[float] = field(default_factory=list)
    ramp: bool = True
    safeBottomInnerLink: bool = True
    simpleFeed: bool = True
    zoneOrder: List[int] = field(default_factory=list)
    zoneBounds: List[float] = field(default_factory=list)
    lineNumbers: bool = True
    ops: List[Op] = field(default_factory=lambda: make_ops(["round", "rough-d", "offset", "finish"]))
    format: CodeFormat = "modal"
    spreadG0: bool = False
    split: SplitState = field(default_factory=SplitState)
    holder2: Holder2State = field(default_factory=Holder2State)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blankD": self.blankD,
            "blankL": self.blankL,
            "blankShape": self.blankShape,
            "doc": self.doc,
            "innerDoc": self.innerDoc,
            "offsetDist": self.offsetDist,
            "innerOffsetDist": self.innerOffsetDist,
            "innerStartClearance": self.innerStartClearance,
            "innerEndTravel": self.innerEndTravel,
            "bottomRoughOverlap": self.bottomRoughOverlap,
            "bottomOffsetClearance": self.bottomOffsetClearance,
            "feedRough": self.feedRough,
            "feedFinish": self.feedFinish,
            "feedByKind": self.feedByKind,
            "rpm": self.rpm,
            "tool": self.tool.to_dict(),
            "safety": self.safety,
            "roughMode": self.roughMode,
            "innerRoughMode": self.innerRoughMode,
            "innerZoneOrder": list(self.innerZoneOrder),
            "innerZoneBounds": list(self.innerZoneBounds),
            "ramp": self.ramp,
            "safeBottomInnerLink": self.safeBottomInnerLink,
            "simpleFeed": self.simpleFeed,
            "zoneOrder": list(self.zoneOrder),
            "zoneBounds": list(self.zoneBounds),
            "lineNumbers": self.lineNumbers,
            "ops": [o.to_dict() for o in self.ops],
            "format": self.format,
            "spreadG0": self.spreadG0,
            "split": self.split.to_dict(),
            "holder2": self.holder2.to_dict(),
        }


@dataclass
class Seg:
    motion: Literal[0, 1]
    x1: float
    z1: float
    x2: float
    z2: float
    feed: float
    line: int
    kind: SegKind
    op: str
    opId: int
    holder: int = 1
    feedOvr: Optional[bool] = None
    bridgeMoves: Optional[Dict[int, Dict[str, Any]]] = None
    note: Optional[List[str]] = None
    fan: Optional[float] = None
    fanU: Optional[float] = None
    ovrKey: Optional[str] = None

    def copy(self) -> "Seg":
        return Seg(
            motion=self.motion,
            x1=self.x1,
            z1=self.z1,
            x2=self.x2,
            z2=self.z2,
            feed=self.feed,
            line=self.line,
            kind=self.kind,
            op=self.op,
            opId=self.opId,
            holder=self.holder,
            feedOvr=self.feedOvr,
            bridgeMoves=dict(self.bridgeMoves) if self.bridgeMoves else None,
            note=list(self.note) if self.note else None,
            fan=self.fan,
            fanU=self.fanU,
            ovrKey=self.ovrKey,
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "motion": self.motion,
            "x1": self.x1,
            "z1": self.z1,
            "x2": self.x2,
            "z2": self.z2,
            "feed": self.feed,
            "line": self.line,
            "kind": self.kind,
            "op": self.op,
            "opId": self.opId,
            "holder": self.holder,
        }
        if self.feedOvr is not None:
            out["feedOvr"] = self.feedOvr
        if self.bridgeMoves is not None:
            out["bridgeMoves"] = self.bridgeMoves
        if self.note is not None:
            out["note"] = self.note
        if self.fan is not None:
            out["fan"] = self.fan
        if self.fanU is not None:
            out["fanU"] = self.fanU
        if self.ovrKey is not None:
            out["ovrKey"] = self.ovrKey
        return out


@dataclass
class GenResult:
    lines: List[str]
    segs: List[Seg]
    samples: List[Sample]
    innerSamples: List[Sample]
    cutLen: float
    rapidLen: float
    timeSec: float
    volumeCm3: float
    roughLayers: int
    format: CodeFormat

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lines": self.lines,
            "segs": [s.to_dict() for s in self.segs],
            "samples": [s.to_dict() for s in self.samples],
            "innerSamples": [s.to_dict() for s in self.innerSamples],
            "cutLen": self.cutLen,
            "rapidLen": self.rapidLen,
            "timeSec": self.timeSec,
            "volumeCm3": self.volumeCm3,
            "roughLayers": self.roughLayers,
            "format": self.format,
        }


def rotational_envelope(blank_d: float, shape: BlankShape) -> Dict[str, Any]:
    s = next((b for b in BLANK_SHAPES if b["id"] == shape), None)
    in_r = blank_d / 2.0
    if not s or s["sides"] == 0:
        return {
            "maxRotD": blank_d,
            "inR": in_r,
            "outR": in_r,
            "sides": 0,
            "hasCorners": False,
            "growth": 0.0,
        }
    sides = int(s["sides"])
    out_r = in_r / math.cos(math.pi / sides)
    return {
        "maxRotD": out_r * 2.0,
        "inR": in_r,
        "outR": out_r,
        "sides": sides,
        "hasCorners": True,
        "growth": out_r * 2.0 - blank_d,
    }


def holder2_offset_from_coordinates(holder1: Dict[str, float], holder2: Dict[str, float]) -> Holder2State:
    return Holder2State(
        xOff=round((float(holder2["x"]) - float(holder1["x"])) * 100.0) / 100.0,
        yOff=round((float(holder1["y"]) - float(holder2["y"])) * 100.0) / 100.0,
    )


def normalize_tool(raw: Any, legacy_w: Optional[float] = None) -> ToolSpec:
    base = ToolSpec()
    if isinstance(raw, dict):
        if raw.get("type") in ("angle", "round", "groove"):
            base.type = raw["type"]
        if raw.get("hand") in ("center", "left", "right"):
            base.hand = raw["hand"]
        for k in ("angle", "nose", "size", "radius", "width", "corner", "shank"):
            v = raw.get(k)
            if isinstance(v, (int, float)) and math.isfinite(float(v)) and float(v) >= 0:
                setattr(base, k, float(v))
        return base
    if isinstance(legacy_w, (int, float)) and math.isfinite(float(legacy_w)) and float(legacy_w) > 0:
        base.type = "groove"
        base.width = float(legacy_w)
    return base


def tool_profile(t: ToolSpec) -> Dict[str, Any]:
    rad = lambda d: d * math.pi / 180.0
    pts: List[List[float]] = []
    min_z = 0.0
    max_z = 1.0
    height = 6.0
    step = 0.2

    if t.type == "groove":
        w = max(0.5, t.width)
        rc = min(max(0.0, t.corner), w / 2.0)
        min_z = -w / 2.0
        max_z = w / 2.0
        height = max(4.0, w * 1.6)
        dz = min_z
        while dz <= max_z + 1e-9:
            z = min(max_z, dz)
            edge = w / 2.0 - rc
            over = abs(z) - edge
            c = rc - math.sqrt(max(0.0, rc * rc - over * over)) if over > 0 else 0.0
            pts.append([z, c])
            dz += step
        pts.append([max_z, pts[-1][1]])
    elif t.type == "round":
        R = max(0.5, t.radius)
        min_z = -R
        max_z = R
        height = R * 2.0
        dz = -R
        while dz <= R + 1e-9:
            z = min(R, dz)
            pts.append([z, R - math.sqrt(max(0.0, R * R - z * z))])
            dz += step
        pts.append([R, R])
    else:
        inc = INSERT_ANGLE
        S = max(3.0, t.size)
        rn = max(0.0, min(t.nose, S / 4.0))
        if t.hand == "center":
            a_l = 90.0 + inc / 2.0
            a_r = 90.0 - inc / 2.0
        elif t.hand == "right":
            a_r = 87.0
            a_l = a_r + inc
        else:
            a_l = 93.0
            a_r = a_l - inc
        r_l = rad(a_l)
        r_r = rad(a_r)
        s_l = math.tan(r_l)
        s_r = math.tan(r_r)
        line_c = lambda dz_val: dz_val * s_l if dz_val < 0 else dz_val * s_r
        xc = 0.0
        yc = rn
        det = math.sin(r_l - r_r)
        if rn > 0 and abs(det) > 1e-9:
            xc = (rn * (math.cos(r_r) + math.cos(r_l))) / det
            yc = (rn * (math.sin(r_l) + math.sin(r_r))) / det

        def arc_c(dz_val: float) -> float:
            dx = dz_val - xc
            if rn <= 0 or abs(dx) > rn:
                return float("-inf")
            return yc - math.sqrt(max(0.0, rn * rn - dx * dx))

        min_z = S * math.cos(r_l)
        max_z = S * math.cos(r_r)
        height = max(4.0, S * 0.95)
        dz = min_z
        while dz <= max_z + 1e-9:
            z = min(max_z, dz)
            pts.append([z, max(line_c(z), arc_c(z))])
            dz += step
        pts.append([max_z, max(line_c(max_z), arc_c(max_z))])

    if len(pts) >= 2 and pts[0][0] < -1e-9 and pts[-1][0] > 1e-9:
        k = 0
        while k < len(pts) - 1 and pts[k + 1][0] < 0:
            k += 1
        z1, c1 = pts[k]
        z2, c2 = pts[k + 1]
        c0 = c1 + (c2 - c1) * ((0.0 - z1) / (z2 - z1))
        pts.insert(k + 1, [0.0, c0])

    return {"min": min_z, "max": max_z, "pts": pts, "height": height}


def tool_desc(t: ToolSpec) -> str:
    if t.type == "round":
        return f"ROUND INSERT R{t.radius:g}"
    if t.type == "groove":
        return f"GROOVE TOOL W{t.width:g}"
    hname = HAND_INFO.get(t.hand, HAND_INFO["center"])["name"].upper()
    return f"V{INSERT_ANGLE:g} {hname} INSERT NOSE R{t.nose:g}"


def outer_first_types(types: List[OpType]) -> List[OpType]:
    return [t for t in types if t not in INNER_OPS] + [t for t in types if t in INNER_OPS]


def outer_first_ops(ops: List[Op]) -> List[Op]:
    outer = [o for o in ops if o.type not in INNER_OPS]
    inner = [o for o in ops if o.type in INNER_OPS]
    return outer + inner


def make_ops(types: List[OpType]) -> List[Op]:
    ops = [Op(id=_next_op_id(), type=t, on=True, reverse=False, holder=DEFAULT_HOLDER[t]) for t in types]
    return outer_first_ops(ops)


def default_op_insert_index(ops: List[Op], op_type: OpType) -> int:
    if op_type in INNER_OPS:
        return len(ops)
    for idx, o in enumerate(ops):
        if o.type in INNER_OPS:
            return idx
    return len(ops)


def normalize_ops(raw: Any, legacy: bool = False) -> Optional[List[Op]]:
    if not isinstance(raw, list) or not raw:
        return None
    out: List[Op] = []
    for o in raw:
        if not isinstance(o, dict) or not isinstance(o.get("type"), str):
            continue
        t = o["type"]
        if legacy:
            if t == "offset":
                t = "copy"
            elif t == "spring":
                t = "offset"
        if t in ALL_OP_TYPES:
            hh = o.get("holder")
            holder = 2 if hh == 2 else (1 if hh == 1 else DEFAULT_HOLDER[t])
            out.append(
                Op(
                    id=int(o["id"]) if isinstance(o.get("id"), (int, float)) else _next_op_id(),
                    type=t,  # type: ignore
                    on=(o.get("on") is not False),
                    reverse=(o.get("reverse") is True),
                    holder=holder,
                )
            )
    if (
        any(o.type == "inner-rough" for o in out)
        and any(o.type == "inner-finish" for o in out)
        and not any(o.type == "inner-offset" for o in out)
    ):
        rough_at = next(i for i, o in enumerate(out) if o.type == "inner-rough")
        new_id = max((o.id for o in out), default=0) + 1
        out.insert(rough_at + 1, Op(id=new_id, type="inner-offset", on=True, holder=2))
    if legacy and out:
        offsets = [o for o in out if o.type == "offset"]
        if offsets:
            rest = [o for o in out if o.type != "offset"]
            fi = next((i for i, o in enumerate(rest) if o.type == "finish"), -1)
            if fi >= 0:
                rest[fi:fi] = offsets
            else:
                rest.extend(offsets)
            return rest
    return out if out else None


def normalize_params(raw: Optional[Dict[str, Any]] = None, legacy: bool = False) -> Params:
    base = Params(
        ops=make_ops(STRATEGIES[0]["types"]),
        tool=ToolSpec(),
        split=SplitState(),
        holder2=Holder2State(),
    )
    if not raw or not isinstance(raw, dict):
        return base

    num_keys = [
        "blankD",
        "blankL",
        "doc",
        "innerDoc",
        "offsetDist",
        "innerOffsetDist",
        "innerStartClearance",
        "innerEndTravel",
        "bottomRoughOverlap",
        "bottomOffsetClearance",
        "feedRough",
        "feedFinish",
        "rpm",
        "safety",
    ]
    bool_keys = ["lineNumbers", "ramp", "safeBottomInnerLink", "simpleFeed", "spreadG0"]

    for k in num_keys:
        v = raw.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)):
            setattr(base, k, float(v))
    for k in bool_keys:
        v = raw.get(k)
        if isinstance(v, bool):
            setattr(base, k, v)

    if not (isinstance(raw.get("innerDoc"), (int, float)) and math.isfinite(float(raw["innerDoc"]))) and (
        isinstance(raw.get("doc"), (int, float)) and math.isfinite(float(raw["doc"]))
    ):
        base.innerDoc = float(raw["doc"])

    base.innerDoc = min(10.0, max(0.5, base.innerDoc))
    base.innerStartClearance = min(20.0, max(0.0, base.innerStartClearance))
    base.innerEndTravel = min(500.0, max(300.0, base.innerEndTravel))
    base.bottomRoughOverlap = min(50.0, max(0.0, base.bottomRoughOverlap))
    base.bottomOffsetClearance = min(100.0, max(0.0, base.bottomOffsetClearance))

    if isinstance(raw.get("finAllow"), (int, float)) and math.isfinite(float(raw["finAllow"])):
        base.offsetDist = float(raw["finAllow"])

    if raw.get("roughMode") in ("classic", "zigzag", "zone"):
        base.roughMode = raw["roughMode"]
    elif isinstance(raw.get("zigzag"), bool):
        base.roughMode = "zigzag" if raw["zigzag"] else "classic"

    if raw.get("innerRoughMode") in ("classic", "zigzag", "zone"):
        base.innerRoughMode = raw["innerRoughMode"]

    if raw.get("blankShape") in ("circle", "square", "hex", "octagon"):
        base.blankShape = raw["blankShape"]

    if isinstance(raw.get("zoneOrder"), list) and all(isinstance(v, int) and v >= 0 for v in raw["zoneOrder"]):
        base.zoneOrder = list(raw["zoneOrder"])
    if isinstance(raw.get("zoneBounds"), list) and all(isinstance(v, (int, float)) and math.isfinite(float(v)) for v in raw["zoneBounds"]):
        base.zoneBounds = sorted(float(v) for v in raw["zoneBounds"])
    if isinstance(raw.get("innerZoneOrder"), list) and all(isinstance(v, int) and v >= 0 for v in raw["innerZoneOrder"]):
        base.innerZoneOrder = list(raw["innerZoneOrder"])
    if isinstance(raw.get("innerZoneBounds"), list) and all(isinstance(v, (int, float)) and math.isfinite(float(v)) for v in raw["innerZoneBounds"]):
        base.innerZoneBounds = sorted(float(v) for v in raw["innerZoneBounds"])

    if isinstance(raw.get("feedByKind"), dict):
        fbk: Dict[str, float] = {}
        for k, v in raw["feedByKind"].items():
            if isinstance(v, (int, float)) and math.isfinite(float(v)):
                fbk[str(k)] = float(v)
        base.feedByKind = fbk

    ops = normalize_ops(raw.get("ops"), legacy)
    if ops is not None:
        base.ops = ops
    if raw.get("format") in ("modal", "std"):
        base.format = raw["format"]

    if isinstance(raw.get("split"), dict):
        s = raw["split"]
        if isinstance(s.get("enabled"), bool):
            base.split.enabled = s["enabled"]
        if isinstance(s.get("z"), (int, float)) and math.isfinite(float(s["z"])):
            base.split.z = float(s["z"])
        if isinstance(s.get("r"), (int, float)) and math.isfinite(float(s["r"])):
            base.split.r = float(s["r"])
        if isinstance(s.get("swapped"), bool):
            base.split.swapped = s["swapped"]

    if isinstance(raw.get("holder2"), dict):
        h = raw["holder2"]
        if isinstance(h.get("xOff"), (int, float)) and math.isfinite(float(h["xOff"])):
            base.holder2.xOff = max(MIN_HOLDER2_OFFSET, float(h["xOff"]))
        if isinstance(h.get("yOff"), (int, float)) and math.isfinite(float(h["yOff"])):
            base.holder2.yOff = max(MIN_HOLDER2_OFFSET, float(h["yOff"]))

    base.tool = normalize_tool(raw.get("tool"), raw.get("toolW"))
    return base


def _seg_cross(p1: Sample, p2: Sample, p3: Sample, p4: Sample) -> Optional[Sample]:
    dz1 = p2.z - p1.z
    dr1 = p2.r - p1.r
    dz2 = p4.z - p3.z
    dr2 = p4.r - p3.r
    d = dz1 * dr2 - dr1 * dz2
    if abs(d) < 1e-12:
        return None
    t = ((p3.z - p1.z) * dr2 - (p3.r - p1.r) * dz2) / d
    u = ((p3.z - p1.z) * dr1 - (p3.r - p1.r) * dz1) / d
    if 1e-6 < t < 1.0 - 1e-6 and 1e-6 < u < 1.0 - 1e-6:
        return Sample(z=p1.z + t * dz1, r=p1.r + t * dr1)
    return None


def trim_offset_loops(pts: List[Sample]) -> List[Sample]:
    cur = list(pts)
    for _ in range(len(cur)):
        cut = False
        for i in range(len(cur) - 1):
            if cut:
                break
            a1, a2 = cur[i], cur[i + 1]
            az0, az1 = min(a1.z, a2.z), max(a1.z, a2.z)
            ar0, ar1 = min(a1.r, a2.r), max(a1.r, a2.r)
            for j in range(i + 2, len(cur) - 1):
                b1, b2 = cur[j], cur[j + 1]
                if min(b1.z, b2.z) > az1 + 1e-9 or max(b1.z, b2.z) < az0 - 1e-9:
                    continue
                if min(b1.r, b2.r) > ar1 + 1e-9 or max(b1.r, b2.r) < ar0 - 1e-9:
                    continue
                P = _seg_cross(a1, a2, b1, b2)
                if P is not None:
                    cur = cur[: i + 1] + [P] + cur[j + 1 :]
                    cut = True
                    break
        if not cut:
            return cur
    return cur


def normal_offset(pts: List[Sample], dist_val: float, outward: bool) -> List[Sample]:
    n = len(pts)
    if n == 0:
        return []
    if n == 1 or dist_val == 0:
        return [s.copy() for s in pts]
    z_min = min(s.z for s in pts)
    z_max = max(s.z for s in pts)
    z_mid = (z_min + z_max) / 2.0
    out: List[Sample] = []
    for i in range(n):
        a = pts[max(0, i - 1)]
        b = pts[min(n - 1, i + 1)]
        tl = math.hypot(b.z - a.z, b.r - a.r)
        if tl < 1e-9:
            nz, nr = 0.0, 1.0
        else:
            tz = (b.z - a.z) / tl
            tr = (b.r - a.r) / tl
            nz, nr = -tr, tz
        if abs(nr) < 1e-9:
            sgn = 1.0 if pts[i].z >= z_mid else -1.0
            nz = sgn if outward else -sgn
            nr = 0.0
        elif (nr < 0) if outward else (nr > 0):
            nz = -nz
            nr = -nr
        out.append(Sample(z=pts[i].z + dist_val * nz, r=pts[i].r + dist_val * nr))
    return trim_offset_loops(out)


def continuous_path_offset(pts: List[Sample], dist_val: float, left_side: bool = True) -> List[Sample]:
    clean: List[Sample] = []
    for i, point in enumerate(pts):
        if i == 0 or math.hypot(point.z - pts[i - 1].z, point.r - pts[i - 1].r) > 1e-9:
            clean.append(point)
    n = len(clean)
    if n < 2 or dist_val == 0:
        return [p.copy() for p in clean]
    sign = 1.0 if left_side else -1.0
    segments = []
    for i in range(n - 1):
        a, b = clean[i], clean[i + 1]
        length = math.hypot(b.z - a.z, b.r - a.r)
        tz = (b.z - a.z) / length
        tr = (b.r - a.r) / length
        nz = -tr * sign
        nr = tz * sign
        segments.append(
            {
                "tz": tz,
                "tr": tr,
                "a": Sample(z=a.z + nz * dist_val, r=a.r + nr * dist_val),
                "b": Sample(z=b.z + nz * dist_val, r=b.r + nr * dist_val),
            }
        )
    out: List[Sample] = [segments[0]["a"].copy()]
    for i in range(1, n - 1):
        prev = segments[i - 1]
        nxt = segments[i]
        cross = prev["tz"] * nxt["tr"] - prev["tr"] * nxt["tz"]
        joined: Optional[Sample] = None
        if abs(cross) >= 1e-8:
            qz = nxt["a"].z - prev["a"].z
            qr = nxt["a"].r - prev["a"].r
            t = (qz * nxt["tr"] - qr * nxt["tz"]) / cross
            cand = Sample(z=prev["a"].z + prev["tz"] * t, r=prev["a"].r + prev["tr"] * t)
            miter = math.hypot(cand.z - clean[i].z, cand.r - clean[i].r)
            if math.isfinite(miter) and miter <= max(0.05, abs(dist_val) * 2.5):
                joined = cand
        if joined is not None:
            out.append(joined)
        else:
            out.append(prev["b"].copy())
            if math.hypot(nxt["a"].z - prev["b"].z, nxt["a"].r - prev["b"].r) > 1e-9:
                out.append(nxt["a"].copy())
    out.append(segments[-1]["b"].copy())

    clipped: List[Sample] = []
    for i, point in enumerate(out):
        if point.r >= -1e-9:
            clipped.append(Sample(z=point.z, r=max(0.0, point.r)))
            continue
        if clipped and i > 0:
            prev_pt = out[i - 1]
            t = prev_pt.r / max(1e-12, prev_pt.r - point.r)
            clipped.append(Sample(z=prev_pt.z + (point.z - prev_pt.z) * t, r=0.0))
        break
    result = clipped if len(clipped) >= 2 else [Sample(z=p.z, r=max(0.0, p.r)) for p in out]
    result = trim_offset_loops(result)
    if result:
        last = result[-1]
        if last.r > 1e-9:
            if len(result) >= 2 and last.r < result[-2].r - 1e-9:
                prev_pt = result[-2]
                t = last.r / (prev_pt.r - last.r)
                result.append(Sample(z=last.z + (last.z - prev_pt.z) * t, r=0.0))
            else:
                result.append(Sample(z=last.z, r=0.0))
        else:
            last.r = 0.0
    return result


def _cr(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    t2 = t * t
    t3 = t2 * t
    return 0.5 * (
        2.0 * p1
        + (-p0 + p2) * t
        + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
        + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
    )


def sample_profile(points: List[PPoint], blank_r: float) -> List[Sample]:
    clamp_r = lambda r: min(max(r, 0.0), blank_r)
    pts = sorted(points, key=lambda a: a.z)
    out: List[Sample] = []
    if not pts:
        return out
    if len(pts) == 1:
        return [Sample(z=pts[0].z, r=clamp_r(pts[0].r))]
    for i in range(len(pts) - 1):
        p0 = pts[max(0, i - 1)]
        p1 = pts[i]
        p2 = pts[i + 1]
        p3 = pts[min(len(pts) - 1, i + 2)]
        seg_len = math.hypot(p2.z - p1.z, p2.r - p1.r)
        steps = max(6, int(math.ceil(seg_len / 1.2)))
        smooth = p1.smooth and p2.smooth
        start_j = 0 if i == 0 else 1
        for j in range(start_j, steps + 1):
            t = j / steps
            if smooth:
                z = _cr(p0.z, p1.z, p2.z, p3.z, t)
                r = _cr(p0.r, p1.r, p2.r, p3.r, t)
            else:
                z = p1.z + (p2.z - p1.z) * t
                r = p1.r + (p2.r - p1.r) * t
            out.append(Sample(z=z, r=clamp_r(r)))
    out.sort(key=lambda a: a.z)
    return out


def sample_ordered_profile(points: List[PPoint], blank_r: float) -> List[Sample]:
    clamp_r = lambda r: min(max(r, 0.0), blank_r)
    pts = list(points)
    out: List[Sample] = []
    for i in range(len(pts) - 1):
        p0 = pts[max(0, i - 1)]
        p1 = pts[i]
        p2 = pts[i + 1]
        p3 = pts[min(len(pts) - 1, i + 2)]
        steps = max(6, int(math.ceil(math.hypot(p2.z - p1.z, p2.r - p1.r) / 1.2)))
        start_j = 0 if i == 0 else 1
        for j in range(start_j, steps + 1):
            t = j / steps
            if p1.smooth and p2.smooth:
                out.append(Sample(z=_cr(p0.z, p1.z, p2.z, p3.z, t), r=clamp_r(_cr(p0.r, p1.r, p2.r, p3.r, t))))
            else:
                out.append(Sample(z=p1.z + (p2.z - p1.z) * t, r=clamp_r(p1.r + (p2.r - p1.r) * t)))
    return out


def inner_rough_envelope(path: List[Sample]) -> List[Sample]:
    sorted_pts = sorted(path, key=lambda a: a.z)
    out: List[Sample] = []
    for point in sorted_pts:
        if out and abs(out[-1].z - point.z) < 0.06:
            if point.r < out[-1].r:
                out[-1].r = point.r
        else:
            out.append(point.copy())
    return out


def cut_intervals(samples: List[Sample], layer: float) -> List[Dict[str, float]]:
    raw: List[Dict[str, float]] = []
    cur: Optional[Dict[str, float]] = None
    for s in samples:
        if s.r < layer - 0.01:
            if cur is None:
                cur = {"a": s.z, "b": s.z}
            else:
                cur["b"] = s.z
        elif cur is not None:
            raw.append(cur)
            cur = None
    if cur is not None:
        raw.append(cur)
    merged: List[Dict[str, float]] = []
    for iv in raw:
        if merged and iv["a"] - merged[-1]["b"] < 0.9:
            merged[-1]["b"] = iv["b"]
        else:
            merged.append({"a": iv["a"], "b": iv["b"]})
    return [iv for iv in merged if iv["b"] - iv["a"] > 0.3]


def find_zones(samples: List[Sample]) -> List[Dict[str, float]]:
    n = len(samples)
    z0 = samples[0].z if n else 0.0
    z1 = samples[-1].z if n else 0.0
    if n < 7:
        return [{"a": z0, "b": z1}]
    rs: List[float] = []
    for i in range(n):
        lo = max(0, i - 2)
        hi = min(n - 1, i + 2)
        rs.append(sum(samples[j].r for j in range(lo, hi + 1)) / (hi - lo + 1))
    dz = (z1 - z0) / (n - 1)
    W = max(3, int(round(6.0 / max(0.2, dz))))
    min_r = min(rs)
    max_r = max(rs)
    prom = max(0.5, (max_r - min_r) * 0.05)

    peaks: List[Dict[str, float]] = []
    valleys: List[Dict[str, float]] = []
    for i in range(W, n - W):
        window = rs[i - W : i + W + 1]
        is_max = all(v <= rs[i] for v in window)
        is_min = all(v >= rs[i] for v in window)
        if is_max:
            peaks.append({"z": samples[i].z, "r": rs[i]})
        elif is_min:
            valleys.append({"z": samples[i].z, "r": rs[i]})

    peak_bounds: List[Dict[str, float]] = []
    for pk in peaks:
        left_r = rs[0]
        right_r = rs[-1]
        found_left = False
        found_right = False
        for v in valleys:
            if v["z"] < pk["z"]:
                left_r = v["r"]
                found_left = True
            elif v["z"] > pk["z"] and not found_right:
                right_r = v["r"]
                found_right = True
        if not found_left:
            left_r = rs[0]
        if not found_right:
            right_r = rs[-1]
        if pk["r"] - max(left_r, right_r) > prom:
            peak_bounds.append(pk)

    dedup_peak: List[Dict[str, float]] = []
    for pk in peak_bounds:
        if dedup_peak and pk["z"] - dedup_peak[-1]["z"] < 3.0:
            if pk["r"] > dedup_peak[-1]["r"]:
                dedup_peak[-1] = pk
        else:
            dedup_peak.append(pk)

    bounds = sorted([z0] + [p["z"] for p in dedup_peak] + [z1])
    zones = [{"a": bounds[i], "b": bounds[i + 1]} for i in range(len(bounds) - 1) if bounds[i + 1] - bounds[i] > 0.3]
    merged: List[Dict[str, float]] = []
    for z in zones:
        if z["b"] - z["a"] < 4.0 and merged:
            merged[-1]["b"] = z["b"]
        else:
            merged.append({"a": z["a"], "b": z["b"]})
    if len(merged) > 1 and merged[-1]["b"] - merged[-1]["a"] < 4.0:
        merged[-2]["b"] = merged[-1]["b"]
        merged.pop()
    return merged if merged else [{"a": z0, "b": z1}]


def resolve_zones(samples: List[Sample], manual_bounds: List[float], z0: float, z1: float) -> List[Dict[str, float]]:
    if manual_bounds:
        filtered = sorted(v for v in manual_bounds if z0 + 0.3 < v < z1 - 0.3)
        bounds: List[float] = []
        for v in filtered:
            if not bounds or v - bounds[-1] >= 1.0:
                bounds.append(v)
        if bounds:
            all_b = [z0] + bounds + [z1]
            zones = [{"a": all_b[i], "b": all_b[i + 1]} for i in range(len(all_b) - 1) if all_b[i + 1] - all_b[i] > 0.3]
            if zones:
                return zones
    return find_zones(samples)


def machine_uv(zw: float, xw: float, holder: int, p: Params) -> Dict[str, float]:
    if holder == 2:
        return {"u": zw + p.holder2.xOff, "v": xw / 2.0 - p.holder2.yOff}
    return {"u": zw, "v": xw / 2.0}


def exec_uv(s: Seg, end: bool, p: Params) -> Dict[str, float]:
    m = machine_uv(s.z2 if end else s.z1, s.x2 if end else s.x1, s.holder, p)
    if not s.fan and not s.fanU:
        return m
    return {"u": m["u"] + (s.fanU or 0.0), "v": m["v"] + (s.fan or 0.0)}


def _norm_feed(sg: Seg, p: Params) -> float:
    op_feed = None if sg.kind == "rapid" or not p.feedByKind else p.feedByKind.get(sg.kind)
    if op_feed is not None and not sg.feedOvr:
        return min(20000.0, max(1.0, float(op_feed)))
    if sg.feedOvr or not p.simpleFeed:
        return sg.feed
    return p.feedFinish if sg.kind in FINISH_KINDS else p.feedRough


def plan_bridges(segs: List[Seg], p: Params) -> Dict[str, Any]:
    n = len(segs)
    starts = [exec_uv(s, False, p) for s in segs]
    ends = [exec_uv(s, True, p) for s in segs]
    max_u = max([pt["u"] for pt in starts + ends], default=float("-inf"))
    max_v = max([pt["v"] for pt in starts + ends], default=float("-inf"))
    home_v = rotational_envelope(p.blankD, p.blankShape)["maxRotD"] + 20.0
    home = {"u": p.blankL + 10.0, "v": home_v / 2.0}
    max_u = max(max_u, home["u"])
    max_v = max(max_v, home["v"])
    tc = {"u": max_u + p.safety, "v": max_v + p.safety}
    bridges: List[Dict[str, Any]] = []
    jump = lambda a, b: math.hypot(a["u"] - b["u"], a["v"] - b["v"])
    jmin = BRIDGE_MIN_JUMP / 2.0

    def legs_for(a: Dict[str, float], b: Dict[str, float], absorb: bool, tcu: float, rd: float) -> List[Dict[str, float]]:
        ty = b["v"] if absorb else b["v"] + rd
        legs = [
            {"u": tcu, "v": a["v"] + rd},
            {"u": tcu, "v": ty},
            {"u": b["u"], "v": b["v"]},
        ]
        return legs[:2] if absorb else legs

    def absorbable(j: int) -> bool:
        return segs[j].motion == 0 and abs(ends[j]["v"] - starts[j]["v"]) < 1e-9

    nz = [i for i in range(n) if jump(starts[i], ends[i]) > 1e-9]

    def mk_bridge(at_index: int, from_h: int, to_h: int, from_pt: Dict[str, float]) -> None:
        b = starts[at_index]
        absorb = absorbable(at_index)
        btcu = tc["u"] + (len(bridges) * 3.0 if p.spreadG0 else 0.0)
        rd = len(bridges) * 3.0 if p.spreadG0 else 0.0
        bridges.append(
            {
                "atIndex": at_index,
                "fromH": from_h,
                "toH": to_h,
                "from": from_pt,
                "legs": legs_for(from_pt, b, absorb, btcu, rd),
                "absorbed": absorb,
            }
        )

    pstart = lambda j: machine_uv(segs[j].z1, segs[j].x1, segs[j].holder, p)
    pend = lambda j: machine_uv(segs[j].z2, segs[j].x2, segs[j].holder, p)
    if nz and jump(home, pstart(nz[0])) > jmin:
        mk_bridge(nz[0], 1, segs[nz[0]].holder, home)
    for k in range(1, len(nz)):
        i = nz[k]
        pv = nz[k - 1]
        if jump(pend(pv), pstart(i)) > jmin:
            mk_bridge(i, segs[pv].holder, segs[i].holder, ends[pv])

    return {"tc": tc, "home": home, "bridges": bridges}


def build_std_lines(segs: List[Seg], p: Params) -> List[str]:
    lines: List[str] = []
    n_word = 0

    def emit(code: str) -> int:
        nonlocal n_word
        n_word += 10
        lines.append(f"N{n_word} {code}" if p.lineNumbers else code)
        return len(lines) - 1

    lines.append("%")
    lines.append("O1001 (KHARRATKOD - 2 AXIS WOOD LATHE)")
    lines.append(f"(STOCK D{p.blankD:g} x L{p.blankL:g} MM)")
    lines.append(f"(TOOL: {tool_desc(p.tool)})")
    lines.append(
        f"(DOC OUT {p.doc:g} MM - DOC INNER {p.innerDoc:g} MM - OFFSET OUT {p.offsetDist:g} MM - INNER {p.innerOffsetDist:g} MM - INNER START {p.innerStartClearance:g} MM - INNER END +X {p.innerEndTravel:g} MM - BOTTOM/ROUGH OVERLAP {p.bottomRoughOverlap:g} MM - BOTTOM/OFFSET CLEARANCE {p.bottomOffsetClearance:g} MM)"
    )
    uses_h2 = any(s.motion == 1 and s.holder == 2 for s in segs)
    if uses_h2:
        lines.append(f"(HOLDER2: XOFF {p.holder2.xOff:g} YOFF {p.holder2.yOff:g} ROT {HOLDER2_ROT})")
        lines.append("(H2 MAP: Xm = Xw + XOFF , Ym = Yw/2 - YOFF)")
    emit("G21 G18 G40")
    plan = plan_bridges(segs, p)
    bridge_at = {b["atIndex"]: b for b in plan["bridges"]}
    from_home = p.spreadG0 or not segs
    mu = plan["home"]["u"] if from_home else exec_uv(segs[0], False, p)["u"]
    mv = plan["home"]["v"] if from_home else exec_uv(segs[0], False, p)["v"]
    last_feed = -1

    for i, sg in enumerate(segs):
        e1 = exec_uv(sg, False, p)
        e2 = exec_uv(sg, True, p)
        br = bridge_at.get(i)
        if br is not None:
            lines.append(f"(HOLDER {br['fromH']} -> {br['toH']})")
            pu, pv = br["from"]["u"], br["from"]["v"]
            for j, leg in enumerate(br["legs"]):
                if math.hypot(leg["u"] - pu, leg["v"] - pv) < 1e-9:
                    continue
                move = sg.bridgeMoves.get(j) if sg.bridgeMoves else None
                if move and move.get("motion") == 1:
                    F = max(1, int(round(float(move["feed"]))))
                    emit(f"G1 X{_f2(leg['v'])} Z{_f2(leg['u'])} F{F}")
                    last_feed = F
                else:
                    emit(f"G0 X{_f2(leg['v'])} Z{_f2(leg['u'])}")
                pu, pv = leg["u"], leg["v"]
                mu, mv = leg["u"], leg["v"]

        if not (br and br["absorbed"]) and math.hypot(e1["u"] - mu, e1["v"] - mv) > 1e-9:
            move = sg.bridgeMoves.get(8) if sg.bridgeMoves else None
            if move and move.get("motion") == 1:
                F = max(1, int(round(float(move["feed"]))))
                emit(f"G1 X{_f2(e1['v'])} Z{_f2(e1['u'])} F{F}")
                last_feed = F
            else:
                emit(f"G0 X{_f2(e1['v'])} Z{_f2(e1['u'])}")
            mu, mv = e1["u"], e1["v"]

        if sg.note:
            for c in sg.note:
                lines.append(f"({c})")
        if sg.motion == 0:
            sg.line = emit(f"G0 X{_f2(e2['v'])} Z{_f2(e2['u'])}")
        else:
            F = max(1, int(round(_norm_feed(sg, p))))
            f_word = f" F{F}" if (not p.simpleFeed or F != last_feed) else ""
            last_feed = F
            sg.line = emit(f"G1 X{_f2(e2['v'])} Z{_f2(e2['u'])}{f_word}")
        mu, mv = e2["u"], e2["v"]
        if i == 0:
            emit(f"M3 S{int(round(p.rpm))}")
            emit("G4 P2")

    emit("M5")
    emit("M30")
    lines.append("%")
    return lines


def build_modal_lines(segs: List[Seg], p: Params) -> List[str]:
    lines: List[str] = ["%", "G21 G40 G90", "G49", f"M3 S{int(round(p.rpm))}"]
    uses_h2 = any(s.motion == 1 and s.holder == 2 for s in segs)
    if uses_h2:
        lines.append(f"(HOLDER2 XOFF {p.holder2.xOff:g} YOFF {p.holder2.yOff:g} ROT {HOLDER2_ROT} : Xm=Xw+XOFF Ym=Yw/2-YOFF)")
    mode = -1
    m_feed = -1
    last_op = "sys"
    last_holder = 1
    plan = plan_bridges(segs, p)
    bridge_at = {b["atIndex"]: b for b in plan["bridges"]}
    lines.append(f"G0 X{_f3(plan['home']['u'])} Y{_f3(plan['home']['v'])}")
    mode = 0
    mu = plan["home"]["u"]
    mv = plan["home"]["v"]

    for i, sg in enumerate(segs):
        e1 = exec_uv(sg, False, p)
        e2 = exec_uv(sg, True, p)
        if sg.op != last_op or sg.holder != last_holder:
            lines.append("")
        last_op = sg.op
        last_holder = sg.holder
        br = bridge_at.get(i)
        if br is not None:
            lines.append(f"(HOLDER {br['fromH']} -> {br['toH']})")
            pu, pv = br["from"]["u"], br["from"]["v"]
            for j, leg in enumerate(br["legs"]):
                if math.hypot(leg["u"] - pu, leg["v"] - pv) < 1e-9:
                    continue
                move = sg.bridgeMoves.get(j) if sg.bridgeMoves else None
                if move and move.get("motion") == 1:
                    F = max(1, int(round(float(move["feed"]))))
                    lines.append(f"G1 X{_f3(leg['u'])} Y{_f3(leg['v'])} F{F}")
                    mode = 1
                    m_feed = F
                else:
                    lines.append(f"G0 X{_f3(leg['u'])} Y{_f3(leg['v'])}")
                    mode = 0
                pu, pv = leg["u"], leg["v"]
                mu, mv = leg["u"], leg["v"]

        if not (br and br["absorbed"]) and math.hypot(e1["u"] - mu, e1["v"] - mv) > 1e-9:
            sw: List[str] = []
            if abs(e1["u"] - mu) > 1e-9:
                sw.append(f"X{_f3(e1['u'])}")
            if abs(e1["v"] - mv) > 1e-9:
                sw.append(f"Y{_f3(e1['v'])}")
            move = sg.bridgeMoves.get(8) if sg.bridgeMoves else None
            if move and move.get("motion") == 1:
                F = max(1, int(round(float(move["feed"]))))
                lines.append(f"G1 {' '.join(sw)} F{F}")
                mode = 1
                m_feed = F
            else:
                lines.append(f"G0 {' '.join(sw)}")
                mode = 0
            mu, mv = e1["u"], e1["v"]

        words: List[str] = []
        if abs(e2["u"] - mu) > 1e-9:
            words.append(f"X{_f3(e2['u'])}")
        if abs(e2["v"] - mv) > 1e-9:
            words.append(f"Y{_f3(e2['v'])}")
        if not words:
            sg.line = len(lines) - 1
            continue
        if sg.motion == 0:
            lines.append(f"G0 {' '.join(words)}")
            mode = 0
        else:
            F = max(1, int(round(_norm_feed(sg, p))))
            f_changed = F != m_feed
            g_prefix = "G1 " if mode != 1 else ""
            f_suffix = f" F{F}" if f_changed else ""
            lines.append(f"{g_prefix}{' '.join(words)}{f_suffix}")
            if f_changed:
                m_feed = F
            mode = 1
        sg.line = len(lines) - 1
        mu, mv = e2["u"], e2["v"]

    lines.extend(["", "M05", "M02", "%"])
    return lines


def generate(
    pts: List[PPoint],
    p: Params,
    inner_pts: Optional[List[PPoint]] = None,
    outer_finish_pts: Optional[List[PPoint]] = None,
) -> GenResult:
    R = p.blankD / 2.0
    samples = sample_profile(pts, R)
    outer_finish_path = (
        sample_ordered_profile(outer_finish_pts, R)
        if outer_finish_pts and len(outer_finish_pts) >= 2
        else list(samples)
    )
    if len(outer_finish_path) >= 2 and outer_finish_path[-1].z < outer_finish_path[0].z:
        outer_finish_path = list(reversed(outer_finish_path))

    inner_path_samples = (
        sample_ordered_profile(inner_pts, R)
        if p.split.enabled and inner_pts and len(inner_pts) >= 2
        else []
    )
    inner_finish_path = list(reversed(inner_path_samples))
    inner_samples = inner_rough_envelope(inner_path_samples)
    segs: List[Seg] = []
    has_outer = len(samples) >= 2
    has_inner = len(inner_samples) >= 2

    if not has_outer and not has_inner:
        return GenResult(
            lines=["%", "M05" if p.format == "modal" else "(NO PROFILE)", "M02", "%"],
            segs=[],
            samples=samples,
            innerSamples=inner_samples,
            cutLen=0.0,
            rapidLen=0.0,
            timeSec=0.0,
            volumeCm3=0.0,
            roughLayers=0,
            format=p.format,
        )

    env_rot = rotational_envelope(p.blankD, p.blankShape)
    env_max_rot_d = float(env_rot["maxRotD"])
    corners_cleared = not bool(env_rot["hasCorners"])
    home = {"x": env_max_rot_d + 20.0, "z": p.blankL + 10.0}
    retract_x = env_max_rot_d + 2.0 * p.safety
    cur = {"x": home["x"], "z": home["z"]}
    cur_op = "sys"
    cur_op_id = -1
    cur_holder = 1
    notes: List[str] = []

    def note(s: str) -> None:
        notes.append(s)

    def push_seg(motion: Literal[0, 1], x: float, z: float, feed: float, kind: SegKind) -> None:
        nonlocal notes, cur
        segs.append(
            Seg(
                motion=motion,
                x1=cur["x"],
                z1=cur["z"],
                x2=x,
                z2=z,
                feed=feed if motion == 1 else RAPID_RATE,
                line=-1,
                kind=kind,
                op=cur_op,
                opId=cur_op_id,
                holder=cur_holder,
                note=list(notes) if notes else None,
            )
        )
        notes = []
        cur = {"x": x, "z": z}

    def mv(motion: Literal[0, 1], x: float, z: float, feed: float, kind: SegKind) -> None:
        if motion == 0:
            eps = 1e-9
            if cur["x"] < retract_x - eps:
                push_seg(0, retract_x, cur["z"], 0.0, "rapid")
            if abs(z - cur["z"]) > eps:
                push_seg(0, max(cur["x"], retract_x), z, 0.0, "rapid")
            if abs(x - cur["x"]) > eps:
                push_seg(0, x, z, 0.0, "rapid")
            return
        op_feed = None if kind == "rapid" or not p.feedByKind else p.feedByKind.get(kind)
        push_seg(1, x, z, feed if op_feed is None else min(20000.0, max(1.0, float(op_feed))), kind)

    def raw_rapid(x: float, z: float) -> None:
        push_seg(0, x, z, 0.0, "rapid")

    first_inner_entry_done = False

    def enter_first_inner(entry_x: float, mouth_x: float) -> None:
        nonlocal first_inner_entry_done, cur_holder, cur
        if first_inner_entry_done:
            mv(0, entry_x, mouth_x, 0.0, "rapid")
            return
        last_holder = segs[-1].holder if segs else 1
        if last_holder == 1:
            cur_holder = 1
            safe_d = max(retract_x, cur["x"])
            if safe_d > cur["x"] + 1e-9:
                raw_rapid(safe_d, cur["z"])
            entry_machine_x = mouth_x + p.holder2.xOff
            raw_rapid(safe_d, entry_machine_x)
            safe_machine_y = safe_d / 2.0
            cur_holder = 2
            cur = {"z": mouth_x, "x": 2.0 * (safe_machine_y + p.holder2.yOff)}
            raw_rapid(entry_x, mouth_x)
        else:
            cur_holder = 2
            mv(0, entry_x, mouth_x, 0.0, "rapid")
        first_inner_entry_done = True

    z0 = samples[0].z if has_outer else 0.0
    z_end = samples[-1].z if has_outer else p.blankL
    r0 = samples[0].r if has_outer else R
    min_r = min((s.r for s in samples), default=float("inf"))

    od = max(0.0, p.offsetDist)
    iod = max(0.0, p.innerOffsetDist)

    inner_finish_off_samples: List[Sample] = (
        list(reversed(continuous_path_offset(inner_path_samples, iod, True))) if has_inner else []
    )
    inner_operation_boundary_z = (
        max(pt.z for pt in inner_finish_off_samples) if inner_finish_off_samples else z_end
    )
    bottom_operation_end_z = min(p.blankL, inner_operation_boundary_z + p.bottomOffsetClearance)

    last_runnable_inner_op_id: Optional[int] = None
    for o in reversed(p.ops):
        if not o.on:
            continue
        if o.type == "bottom" and has_outer and p.blankL - bottom_operation_end_z > 0.05:
            last_runnable_inner_op_id = o.id
            break
        if o.type == "inner-offset" and has_inner and iod > 0.01:
            last_runnable_inner_op_id = o.id
            break
        if has_inner and o.type in ("inner-rough", "inner-finish"):
            last_runnable_inner_op_id = o.id
            break

    def next_enabled_op(op_id: int) -> Optional[Op]:
        at = next((idx for idx, o in enumerate(p.ops) if o.id == op_id), -1)
        if at < 0:
            return None
        return next((o for o in p.ops[at + 1 :] if o.on), None)

    def next_is_inner_path(op_id: int) -> bool:
        nxt = next_enabled_op(op_id)
        return bool(nxt and nxt.type in ("inner-offset", "inner-finish", "inner-rough"))

    def move_inner_to_axis_safely() -> None:
        current_r = max(0.0, cur["x"] / 2.0)
        peak = float("-inf")
        for pt in inner_finish_off_samples:
            if pt.r <= current_r + 1e-6:
                peak = max(peak, pt.z)
        safe_z = max(cur["z"], peak + p.safety if math.isfinite(peak) else cur["z"])
        if safe_z > cur["z"] + 1e-7:
            raw_rapid(cur["x"], safe_z)
        if current_r > 1e-7:
            raw_rapid(0.0, safe_z)

    ended_at_inner_endpoint = False

    def finish_last_inner(op_id: int) -> bool:
        nonlocal ended_at_inner_endpoint
        if op_id != last_runnable_inner_op_id:
            return False
        at = next((idx for idx, o in enumerate(p.ops) if o.id == op_id), -1)
        if at >= 0 and any(o.on for o in p.ops[at + 1 :]):
            return False
        note(f"FINAL INNER END +X {_f2(p.innerEndTravel)} MM")
        raw_rapid(cur["x"], cur["z"] + p.innerEndTravel)
        ended_at_inner_endpoint = True
        return True

    off_samples = normal_offset(samples, od, True)
    rough_off_samples: List[Sample] = []
    if off_samples:
        if off_samples[0].z > 1e-9:
            rough_off_samples.append(Sample(z=0.0, r=off_samples[0].r))
        rough_off_samples.extend(off_samples)
        if off_samples[-1].z < p.blankL - 1e-9:
            rough_off_samples.append(Sample(z=p.blankL, r=off_samples[-1].r))
    floor_r = min_r + od

    ng = 600
    phys_r = [float(env_rot["outR"])] * (ng + 1)

    def phys_cut(a: float, b: float, r_val: float) -> None:
        i0 = max(0, int(round((min(a, b) / p.blankL) * ng)))
        i1 = min(ng, int(round((max(a, b) / p.blankL) * ng)))
        for idx in range(i0, i1 + 1):
            if r_val < phys_r[idx]:
                phys_r[idx] = r_val

    def min_safe_radius(z_from: float, z_to: float) -> float:
        lo, hi = min(z_from, z_to), max(z_from, z_to)
        i0 = max(0, int(round((lo / p.blankL) * ng)))
        i1 = min(ng, int(round((hi / p.blankL) * ng)))
        mx = max(phys_r[i0 : i1 + 1], default=0.0)
        return mx + p.safety

    def radius_at(z_val: float) -> float:
        if not samples:
            return R
        if z_val <= samples[0].z:
            return samples[0].r
        for idx in range(1, len(samples)):
            if samples[idx].z >= z_val:
                a, b = samples[idx - 1], samples[idx]
                t = (z_val - a.z) / max(1e-9, b.z - a.z)
                return a.r + (b.r - a.r) * t
        return samples[-1].r

    def offset_radius_at(z_val: float) -> float:
        if not off_samples:
            return R
        if z_val <= off_samples[0].z:
            return off_samples[0].r
        for idx in range(1, len(off_samples)):
            if off_samples[idx].z >= z_val:
                a, b = off_samples[idx - 1], off_samples[idx]
                t = (z_val - a.z) / max(1e-9, b.z - a.z)
                return a.r + (b.r - a.r) * t
        return off_samples[-1].r

    def ramp_is_safe(from_z: float, from_r: float, to_z: float, to_r: float) -> bool:
        if not math.isfinite(from_z) or not off_samples:
            return False
        lo_z, hi_z = min(from_z, to_z), max(from_z, to_z)
        steps = max(8, int(math.ceil(abs(hi_z - lo_z) / 2.0)))
        for idx in range(steps + 1):
            t = idx / steps
            z_val = from_z + (to_z - from_z) * t
            r_val = from_r + (to_r - from_r) * t
            if z_val < off_samples[0].z - 0.01 or z_val > off_samples[-1].z + 0.01:
                continue
            if r_val < offset_radius_at(z_val) - 0.05:
                return False
        return True

    def profile_path(kind: SegKind, feed: float, reverse: bool = False) -> None:
        source = outer_finish_path if kind == "finish" else samples
        path = list(reversed(source)) if reverse else source
        if not path:
            return
        mv(1, 2.0 * path[0].r, path[0].z, feed, kind)
        for pt in path[1:]:
            mv(1, 2.0 * pt.r, pt.z, feed, kind)

    inner_cleared = False
    split_plane_already_cut = False
    radial_rough_end_r: Optional[float] = None
    bottom_covered_from_z: Optional[float] = None
    bottom_to_inner_rough_ready = False
    bottom_to_inner_rough_direct = False

    for op in p.ops:
        if not op.on:
            continue
        cur_op_id = op.id
        cur_holder = op.holder

        if op.type == "round":
            cur_op = "round"
            envr = rotational_envelope(p.blankD, p.blankShape)
            if envr["hasCorners"] and envr["outR"] > R + 0.02:
                sh_name = next((b["name"] for b in BLANK_SHAPES if b["id"] == p.blankShape), p.blankShape)
                note(f"ROUNDING CORNERS - {_f2(2.0 * envr['outR'])} TO {_f2(2.0 * R)} (ZIGZAG)")
                round_layers: List[float] = []
                layer = float(envr["outR"]) - p.doc
                guard = 0
                while layer > R + 1e-6 and guard < 40:
                    round_layers.append(layer)
                    layer -= p.doc
                    guard += 1
                round_layers.append(R)
                direction = -1 if op.reverse else 1
                at_z = 0.0
                for i, r_val in enumerate(round_layers):
                    start_z = 0.0 if direction == 1 else p.blankL
                    end_z = p.blankL if direction == 1 else 0.0
                    note(f"ROUND LAYER X{_f2(r_val)}{' (RETURN)' if direction == -1 else ''}")
                    if i == 0:
                        mv(0, retract_x, start_z, 0.0, "rapid")
                    mv(1, 2.0 * r_val, start_z, p.feedRough * 0.7, "round")
                    if abs(end_z - start_z) > 0.01:
                        mv(1, 2.0 * r_val, end_z, p.feedRough, "round")
                    at_z = end_z
                    direction = -1 if direction == 1 else 1
                corners_cleared = True
                for idx in range(len(phys_r)):
                    phys_r[idx] = R
                note(f"ROUND DONE AT X{_f2(R)} ({sh_name})")
                mv(0, retract_x, at_z, 0.0, "rapid")

        elif op.type == "face":
            cur_op = "face"
            if has_outer and R - r0 > 0.05:
                note("FACING")
                mv(0, retract_x, z0, 0.0, "face")
                mv(1, 2.0 * r0, z0, p.feedRough * 0.8, "face")
                mv(0, retract_x, z0, 0.0, "rapid")

        elif op.type == "bottom":
            cur_op = "bottom"
            if not has_outer:
                continue
            bottom_end_z = bottom_operation_end_z
            excess = p.blankL - bottom_end_z
            if excess > 0.05:
                note(f"BOTTOM FACING - EXCESS {_f2(excess)} (HOLDER {op.holder})")
                full_outside_r = (R + p.safety) if corners_cleared else (float(env_rot["outR"]) + p.safety)
                outside_r = (
                    full_outside_r
                    if radial_rough_end_r is None
                    else min(full_outside_r, radial_rough_end_r + p.bottomRoughOverlap)
                )
                outside_d = 2.0 * outside_r
                center_d = 0.0
                N = max(1, int(math.ceil(excess / p.innerDoc - 1e-9)))
                depths = [bottom_end_z if i == N - 1 else p.blankL - (i + 1) * p.innerDoc for i in range(N)]
                machining_depths = [zk for zk in depths if not (abs(zk - bottom_end_z) < 0.05 and split_plane_already_cut)]
                zigzag_bottom = p.innerRoughMode != "classic"
                if zigzag_bottom:
                    note(f"BOTTOM SERPENTINE {len(machining_depths)} PASSES - CUTS BOTH Y DIRECTIONS")
                first_bottom_forward = not op.reverse
                first_bottom_d = center_d if first_bottom_forward else outside_d
                first_zk = machining_depths[0] if machining_depths else depths[0]
                enter_first_inner(first_bottom_d, first_zk + p.innerStartClearance)
                for k, zk in enumerate(machining_depths):
                    forward = (first_bottom_forward if k % 2 == 0 else not first_bottom_forward) if zigzag_bottom else first_bottom_forward
                    start_d = center_d if forward else outside_d
                    end_d = outside_d if forward else center_d
                    is_split_plane = abs(zk - bottom_end_z) < 0.05
                    if k == 0:
                        if abs(p.innerStartClearance) > 1e-9:
                            mv(1, start_d, zk, p.feedRough * 0.8, "bottom")
                    elif zigzag_bottom:
                        mv(1, start_d, zk, p.feedRough * 0.7, "bottom")
                    else:
                        prev_z = machining_depths[k - 1]
                        reset_d = center_d if first_bottom_forward else outside_d
                        raw_rapid(reset_d, prev_z + 0.5)
                        mv(1, reset_d, zk, p.feedRough * 0.7, "bottom")
                    mv(1, end_d, zk, p.feedRough * 0.8, "bottom")
                    if is_split_plane and has_inner:
                        split_plane_already_cut = True
                if not finish_last_inner(op.id):
                    nxt_op = next_enabled_op(op.id)
                    if nxt_op and nxt_op.type == "inner-rough":
                        if p.safeBottomInnerLink:
                            raw_rapid(cur["x"], cur["z"] + p.safety)
                            bottom_to_inner_rough_ready = True
                        else:
                            bottom_to_inner_rough_direct = True
                    elif next_is_inner_path(op.id):
                        move_inner_to_axis_safely()
                    else:
                        mv(0, retract_x, bottom_end_z, 0.0, "rapid")
                phys_cut(bottom_end_z, p.blankL, 0.0)
                bottom_covered_from_z = bottom_end_z

        elif op.type == "rough-d":
            cur_op = "rough-d"
            if not has_outer:
                continue
            radial_end_z = (
                p.blankL
                if bottom_covered_from_z is None
                else min(p.blankL, bottom_covered_from_z + p.bottomRoughOverlap)
            )
            rough_run_samples = [s.copy() for s in rough_off_samples if s.z <= radial_end_z + 1e-9]
            if not rough_run_samples or rough_run_samples[-1].z < radial_end_z - 1e-9:
                rough_run_samples.append(Sample(z=radial_end_z, r=offset_radius_at(radial_end_z)))

            if p.roughMode == "zigzag":
                note("ROUGHING - CONTOUR SERPENTINE (ACTIVE REGIONS, CUTS BOTH WAYS)")
                F = rough_run_samples
                min_f = min((s.r for s in F), default=float("inf"))
                total_depth = R - min_f
                if total_depth > 0.02:
                    N = max(1, int(math.ceil(total_depth / p.doc - 1e-9)))

                    def max_f_in(a_val: float, b_val: float) -> float:
                        vals = [s.r for s in F if a_val - 0.01 <= s.z <= b_val + 0.01]
                        return max(vals) if vals else min_f

                    def simplify_pass(pass_pts: List[Sample]) -> List[Sample]:
                        if len(pass_pts) <= 2:
                            return pass_pts
                        keep = [False] * len(pass_pts)
                        keep[0] = True
                        keep[-1] = True
                        stack = [(0, len(pass_pts) - 1)]
                        while stack:
                            a_idx, b_idx = stack.pop()
                            A, B = pass_pts[a_idx], pass_pts[b_idx]
                            dz, dr = B.z - A.z, B.r - A.r
                            den = dz * dz + dr * dr
                            best = 0.0
                            at = -1
                            for idx in range(a_idx + 1, b_idx):
                                t = max(0.0, min(1.0, ((pass_pts[idx].z - A.z) * dz + (pass_pts[idx].r - A.r) * dr) / den)) if den > 1e-18 else 0.0
                                d = math.hypot(pass_pts[idx].z - (A.z + t * dz), pass_pts[idx].r - (A.r + t * dr))
                                if d > best:
                                    best = d
                                    at = idx
                            if at >= 0 and best > 0.02:
                                keep[at] = True
                                stack.append((a_idx, at))
                                stack.append((at, b_idx))
                        return [pt for idx, pt in enumerate(pass_pts) if keep[idx]]

                    forward = (abs(cur["z"]) > abs(radial_end_z - cur["z"])) if op.reverse else (abs(cur["z"]) <= abs(radial_end_z - cur["z"]))
                    first = True
                    last_end_z = float("nan")
                    last_end_r = 0.0
                    for j in range(1, N + 1):
                        prev_layer = R - (j - 1) * p.doc
                        layer = R - j * p.doc
                        active_raw = cut_intervals(F, prev_layer)
                        if not active_raw:
                            break
                        note(f"SERPENTINE PASS {j}/{N} - X{_f2(layer)}{'' if forward else ' (RETURN)'}")
                        active = active_raw if forward else list(reversed(active_raw))
                        for iv in active:
                            start_z = iv["a"] if forward else iv["b"]
                            end_z = iv["b"] if forward else iv["a"]
                            if first:
                                mv(0, retract_x, start_z, 0.0, "rapid")
                                first = False
                            else:
                                lo_z, hi_z = min(last_end_z, start_z), max(last_end_z, start_z)
                                clear_r = max(max_f_in(lo_z, hi_z) + p.safety, 0.0 if corners_cleared else float(env_rot["outR"]) + p.safety)
                                travel_r = max(last_end_r, clear_r)
                                if travel_r > last_end_r + 1e-6:
                                    raw_rapid(2.0 * travel_r, last_end_z)
                                raw_rapid(2.0 * travel_r, start_z)
                            c_start = max(offset_radius_at(start_z), layer)
                            mv(1, 2.0 * c_start, start_z, p.feedRough * 0.7, "rough")
                            lo, hi = min(start_z, end_z), max(start_z, end_z)
                            pts_in = [s for s in F if lo + 1e-6 < s.z < hi - 1e-6]
                            ordered = pts_in if forward else list(reversed(pts_in))
                            c_end = max(offset_radius_at(end_z), layer)
                            pass_pts = simplify_pass(
                                [Sample(z=start_z, r=c_start)]
                                + [Sample(z=s.z, r=max(s.r, layer)) for s in ordered]
                                + [Sample(z=end_z, r=c_end)]
                            )
                            for pt in pass_pts[1:]:
                                mv(1, 2.0 * pt.r, pt.z, p.feedRough, "rough")
                            last_end_z = end_z
                            last_end_r = c_end
                        forward = not forward
                    if not math.isnan(last_end_z):
                        mv(0, retract_x, last_end_z, 0.0, "rapid")
                        radial_rough_end_r = offset_radius_at(radial_end_z)
                continue

            note("ROUGHING - RADIAL LAYERS (BY ZONE)" if p.roughMode == "zone" else "ROUGHING - RADIAL LAYERS")
            if p.ramp:
                note("CONTINUOUS RAMP LINKS - NO G0 BETWEEN PASSES")
            cuts: List[Dict[str, float]] = []
            if p.roughMode == "zone":
                zones = resolve_zones(rough_run_samples, p.zoneBounds, 0.0, radial_end_z)
                ord_list = p.zoneOrder
                is_perm = (
                    len(ord_list) == len(zones)
                    and all(0 <= v < len(zones) for v in ord_list)
                    and len(set(ord_list)) == len(zones)
                )
                if is_perm:
                    zones = [zones[i] for i in ord_list]
                elif cur["z"] > radial_end_z / 2.0:
                    zones = list(reversed(zones))
                for zone in zones:
                    layer = R - p.doc
                    guard = 0
                    while layer > floor_r + 1e-6 and guard < 80:
                        guard += 1
                        for iv in cut_intervals(rough_run_samples, layer):
                            a_val = max(iv["a"], zone["a"])
                            b_val = min(iv["b"], zone["b"])
                            if b_val - a_val > 0.3:
                                cuts.append({"a": a_val, "b": b_val, "r": layer})
                        layer -= p.doc
            else:
                layer = R - p.doc
                guard = 0
                while layer > floor_r + 1e-6 and guard < 80:
                    guard += 1
                    for iv in cut_intervals(rough_run_samples, layer):
                        cuts.append({"a": iv["a"], "b": iv["b"], "r": layer})
                    layer -= p.doc

            end_cuts = [c["r"] for c in cuts if c["a"] <= radial_end_z + 1e-6 and c["b"] >= radial_end_z - 1e-6]
            if end_cuts:
                radial_rough_end_r = min(end_cuts)

            if p.roughMode == "classic":
                n_l = 0
                last_r = float("nan")
                for c in cuts:
                    if c["r"] != last_r:
                        n_l += 1
                        note(f"LAYER {n_l} - X{_f2(c['r'])}")
                        last_r = c["r"]
                    start_z = c["b"] if op.reverse else c["a"]
                    end_z = c["a"] if op.reverse else c["b"]
                    mv(0, retract_x, start_z, 0.0, "rapid")
                    mv(1, 2.0 * c["r"], start_z, p.feedRough * 0.7, "rough")
                    if c["b"] - c["a"] > 0.01:
                        mv(1, 2.0 * c["r"], end_z, p.feedRough, "rough")
                    mv(0, retract_x, end_z, 0.0, "rapid")
                continue

            cur_z = float("nan")
            cur_r = 0.0
            n_l = 0
            last_r = float("nan")
            for c in cuts:
                if c["r"] != last_r:
                    n_l += 1
                    note(f"LAYER {n_l} - X{_f2(c['r'])}")
                    last_r = c["r"]
                first_cut = math.isnan(cur_z)
                ref_z = cur["z"] if first_cut else cur_z
                near_a = abs(c["a"] - ref_z) <= abs(c["b"] - ref_z)
                start_z = (c["b"] if near_a else c["a"]) if (first_cut and op.reverse) else (c["a"] if near_a else c["b"])
                end_z = c["b"] if start_z == c["a"] else c["a"]
                ramp_ok = p.ramp and ramp_is_safe(cur_z, cur_r, start_z, c["r"])
                if math.isnan(cur_z):
                    mv(0, retract_x, start_z, 0.0, "rapid")
                elif not ramp_ok:
                    safe_r = min_safe_radius(cur_z, start_z)
                    travel_r = max(cur_r, safe_r)
                    if travel_r > cur_r + 1e-6:
                        raw_rapid(2.0 * travel_r, cur_z)
                    raw_rapid(2.0 * travel_r, start_z)
                mv(1, 2.0 * c["r"], start_z, p.feedRough * 0.7, "rough")
                if abs(end_z - start_z) > 0.01:
                    mv(1, 2.0 * c["r"], end_z, p.feedRough, "rough")
                phys_cut(c["a"], c["b"], c["r"])
                cur_z = end_z
                cur_r = c["r"]
            if not math.isnan(cur_z):
                mv(0, retract_x, cur_z, 0.0, "rapid")

        elif op.type == "rough-z":
            cur_op = "rough-z"
            if not has_outer:
                continue
            note("ROUGHING - AXIAL PEEL")
            step_z = max(0.5, p.doc)
            n_p = 0
            axial_positions: List[float] = []
            z_cur = z0
            while z_cur <= z_end + 1e-6:
                axial_positions.append(z_cur)
                z_cur += step_z
            if op.reverse:
                axial_positions.reverse()
            for z_val in axial_positions:
                target = offset_radius_at(z_val)
                if target < R - 0.02:
                    if n_p == 0:
                        note(f"AXIAL STEP {_f2(step_z)} MM")
                    n_p += 1
                    mv(0, retract_x, z_val, 0.0, "rapid")
                    mv(1, 2.0 * target, z_val, p.feedRough * 0.8, "roughz")
                    mv(0, retract_x, z_val, 0.0, "rapid")

        elif op.type == "copy":
            cur_op = "copy"
            if not has_outer:
                continue
            note("ROUGHING - CONTOUR PARALLELS")
            k_max = int(math.floor((R - floor_r - 1e-6) / p.doc))
            for k in range(k_max, 0, -1):
                d = od + k * p.doc
                ivs = cut_intervals(samples, R - d)
                if not ivs:
                    continue
                note(f"CONTOUR +{_f2(d)} MM")
                for iv in ivs:
                    span = [s for s in samples if iv["a"] - 1e-6 <= s.z <= iv["b"] + 1e-6]
                    if len(span) < 2:
                        continue
                    stride = max(1, len(span) // 42)
                    sampled = [s for idx, s in enumerate(span) if idx % stride == 0 or idx == len(span) - 1]
                    pts_run = list(reversed(sampled)) if op.reverse else sampled
                    mv(0, retract_x, pts_run[0].z, 0.0, "rapid")
                    mv(1, 2.0 * (pts_run[0].r + d), pts_run[0].z, p.feedRough * 0.7, "copy")
                    for pt in pts_run[1:]:
                        mv(1, 2.0 * (pt.r + d), pt.z, p.feedRough, "copy")
                    mv(0, retract_x, pts_run[-1].z, 0.0, "rapid")

        elif op.type == "inner-rough":
            cur_op = "inner-rough"
            if not has_inner:
                continue
            note(f"INNER ROUGH - BOWL HOLLOWING (HOLDER {op.holder})")
            wall_by_r = sorted([Sample(z=pt.z, r=max(0.0, pt.r)) for pt in inner_finish_off_samples], key=lambda a: a.r)
            merged_wall: List[Sample] = []
            for pt in wall_by_r:
                if merged_wall and abs(merged_wall[-1].r - pt.r) < 0.04:
                    if pt.z > merged_wall[-1].z:
                        merged_wall[-1].z = pt.z
                else:
                    merged_wall.append(pt.copy())
            if len(merged_wall) < 2:
                continue
            if merged_wall[0].r > 1e-9:
                merged_wall.insert(0, Sample(z=merged_wall[0].z, r=0.0))
            z_outer = max(pt.z for pt in merged_wall)
            z_inner = min(pt.z for pt in merged_wall)
            rough_offset_clearance = 0.05
            rough_inner_z = z_inner + rough_offset_clearance
            step = max(0.5, p.innerDoc)
            layers: List[float] = []
            first_layer = (
                bottom_covered_from_z - step
                if bottom_covered_from_z is not None
                else (z_outer - step if split_plane_already_cut else z_outer)
            )
            z_cur = first_layer
            while z_cur > rough_inner_z + 0.05:
                layers.append(z_cur)
                z_cur -= step
            if not layers or abs(layers[-1] - rough_inner_z) > 0.05:
                layers.append(rough_inner_z)
            if not split_plane_already_cut and abs(layers[0] - z_outer) < 0.05:
                split_plane_already_cut = True

            def intervals_at(layer_z: float) -> List[Dict[str, float]]:
                boundary = [{"r": max(0.0, q.r), "z": q.z + rough_offset_clearance} for q in inner_finish_off_samples]
                mouth_plane_z = bottom_covered_from_z if bottom_covered_from_z is not None else p.blankL
                polygon = boundary + [
                    {"r": boundary[-1]["r"], "z": mouth_plane_z},
                    {"r": boundary[0]["r"], "z": mouth_plane_z},
                ]
                hits: List[float] = []
                for idx in range(len(polygon)):
                    a_pt = polygon[idx]
                    b_pt = polygon[(idx + 1) % len(polygon)]
                    if not ((a_pt["z"] <= layer_z < b_pt["z"]) or (b_pt["z"] <= layer_z < a_pt["z"])):
                        continue
                    t = (layer_z - a_pt["z"]) / (b_pt["z"] - a_pt["z"])
                    hits.append(a_pt["r"] + (b_pt["r"] - a_pt["r"]) * t)
                hits.sort()
                ivs: List[Dict[str, float]] = []
                for idx in range(0, len(hits) - 1, 2):
                    a_val = max(0.0, hits[idx])
                    b_val = max(a_val, hits[idx + 1])
                    if b_val - a_val > 0.05:
                        ivs.append({"a": a_val, "b": b_val})
                return ivs

            note(f"INNER VERTICAL LAYERS {len(layers)} x {_f2(step)} MM")
            r_entry = 0.0
            mouth_x = z_outer + p.innerStartClearance
            if not bottom_to_inner_rough_ready and not bottom_to_inner_rough_direct:
                enter_first_inner(2.0 * r_entry, mouth_x)
            layer_plans = [{"layerZ": lz, "intervals": intervals_at(lz)} for lz in layers]

            prepared_for_next_layer = False
            for layer_index, plan in enumerate(layer_plans):
                layer_z = plan["layerZ"]
                layer_intervals = plan["intervals"]
                for interval_index, interval in enumerate(layer_intervals):
                    low_r = max(r_entry, interval["a"])
                    high_r = max(low_r, interval["b"])
                    start_r = high_r if op.reverse else low_r
                    end_r = low_r if op.reverse else high_r
                    cut_z = layer_z
                    next_interval = layer_intervals[interval_index + 1] if interval_index + 1 < len(layer_intervals) else None

                    if interval_index == 0:
                        if not prepared_for_next_layer and layer_index == 0:
                            if bottom_to_inner_rough_direct:
                                bottom_to_inner_rough_direct = False
                            elif bottom_to_inner_rough_ready:
                                raw_rapid(2.0 * start_r, cur["z"])
                                bottom_to_inner_rough_ready = False
                            else:
                                raw_rapid(2.0 * start_r, mouth_x)
                        prepared_for_next_layer = False

                    mv(1, 2.0 * start_r, cut_z, p.feedRough * 0.7, "bore")
                    if abs(end_r - start_r) > 0.05:
                        mv(1, 2.0 * end_r, cut_z, p.feedRough, "bore")

                    if next_interval is not None:
                        next_start_r = max(next_interval["a"], next_interval["b"]) if op.reverse else max(end_r, next_interval["a"])
                        peak_lo, peak_hi = min(end_r, next_start_r), max(end_r, next_start_r)
                        peak_points = [pt for pt in merged_wall if peak_lo - 1e-7 <= pt.r <= peak_hi + 1e-7]
                        peak_z = max((pt.z for pt in peak_points), default=layer_z)
                        safe_peak_z = max(cut_z + 0.5, peak_z + 0.5)
                        raw_rapid(2.0 * end_r, safe_peak_z)
                        raw_rapid(2.0 * next_start_r, safe_peak_z)
                    else:
                        next_layer_first = (
                            layer_plans[layer_index + 1]["intervals"][0]
                            if layer_index + 1 < len(layer_plans) and layer_plans[layer_index + 1]["intervals"]
                            else None
                        )
                        next_layer_start_r = max(r_entry, next_layer_first["a"]) if next_layer_first else 0.0
                        if next_layer_first and next_layer_start_r > 1e-7:
                            lo_r, hi_r = min(end_r, next_layer_start_r), max(end_r, next_layer_start_r)
                            blockers = [pt for pt in merged_wall if lo_r - 1e-7 <= pt.r <= hi_r + 1e-7]
                            blocking_z = max((pt.z for pt in blockers), default=layer_z)
                            safe_return_z = max(cut_z + 0.5, blocking_z + 0.5)
                            raw_rapid(2.0 * end_r, safe_return_z)
                            raw_rapid(2.0 * next_layer_start_r, safe_return_z)
                            prepared_for_next_layer = True
                        else:
                            blockers = [pt for pt in merged_wall if pt.r <= end_r + 1e-7]
                            blocking_z = max((pt.z for pt in blockers), default=layer_z)
                            safe_return_z = max(cut_z + 0.5, blocking_z + 0.5)
                            raw_rapid(2.0 * end_r, safe_return_z)
                            raw_rapid(0.0, safe_return_z)

            inner_cleared = True
            if not finish_last_inner(op.id):
                move_inner_to_axis_safely()
                if not next_is_inner_path(op.id):
                    raw_rapid(2.0 * r_entry, mouth_x)
                    mv(0, retract_x, mouth_x, 0.0, "rapid")

        elif op.type == "inner-offset":
            cur_op = "inner-offset"
            if not has_inner or iod <= 0.01:
                continue
            note(f"INNER OFFSET PASS {_f2(iod)} MM (HOLDER {op.holder})")
            inner_off_base = inner_finish_off_samples
            if len(inner_off_base) < 2:
                continue
            z_bot = inner_off_base[0].z
            z_rim_f = inner_off_base[-1].z
            inner_off = list(reversed(inner_off_base)) if op.reverse else inner_off_base
            start_inner_z = inner_off[0].z
            r_entry = 0.0
            mouth_x = z_rim_f + p.innerStartClearance
            if not inner_cleared or cur_holder != 2:
                enter_first_inner(2.0 * r_entry, mouth_x)
            if inner_cleared:
                move_inner_to_axis_safely()
                raw_rapid(0.0, start_inner_z)
                mv(1, 2.0 * inner_off[0].r, inner_off[0].z, p.feedRough * 0.6, "bore")
            else:
                mv(1, 2.0 * r_entry, start_inner_z, p.feedRough * 0.6, "bore")
                mv(1, 2.0 * inner_off[0].r, inner_off[0].z, p.feedRough * 0.6, "bore")
            mv(1, 2.0 * inner_off[0].r, inner_off[0].z, p.feedFinish, "boreoff")
            for pt in inner_off[1:]:
                mv(1, 2.0 * pt.r, pt.z, p.feedFinish, "boreoff")
            if not finish_last_inner(op.id):
                if inner_cleared:
                    move_inner_to_axis_safely()
                    if not next_is_inner_path(op.id):
                        raw_rapid(2.0 * r_entry, mouth_x)
                else:
                    for pt in reversed(inner_off[:-1]):
                        raw_rapid(2.0 * pt.r, pt.z)
                    raw_rapid(2.0 * r_entry, z_bot)
                    raw_rapid(2.0 * r_entry, mouth_x)
                if not next_is_inner_path(op.id):
                    mv(0, retract_x, mouth_x, 0.0, "rapid")

        elif op.type == "inner-finish":
            cur_op = "inner-finish"
            if not has_inner:
                continue
            note(f"INNER FINISH - BOWL WALL (HOLDER {op.holder})")
            iw_base = inner_finish_path
            z_bot = iw_base[0].z
            z_rim_f = iw_base[-1].z
            iw = list(reversed(iw_base)) if op.reverse else iw_base
            start_inner_z = iw[0].z
            r_entry = 0.0
            mouth_x = z_rim_f + p.innerStartClearance
            if not inner_cleared or cur_holder != 2:
                enter_first_inner(2.0 * r_entry, mouth_x)
            if inner_cleared:
                move_inner_to_axis_safely()
                raw_rapid(2.0 * r_entry, start_inner_z)
            else:
                mv(1, 2.0 * r_entry, start_inner_z, p.feedRough * 0.6, "borefin")
            for pt in iw:
                mv(1, 2.0 * pt.r, pt.z, p.feedFinish, "borefin")
            if not finish_last_inner(op.id):
                if inner_cleared:
                    raw_rapid(2.0 * r_entry, z_rim_f)
                    raw_rapid(2.0 * r_entry, mouth_x)
                else:
                    for pt in reversed(iw[:-1]):
                        mv(1, 2.0 * pt.r, pt.z, p.feedFinish, "borefin")
                    mv(1, 2.0 * r_entry, z_bot, p.feedFinish, "borefin")
                    mv(1, 2.0 * r_entry, mouth_x, p.feedRough * 0.6, "borefin")
                mv(0, retract_x, mouth_x, 0.0, "rapid")

        elif op.type == "finish":
            cur_op = "finish"
            if not has_outer:
                continue
            note("FINISHING - MAIN PROFILE")
            ap_x = (
                max(z_end - p.safety - (3.0 if p.spreadG0 else 0.0), z0)
                if op.reverse
                else min(z0 + p.safety + (3.0 if p.spreadG0 else 0.0), z_end)
            )
            ap_r = max(r0, radius_at(ap_x)) + od + p.safety
            mv(0, 2.0 * ap_r, ap_x, 0.0, "rapid")
            profile_path("finish", p.feedFinish, bool(op.reverse))

        elif op.type == "offset":
            cur_op = "offset"
            if not has_outer:
                continue
            if od > 0.01:
                note(f"OFFSET PASS +{_f2(od)} MM (PARALLEL TO PROFILE)")
                offset_path = list(reversed(off_samples)) if op.reverse else off_samples
                ap_x = max(z_end - p.safety, z0) if op.reverse else min(z0 + p.safety, z_end)
                ap_r = max(offset_path[0].r, offset_radius_at(ap_x)) + p.safety
                mv(0, 2.0 * ap_r, ap_x, 0.0, "rapid")
                mv(1, 2.0 * offset_path[0].r, offset_path[0].z, p.feedFinish, "offset")
                for pt in offset_path[1:]:
                    mv(1, 2.0 * pt.r, pt.z, p.feedFinish, "offset")
                mv(0, retract_x, z_end, 0.0, "rapid")

    cur_op = "sys"
    cur_op_id = -1
    if not ended_at_inner_endpoint:
        cur_holder = 1
        note("END OF PROGRAM")
        mv(0, retract_x, p.blankL + 2.0 * p.safety, 0.0, "rapid")
        mv(0, home["x"], home["z"], 0.0, "rapid")

    if p.spreadG0:
        groups: Dict[str, List[int]] = {}
        for idx, s in enumerate(segs):
            if s.motion != 0:
                continue
            a = machine_uv(s.z1, s.x1, s.holder, p)
            b = machine_uv(s.z2, s.x2, s.holder, p)
            if math.hypot(b["u"] - a["u"], b["v"] - a["v"]) < 1e-9:
                continue
            if abs(b["u"] - a["u"]) < 1e-9:
                continue
            if abs(b["v"] - a["v"]) >= 1e-9:
                continue
            if s.holder == 2 and a["v"] < retract_x - p.holder2.yOff - 1e-9:
                continue
            key = f"{b['v']:.2f}"
            groups.setdefault(key, []).append(idx)

        for arr in groups.values():
            if len(arr) < 2:
                if len(arr) == 1:
                    sg = segs[arr[0]]
                    pa = machine_uv(sg.z1, sg.x1, sg.holder, p)
                    funnel_v = 0.0 - (p.holder2.yOff if sg.holder == 2 else 0.0)
                    if abs(pa["v"] - funnel_v) >= 1.0:
                        sg.fan = 3.0
                continue
            for k, si in enumerate(arr):
                segs[si].fan = float(min((k + 1) * 3, 33))

    ctr: Dict[str, int] = {}
    for sg in segs:
        kk = "sys" if sg.opId < 0 else str(sg.opId)
        n_val = ctr.get(kk, 0)
        ctr[kk] = n_val + 1
        sg.ovrKey = f"{kk}:{n_val}"

    lines = build_modal_lines(segs, p) if p.format == "modal" else build_std_lines(segs, p)

    cut_len = 0.0
    rapid_len = 0.0
    time_sec = 0.0
    for s in segs:
        d = math.hypot(s.x2 - s.x1, s.z2 - s.z1)
        if s.motion == 1:
            cut_len += d
            time_sec += (d / max(1.0, s.feed)) * 60.0
        else:
            rapid_len += d
            time_sec += (d / RAPID_RATE) * 60.0

    vol = 0.0
    for i in range(1, len(samples)):
        dz = samples[i].z - samples[i - 1].z
        r_avg = (samples[i].r + samples[i - 1].r) / 2.0
        vol += math.pi * (R * R - r_avg * r_avg) * dz

    env_vol = rotational_envelope(p.blankD, p.blankShape)
    if env_vol["hasCorners"] and env_vol["outR"] > R:
        vol += math.pi * (env_vol["outR"] * env_vol["outR"] - R * R) * p.blankL

    if len(inner_samples) > 1:
        for i in range(1, len(inner_samples)):
            dz = abs(inner_samples[i].z - inner_samples[i - 1].z)
            r_avg = (inner_samples[i].r + inner_samples[i - 1].r) / 2.0
            vol += math.pi * r_avg * r_avg * dz

    rough_layers = sum(
        1
        for o in p.ops
        if o.on and o.type in ("rough-d", "rough-z", "offset", "inner-rough", "inner-offset")
    )

    return GenResult(
        lines=lines,
        segs=segs,
        samples=samples,
        innerSamples=inner_samples,
        cutLen=cut_len,
        rapidLen=rapid_len,
        timeSec=time_sec,
        volumeCm3=vol / 1000.0,
        roughLayers=rough_layers,
        format=p.format,
    )


PRESETS: List[Dict[str, Any]] = [
    {
        "id": "leg",
        "name": "پایه مبل",
        "blankD": 60,
        "blankL": 200,
        "shape": "square",
        "pts": [
            [0, 22, False], [10, 22, False], [16, 29, True], [30, 29, True],
            [42, 17, True], [54, 17, True], [62, 27, True], [76, 27, True],
            [86, 13, True], [98, 13, True], [106, 24, True], [122, 24, True],
            [132, 15, True], [146, 15, True], [154, 27, True], [172, 27, True],
            [180, 19, True], [192, 19, True], [200, 22, False],
        ],
    },
    {
        "id": "vase",
        "name": "گلدان",
        "blankD": 64,
        "blankL": 200,
        "shape": "square",
        "pts": [
            [0, 9, True], [8, 14, True], [20, 24, True], [36, 30, True],
            [54, 27, True], [76, 15, True], [96, 10, True], [114, 11, True],
            [132, 19, True], [150, 26, True], [164, 24, True], [176, 15, True],
            [186, 9, True], [194, 7, True], [200, 8, False],
        ],
    },
    {
        "id": "bowl",
        "name": "پیاله",
        "blankD": 150,
        "blankL": 90,
        "shape": "square",
        "pts": [
            [0, 10, True], [12, 22, True], [30, 42, True], [52, 58, True],
            [70, 67, True], [82, 71, True], [90, 72, False],
        ],
    },
    {
        "id": "bowl-both",
        "name": "کاسه (داخل+خارج)",
        "blankD": 150,
        "blankL": 90,
        "shape": "square",
        "strategy": "bowl",
        "split": {"z": 90, "r": 68},
        "pts": [
            [0, 16, False], [8, 19, True], [18, 27, True], [32, 41, True], [48, 54, True],
            [62, 63, True], [74, 69, True], [84, 71.5, True], [90, 72, False],
        ],
        "wall": [
            [0, 16, False], [8, 19, True], [18, 27, True], [32, 41, True], [48, 54, True],
            [62, 63, True], [74, 69, True], [84, 71.5, True], [90, 72, False],
            [90, 64, False],
            [82, 61, True], [70, 55, True], [56, 45, True], [42, 32, True],
            [32, 20, True], [26, 10, True], [24, 4, False],
        ],
    },
    {
        "id": "inner-arc",
        "name": "قوس داخلی",
        "blankD": 150,
        "blankL": 90,
        "shape": "square",
        "strategy": "bowl",
        "split": {"z": 79.9758998319284, "r": 50.0316974402297},
        "pts": [[0, 0, False], [20, 22, True], [42, 43, True], [64, 52, True], [80, 50, False]],
        "sketch": [
            {"kind": "cubic", "a": {"z": 0, "r": 0}, "b": {"z": 80, "r": 50}, "c1": {"z": -0.001953125, "r": 56}, "c2": {"z": 42, "r": 100}},
            {"kind": "cubic", "a": {"z": 13, "r": 1}, "b": {"z": 77, "r": 48}, "c1": {"z": 15, "r": 62}, "c2": {"z": 51, "r": 75}},
            {"kind": "arc", "a": {"z": 77, "r": 48}, "b": {"z": 80, "r": 50}, "via": {"z": 80, "r": 48}},
        ],
    },
    {
        "id": "inner-rough-test",
        "name": "تست خشن داخل عمودی",
        "blankD": 1000,
        "blankL": 100,
        "shape": "circle",
        "strategy": "bowl",
        "split": {"z": 66, "r": 420},
        "pts": [[0, 365, False], [8, 420, True], [22, 462, True], [40, 475, True], [56, 460, True], [66, 420, False]],
        "wall": [
            [0, 365, False], [8, 420, True], [22, 462, True], [40, 475, True], [56, 460, True], [66, 420, False],
            [60, 365, False], [34, 315, False], [54, 245, False], [30, 190, False], [54, 125, False], [30, 65, False], [54, 2, False],
        ],
    },
    {
        "id": "baluster",
        "name": "ستون نرده",
        "blankD": 70,
        "blankL": 240,
        "shape": "square",
        "pts": [
            [0, 18, False], [8, 24, True], [18, 24, True], [26, 32, True],
            [40, 32, True], [50, 20, True], [62, 14, True], [76, 14, True],
            [86, 26, True], [100, 33, True], [116, 33, True], [126, 22, True],
            [138, 15, True], [152, 15, True], [162, 28, True], [178, 34, True],
            [194, 34, True], [204, 21, True], [216, 15, True], [228, 15, True],
            [234, 20, True], [240, 18, False],
        ],
    },
    {
        "id": "bead",
        "name": "مهره تسبیح",
        "blankD": 40,
        "blankL": 60,
        "shape": "square",
        "pts": [
            [0, 5, True], [8, 11, True], [18, 17, True], [30, 19, True],
            [42, 17, True], [52, 11, True], [60, 5, True],
        ],
    },
    {
        "id": "cyl",
        "name": "استوانه خام",
        "blankD": 60,
        "blankL": 180,
        "shape": "square",
        "pts": [[0, 30, False], [180, 30, False]],
    },
    {
        "id": "empty-100",
        "name": "طرح خالی ۱۰×۱۰",
        "blankD": 100,
        "blankL": 100,
        "shape": "square",
        "empty": True,
        "pts": [],
    },
]


def preset_points(preset: Dict[str, Any]) -> List[PPoint]:
    return [PPoint(id=next_id(), z=float(z), r=float(r), smooth=bool(smooth)) for z, r, smooth in preset.get("pts", [])]


def fmt_time(sec: float) -> str:
    m = int(math.floor(sec / 60.0))
    s = int(round(sec % 60.0))
    if m >= 60:
        return f"{m // 60}س {m % 60}د"
    return f"{m}د و {s}ث" if m > 0 else f"{s} ثانیه"


def apply_gcode_ovr(base: GenResult, ovr: Dict[str, Any], p: Params) -> GenResult:
    if not ovr:
        return base
    expanded: List[Seg] = []
    for sg0 in base.segs:
        o = ovr.get(sg0.ovrKey) if sg0.ovrKey else None
        if o and o.get("del"):
            continue
        s_pt = o.get("s") if o and o.get("s") else {"z": sg0.z1, "x": sg0.x1}
        e_pt = o.get("e") if o and o.get("e") else {"z": sg0.z2, "x": sg0.x2}
        via_pts = o.get("via", []) if o else []
        points = [s_pt] + list(via_pts) + [e_pt]
        moves = o.get("moves", []) if o else []
        for i in range(1, len(points)):
            a, b = points[i - 1], points[i]
            if math.hypot(float(b["z"]) - float(a["z"]), float(b["x"]) - float(a["x"])) < 1e-6:
                continue
            move = moves[i - 1] if i - 1 < len(moves) else None
            motion: Literal[0, 1] = int(move["motion"]) if move and "motion" in move else sg0.motion  # type: ignore
            feed = RAPID_RATE if motion == 0 else (float(move["feed"]) if move and "feed" in move else sg0.feed)
            cp = sg0.copy()
            cp.motion = motion
            cp.feed = feed
            cp.feedOvr = bool(move)
            cp.bridgeMoves = o.get("bridgeMoves") if (o and i == 1) else None
            cp.z1 = float(a["z"])
            cp.x1 = float(a["x"])
            cp.z2 = float(b["z"])
            cp.x2 = float(b["x"])
            cp.note = sg0.note if i == 1 else None
            expanded.append(cp)

    kept: List[Seg] = []
    for sg0 in expanded:
        sg = sg0.copy()
        prev = kept[-1] if kept else None
        if prev is not None and sg.motion == 1 and (abs(sg.z1 - prev.z2) > 1e-6 or abs(sg.x1 - prev.x2) > 1e-6):
            if prev.motion == 0:
                prev.z2 = sg.z1
                prev.x2 = sg.x1
                if math.hypot(prev.z2 - prev.z1, prev.x2 - prev.x1) < 1e-6:
                    kept.pop()
            else:
                kept.append(
                    Seg(
                        motion=0,
                        feed=RAPID_RATE,
                        kind="rapid",
                        opId=-1,
                        op="sys",
                        z1=prev.z2,
                        x1=prev.x2,
                        z2=sg.z1,
                        x2=sg.x1,
                        line=-1,
                        holder=sg.holder,
                    )
                )
        kept.append(sg)

    lines = build_modal_lines(kept, p) if p.format == "modal" else build_std_lines(kept, p)
    cut_len = 0.0
    rapid_len = 0.0
    time_sec = 0.0
    for sg in kept:
        d = math.hypot(sg.x2 - sg.x1, sg.z2 - sg.z1)
        if sg.motion == 1:
            cut_len += d
            time_sec += (d / max(1.0, sg.feed)) * 60.0
        else:
            rapid_len += d
            time_sec += (d / RAPID_RATE) * 60.0

    return GenResult(
        lines=lines,
        segs=kept,
        samples=base.samples,
        innerSamples=base.innerSamples,
        cutLen=cut_len,
        rapidLen=rapid_len,
        timeSec=time_sec,
        volumeCm3=base.volumeCm3,
        roughLayers=base.roughLayers,
        format=base.format,
    )
