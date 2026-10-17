"""
موتور اسکچ — خط، منحنی درجه۲/۳ و کمان سه‌نقطه‌ای برای طراحی پروفایل
مختصات: z = طول قطعه (محور X نمایش) ، r = شعاع (محور Y نمایش)
بازنویسی کامل پایتون متناظر با src/lib/sketch.ts
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple, Any

SketchKind = Literal["line", "quad", "cubic", "arc"]
SnapType = Literal["end", "mid", "center", "ctrl", "cross", "axis", "grid"]

KIND_FA: Dict[str, str] = {
    "line": "خط",
    "quad": "منحنی ساده",
    "cubic": "منحنی کنترلی",
    "arc": "کمان",
}

SNAP_FA: Dict[str, str] = {
    "end": "نقطهٔ انتها",
    "mid": "وسط",
    "center": "مرکز کمان",
    "ctrl": "نقطهٔ کنترل",
    "cross": "تقاطع",
    "axis": "محور",
    "grid": "شبکه",
}

_seg_uid = 5000
_pp_uid = 90000
_branch_uid = 95000


def new_seg_id() -> int:
    global _seg_uid
    _seg_uid += 1
    return _seg_uid


def _next_pp_id() -> int:
    global _pp_uid
    _pp_uid += 1
    return _pp_uid


def _next_branch_id() -> int:
    global _branch_uid
    _branch_uid += 1
    return _branch_uid


@dataclass
class SPoint:
    z: float
    r: float

    def to_dict(self) -> Dict[str, float]:
        return {"z": float(self.z), "r": float(self.r)}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SPoint":
        return SPoint(z=float(d["z"]), r=float(d["r"]))

    def copy(self) -> "SPoint":
        return SPoint(z=self.z, r=self.r)


@dataclass
class SketchSeg:
    id: int
    kind: SketchKind
    a: SPoint
    b: SPoint
    c1: Optional[SPoint] = None
    c2: Optional[SPoint] = None
    via: Optional[SPoint] = None
    polylineId: Optional[int] = None
    filletOf: Optional[Tuple[int, int]] = None
    arcDivisions: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "a": self.a.to_dict(),
            "b": self.b.to_dict(),
        }
        if self.c1 is not None:
            out["c1"] = self.c1.to_dict()
        if self.c2 is not None:
            out["c2"] = self.c2.to_dict()
        if self.via is not None:
            out["via"] = self.via.to_dict()
        if self.polylineId is not None:
            out["polylineId"] = self.polylineId
        if self.filletOf is not None:
            out["filletOf"] = [self.filletOf[0], self.filletOf[1]]
        if self.arcDivisions is not None:
            out["arcDivisions"] = self.arcDivisions
        return out

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SketchSeg":
        fillet = d.get("filletOf")
        return SketchSeg(
            id=int(d.get("id") or new_seg_id()),
            kind=d["kind"],
            a=SPoint.from_dict(d["a"]),
            b=SPoint.from_dict(d["b"]),
            c1=SPoint.from_dict(d["c1"]) if d.get("c1") else None,
            c2=SPoint.from_dict(d["c2"]) if d.get("c2") else None,
            via=SPoint.from_dict(d["via"]) if d.get("via") else None,
            polylineId=int(d["polylineId"]) if d.get("polylineId") is not None else None,
            filletOf=(int(fillet[0]), int(fillet[1])) if isinstance(fillet, (list, tuple)) and len(fillet) == 2 else None,
            arcDivisions=int(d["arcDivisions"]) if d.get("arcDivisions") is not None else None,
        )


@dataclass
class ArcInfo:
    center: SPoint
    radius: float
    a0: float
    sweep: float


@dataclass
class SegBounds:
    minZ: float
    maxZ: float
    minR: float
    maxR: float


@dataclass
class SnapPoint:
    p: SPoint
    type: SnapType
    segId: Optional[int] = None


@dataclass
class ChainItem:
    seg: SketchSeg
    reversed: bool


@dataclass
class SplitResult:
    outer: List[SPoint]
    inner: List[SPoint]
    splitIndex: int
    splitAt: SPoint
    outerDir: Literal[1, -1]
    innerDir: Literal[1, -1]


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def dist(p: SPoint, q: SPoint) -> float:
    return math.hypot(p.z - q.z, p.r - q.r)


def arc_info(s: SketchSeg) -> Optional[ArcInfo]:
    a, b, via = s.a, s.b, s.via
    if via is None:
        return None
    d = 2.0 * (a.z * (via.r - b.r) + via.z * (b.r - a.r) + b.z * (a.r - via.r))
    if abs(d) < 1e-9:
        return None
    aa = a.z * a.z + a.r * a.r
    mm = via.z * via.z + via.r * via.r
    bb = b.z * b.z + b.r * b.r
    cz = (aa * (via.r - b.r) + mm * (b.r - a.r) + bb * (a.r - via.r)) / d
    cr = (aa * (b.z - via.z) + mm * (a.z - b.z) + bb * (via.z - a.z)) / d
    center = SPoint(z=cz, r=cr)
    radius = math.hypot(a.z - cz, a.r - cr)
    if not math.isfinite(radius) or radius > 1e6:
        return None
    tau = math.pi * 2.0
    norm = lambda x: ((x % tau) + tau) % tau
    a0 = math.atan2(a.r - cr, a.z - cz)
    a1 = math.atan2(b.r - cr, b.z - cz)
    am = math.atan2(via.r - cr, via.z - cz)
    d_ccw = norm(a1 - a0)
    m_ccw = norm(am - a0)
    ccw = m_ccw <= d_ccw
    sweep = d_ccw if ccw else -(tau - d_ccw)
    return ArcInfo(center=center, radius=radius, a0=a0, sweep=sweep)


def eval_seg(s: SketchSeg, t: float) -> SPoint:
    a, b = s.a, s.b
    if s.kind == "line":
        return SPoint(z=lerp(a.z, b.z, t), r=lerp(a.r, b.r, t))
    if s.kind == "quad" and s.c1 is not None:
        u = 1.0 - t
        return SPoint(
            z=u * u * a.z + 2.0 * u * t * s.c1.z + t * t * b.z,
            r=u * u * a.r + 2.0 * u * t * s.c1.r + t * t * b.r,
        )
    if s.kind == "cubic" and s.c1 is not None and s.c2 is not None:
        u = 1.0 - t
        w0 = u * u * u
        w1 = 3.0 * u * u * t
        w2 = 3.0 * u * t * t
        w3 = t * t * t
        return SPoint(
            z=w0 * a.z + w1 * s.c1.z + w2 * s.c2.z + w3 * b.z,
            r=w0 * a.r + w1 * s.c1.r + w2 * s.c2.r + w3 * b.r,
        )
    if s.kind == "arc":
        info = arc_info(s)
        if info is None:
            return SPoint(z=lerp(a.z, b.z, t), r=lerp(a.r, b.r, t))
        ang = info.a0 + info.sweep * t
        return SPoint(
            z=info.center.z + info.radius * math.cos(ang),
            r=info.center.r + info.radius * math.sin(ang),
        )
    return SPoint(z=lerp(a.z, b.z, t), r=lerp(a.r, b.r, t))


def seg_length(s: SketchSeg) -> float:
    if s.kind == "line":
        return dist(s.a, s.b)
    if s.kind == "arc":
        info = arc_info(s)
        if info is not None:
            return abs(info.sweep) * info.radius
    length = 0.0
    prev = eval_seg(s, 0.0)
    for i in range(1, 25):
        p = eval_seg(s, i / 24.0)
        length += dist(prev, p)
        prev = p
    return length


def seg_points(s: SketchSeg, n: Optional[int] = None) -> List[SPoint]:
    if s.kind == "line":
        return [s.a.copy(), s.b.copy()]
    configured: Optional[int] = None
    if s.kind == "arc" and s.arcDivisions is not None and math.isfinite(s.arcDivisions):
        configured = max(2, min(500, int(round(s.arcDivisions))))
    steps = n if n is not None else (configured if configured is not None else max(10, min(90, int(math.ceil(seg_length(s) / 1.2)))))
    return [eval_seg(s, i / steps) for i in range(steps + 1)]


def seg_mid(s: SketchSeg) -> SPoint:
    return eval_seg(s, 0.5)


def seg_bounds(s: SketchSeg) -> SegBounds:
    pts: List[SPoint] = [s.a.copy(), s.b.copy()]

    def add_at(t: float) -> None:
        if math.isfinite(t) and 1e-10 < t < 1.0 - 1e-10:
            pts.append(eval_seg(s, t))

    if s.kind == "quad" and s.c1 is not None:
        add_at(0.5)

        def add_quad_root(p0: float, p1: float, p2: float) -> None:
            den = p0 - 2.0 * p1 + p2
            if abs(den) > 1e-12:
                add_at((p0 - p1) / den)

        add_quad_root(s.a.z, s.c1.z, s.b.z)
        add_quad_root(s.a.r, s.c1.r, s.b.r)
    elif s.kind == "cubic" and s.c1 is not None and s.c2 is not None:
        add_at(0.25)
        add_at(0.5)
        add_at(0.75)

        def add_cubic_roots(p0: float, p1: float, p2: float, p3: float) -> None:
            A = -p0 + 3.0 * p1 - 3.0 * p2 + p3
            B = 2.0 * (p0 - 2.0 * p1 + p2)
            C = p1 - p0
            if abs(A) < 1e-12:
                if abs(B) > 1e-12:
                    add_at(-C / B)
                return
            disc = B * B - 4.0 * A * C
            if disc < -1e-12:
                return
            root = math.sqrt(max(0.0, disc))
            add_at((-B - root) / (2.0 * A))
            add_at((-B + root) / (2.0 * A))

        add_cubic_roots(s.a.z, s.c1.z, s.c2.z, s.b.z)
        add_cubic_roots(s.a.r, s.c1.r, s.c2.r, s.b.r)
    elif s.kind == "arc":
        info = arc_info(s)
        if info is not None:
            tau = math.pi * 2.0
            norm = lambda x: ((x % tau) + tau) % tau

            def on_sweep(angle: float) -> bool:
                if info.sweep >= 0:
                    return norm(angle - info.a0) <= info.sweep + 1e-10
                return norm(info.a0 - angle) <= -info.sweep + 1e-10

            for angle in (0.0, math.pi / 2.0, math.pi, 3.0 * math.pi / 2.0):
                if on_sweep(angle):
                    pts.append(
                        SPoint(
                            z=info.center.z + info.radius * math.cos(angle),
                            r=info.center.r + info.radius * math.sin(angle),
                        )
                    )

    return SegBounds(
        minZ=min(p.z for p in pts),
        maxZ=max(p.z for p in pts),
        minR=min(p.r for p in pts),
        maxR=max(p.r for p in pts),
    )


def make_seg(kind: SketchKind, pts: List[SPoint]) -> Optional[SketchSeg]:
    sid = new_seg_id()
    if kind == "line" and len(pts) >= 2:
        return SketchSeg(id=sid, kind="line", a=pts[0].copy(), b=pts[1].copy())
    if kind == "quad" and len(pts) >= 3:
        return SketchSeg(id=sid, kind="quad", a=pts[0].copy(), b=pts[1].copy(), c1=pts[2].copy())
    if kind == "cubic" and len(pts) >= 4:
        return SketchSeg(id=sid, kind="cubic", a=pts[0].copy(), b=pts[1].copy(), c1=pts[2].copy(), c2=pts[3].copy())
    if kind == "arc" and len(pts) >= 3:
        return SketchSeg(id=sid, kind="arc", a=pts[0].copy(), b=pts[1].copy(), via=pts[2].copy())
    return None


def default_cubic_handles(a: SPoint, b: SPoint) -> Tuple[SPoint, SPoint]:
    return (
        SPoint(z=lerp(a.z, b.z, 1.0 / 3.0), r=lerp(a.r, b.r, 1.0 / 3.0)),
        SPoint(z=lerp(a.z, b.z, 2.0 / 3.0), r=lerp(a.r, b.r, 2.0 / 3.0)),
    )


def line_angle(a: SPoint, b: SPoint) -> float:
    return math.atan2(b.r - a.r, b.z - a.z) * 180.0 / math.pi


def end_from_len_angle(a: SPoint, length: float, ang_deg: float) -> SPoint:
    rad = ang_deg * math.pi / 180.0
    return SPoint(z=a.z + length * math.cos(rad), r=a.r + length * math.sin(rad))


def arc_with_radius(s: SketchSeg, radius: float) -> SketchSeg:
    a, b = s.a, s.b
    mz = (a.z + b.z) / 2.0
    mr = (a.r + b.r) / 2.0
    half = dist(a, b) / 2.0
    if half < 1e-6:
        return s
    R = max(radius, half + 1e-4)
    dz = (b.z - a.z) / (2.0 * half)
    dr = (b.r - a.r) / (2.0 * half)
    nz = -dr
    nr = dz
    info = arc_info(s)
    side = 1.0
    if info is not None and s.via is not None:
        cur = (s.via.z - mz) * nz + (s.via.r - mr) * nr
        side = 1.0 if cur >= 0 else -1.0
    sag = R - math.sqrt(max(0.0, R * R - half * half))
    return SketchSeg(
        id=s.id,
        kind=s.kind,
        a=s.a.copy(),
        b=s.b.copy(),
        c1=s.c1.copy() if s.c1 else None,
        c2=s.c2.copy() if s.c2 else None,
        via=SPoint(z=mz + nz * sag * side, r=mr + nr * sag * side),
        polylineId=s.polylineId,
        filletOf=s.filletOf,
        arcDivisions=s.arcDivisions,
    )


def arc_radius(s: SketchSeg) -> float:
    info = arc_info(s)
    return info.radius if info is not None else 0.0


def _move_pt(p: SPoint, dz: float, dr: float) -> SPoint:
    return SPoint(z=p.z + dz, r=p.r + dr)


def move_seg(s: SketchSeg, dz: float, dr: float) -> SketchSeg:
    return SketchSeg(
        id=s.id,
        kind=s.kind,
        a=_move_pt(s.a, dz, dr),
        b=_move_pt(s.b, dz, dr),
        c1=_move_pt(s.c1, dz, dr) if s.c1 else None,
        c2=_move_pt(s.c2, dz, dr) if s.c2 else None,
        via=_move_pt(s.via, dz, dr) if s.via else None,
        polylineId=s.polylineId,
        filletOf=(s.filletOf[0], s.filletOf[1]) if s.filletOf else None,
        arcDivisions=s.arcDivisions,
    )


def clone_seg(s: SketchSeg, dz: float = 0.0, dr: float = 0.0) -> SketchSeg:
    moved = move_seg(s, dz, dr)
    moved.id = new_seg_id()
    return moved


def snap_candidates(segs: List[SketchSeg]) -> List[SnapPoint]:
    out: List[SnapPoint] = []
    for s in segs:
        out.append(SnapPoint(p=s.a, type="end", segId=s.id))
        out.append(SnapPoint(p=s.b, type="end", segId=s.id))
        out.append(SnapPoint(p=seg_mid(s), type="mid", segId=s.id))
        if s.c1 is not None:
            out.append(SnapPoint(p=s.c1, type="ctrl", segId=s.id))
        if s.c2 is not None:
            out.append(SnapPoint(p=s.c2, type="ctrl", segId=s.id))
        if s.kind == "arc":
            info = arc_info(s)
            if info is not None:
                out.append(SnapPoint(p=info.center, type="center", segId=s.id))
            if s.via is not None:
                out.append(SnapPoint(p=s.via, type="ctrl", segId=s.id))
    return out


def _seg_intersect(p1: SPoint, p2: SPoint, p3: SPoint, p4: SPoint) -> Optional[SPoint]:
    d = (p2.z - p1.z) * (p4.r - p3.r) - (p2.r - p1.r) * (p4.z - p3.z)
    if abs(d) < 1e-12:
        return None
    t = ((p3.z - p1.z) * (p4.r - p3.r) - (p3.r - p1.r) * (p4.z - p3.z)) / d
    u = ((p3.z - p1.z) * (p2.r - p1.r) - (p3.r - p1.r) * (p2.z - p1.z)) / d
    if t < 0.0 or t > 1.0 or u < 0.0 or u > 1.0:
        return None
    return SPoint(z=p1.z + t * (p2.z - p1.z), r=p1.r + t * (p2.r - p1.r))


def intersection_points(segs: List[SketchSeg]) -> List[SnapPoint]:
    polys = [seg_points(s, 1 if s.kind == "line" else 26) for s in segs]
    out: List[SnapPoint] = []
    for i in range(len(polys)):
        if len(out) >= 60:
            break
        for j in range(i + 1, len(polys)):
            if len(out) >= 60:
                break
            A, B = polys[i], polys[j]
            for x in range(len(A) - 1):
                for y in range(len(B) - 1):
                    hit = _seg_intersect(A[x], A[x + 1], B[y], B[y + 1])
                    if hit is not None and not any(dist(o.p, hit) < 0.4 for o in out):
                        out.append(SnapPoint(p=hit, type="cross"))
    return out


def dist_to_seg(s: SketchSeg, p: SPoint) -> float:
    pts = seg_points(s, 1 if s.kind == "line" else 40)
    best = float("inf")
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        dz = b.z - a.z
        dr = b.r - a.r
        l2 = dz * dz + dr * dr
        t = ((p.z - a.z) * dz + (p.r - a.r) * dr) / l2 if l2 > 1e-12 else 0.0
        t = max(0.0, min(1.0, t))
        d = math.hypot(p.z - (a.z + t * dz), p.r - (a.r + t * dr))
        if d < best:
            best = d
    return best


def flatten_sketch(segs: List[SketchSeg], blank_r: float, blank_l: float) -> List[Dict[str, Any]]:
    raw: List[SPoint] = []
    for s in segs:
        pts = [s.a, s.b] if s.kind == "line" else seg_points(s)
        for p in pts:
            if not math.isfinite(p.z) or not math.isfinite(p.r):
                continue
            raw.append(
                SPoint(
                    z=min(blank_l, max(0.0, p.z)),
                    r=min(blank_r, max(0.0, p.r)),
                )
            )
    if len(raw) < 2:
        return []
    raw.sort(key=lambda x: x.z)
    merged: List[SPoint] = []
    for p in raw:
        if merged and abs(merged[-1].z - p.z) < 0.06:
            if p.r > merged[-1].r:
                merged[-1].r = p.r
        else:
            merged.append(p.copy())
    if len(merged) < 2:
        return []
    return [{"id": _next_pp_id(), "z": p.z, "r": p.r, "smooth": False} for p in merged]


def sketch_from_points(pts: List[Dict[str, Any]]) -> List[SketchSeg]:
    p = sorted(pts, key=lambda x: float(x["z"]))
    out: List[SketchSeg] = []
    for i in range(len(p) - 1):
        p0 = p[max(0, i - 1)]
        p1 = p[i]
        p2 = p[i + 1]
        p3 = p[min(len(p) - 1, i + 2)]
        if bool(p1.get("smooth")) and bool(p2.get("smooth")):
            out.append(
                SketchSeg(
                    id=new_seg_id(),
                    kind="cubic",
                    a=SPoint(z=float(p1["z"]), r=float(p1["r"])),
                    b=SPoint(z=float(p2["z"]), r=float(p2["r"])),
                    c1=SPoint(
                        z=float(p1["z"]) + (float(p2["z"]) - float(p0["z"])) / 6.0,
                        r=float(p1["r"]) + (float(p2["r"]) - float(p0["r"])) / 6.0,
                    ),
                    c2=SPoint(
                        z=float(p2["z"]) - (float(p3["z"]) - float(p1["z"])) / 6.0,
                        r=float(p2["r"]) - (float(p3["r"]) - float(p1["r"])) / 6.0,
                    ),
                )
            )
        else:
            out.append(
                SketchSeg(
                    id=new_seg_id(),
                    kind="line",
                    a=SPoint(z=float(p1["z"]), r=float(p1["r"])),
                    b=SPoint(z=float(p2["z"]), r=float(p2["r"])),
                )
            )
    return out


def _end_key(p: SPoint) -> str:
    return f"{int(round(p.z * 1000))},{int(round(p.r * 1000))}"


def order_chain(segs: List[SketchSeg]) -> List[ChainItem]:
    if not segs:
        return []
    if len(segs) == 1:
        return [ChainItem(seg=segs[0], reversed=False)]
    unused: Dict[int, SketchSeg] = {s.id: s for s in segs}
    out: List[ChainItem] = []

    def chain_end(it: ChainItem) -> SPoint:
        return it.seg.a if it.reversed else it.seg.b

    count: Dict[str, int] = {}
    for s in segs:
        for k in (_end_key(s.a), _end_key(s.b)):
            count[k] = count.get(k, 0) + 1

    while unused:
        first: Optional[SketchSeg] = None
        for s in unused.values():
            if count.get(_end_key(s.a), 0) <= 1 or count.get(_end_key(s.b), 0) <= 1:
                first = s
                break
        if first is None:
            first = next(iter(unused.values()))
        del unused[first.id]
        a_free = count.get(_end_key(first.a), 0) <= 1
        b_free = count.get(_end_key(first.b), 0) <= 1
        chain: List[ChainItem] = [ChainItem(seg=first, reversed=(not a_free and b_free))]
        while True:
            tip = _end_key(chain_end(chain[-1]))
            nxt: Optional[SketchSeg] = None
            rev = False
            for s in unused.values():
                if _end_key(s.a) == tip:
                    nxt = s
                    rev = False
                    break
                if _end_key(s.b) == tip:
                    nxt = s
                    rev = True
                    break
            if nxt is None:
                break
            del unused[nxt.id]
            chain.append(ChainItem(seg=nxt, reversed=rev))
            if len(chain) > len(segs) + 2:
                break
        out.extend(chain)
    return out


def chain_polyline(chain: List[ChainItem]) -> List[SPoint]:
    out: List[SPoint] = []
    for it in chain:
        pts = [it.seg.a, it.seg.b] if it.seg.kind == "line" else seg_points(it.seg)
        arr = list(reversed(pts)) if it.reversed else pts
        for p in arr:
            if not out or dist(out[-1], p) > 1e-6:
                out.append(SPoint(z=p.z, r=p.r))
    return out


def split_chain_at(poly: List[SPoint], split: SPoint) -> SplitResult:
    bi = 0
    bd = float("inf")
    proj = poly[0].copy() if poly else SPoint(z=0.0, r=0.0)
    for i in range(len(poly) - 1):
        a, b = poly[i], poly[i + 1]
        dz = b.z - a.z
        dr = b.r - a.r
        l2 = dz * dz + dr * dr
        t = ((split.z - a.z) * dz + (split.r - a.r) * dr) / l2 if l2 > 1e-12 else 0.0
        t = max(0.0, min(1.0, t))
        px = a.z + t * dz
        pr = a.r + t * dr
        d = math.hypot(split.z - px, split.r - pr)
        if d < bd:
            bd = d
            bi = i
            proj = SPoint(z=px, r=pr)
    outer = [p.copy() for p in poly[: bi + 1]] + [proj.copy()]
    inner = [proj.copy()] + [p.copy() for p in poly[bi + 1 :]]

    def direction(arr: List[SPoint]) -> Literal[1, -1]:
        return 1 if len(arr) < 2 or arr[-1].z >= arr[0].z else -1

    return SplitResult(
        outer=outer,
        inner=inner,
        splitIndex=bi,
        splitAt=proj,
        outerDir=direction(outer),
        innerDir=direction(inner),
    )


def auto_split_point(poly: List[SPoint]) -> Optional[SPoint]:
    if len(poly) < 3:
        return None
    max_z = max(p.z for p in poly)
    cands = [p for p in poly if abs(p.z - max_z) < 0.6]
    if not cands:
        return None
    avg_r = sum(p.r for p in cands) / len(cands)
    return SPoint(z=round(max_z * 10.0) / 10.0, r=round(avg_r * 10.0) / 10.0)


def sketch_from_wall(wall: List[Dict[str, Any]]) -> List[SketchSeg]:
    p = wall
    out: List[SketchSeg] = []
    for i in range(len(p) - 1):
        p0 = p[max(0, i - 1)]
        p1 = p[i]
        p2 = p[i + 1]
        p3 = p[min(len(p) - 1, i + 2)]
        if bool(p1.get("smooth")) and bool(p2.get("smooth")):
            out.append(
                SketchSeg(
                    id=new_seg_id(),
                    kind="cubic",
                    a=SPoint(z=float(p1["z"]), r=float(p1["r"])),
                    b=SPoint(z=float(p2["z"]), r=float(p2["r"])),
                    c1=SPoint(
                        z=float(p1["z"]) + (float(p2["z"]) - float(p0["z"])) / 6.0,
                        r=float(p1["r"]) + (float(p2["r"]) - float(p0["r"])) / 6.0,
                    ),
                    c2=SPoint(
                        z=float(p2["z"]) - (float(p3["z"]) - float(p1["z"])) / 6.0,
                        r=float(p2["r"]) - (float(p3["r"]) - float(p1["r"])) / 6.0,
                    ),
                )
            )
        else:
            out.append(
                SketchSeg(
                    id=new_seg_id(),
                    kind="line",
                    a=SPoint(z=float(p1["z"]), r=float(p1["r"])),
                    b=SPoint(z=float(p2["z"]), r=float(p2["r"])),
                )
            )
    return out


def branch_path_points(branch: List[SPoint], blank_r: float, blank_l: float) -> List[Dict[str, Any]]:
    return [
        {
            "id": _next_branch_id(),
            "z": min(blank_l, max(0.0, p.z)),
            "r": min(blank_r, max(0.0, p.r)),
            "smooth": False,
        }
        for p in branch
        if math.isfinite(p.z) and math.isfinite(p.r)
    ]


def branch_points(branch: List[SPoint], blank_r: float, blank_l: float, keep: Literal["max", "min"]) -> List[Dict[str, Any]]:
    raw: List[SPoint] = []
    for p in branch:
        if not math.isfinite(p.z) or not math.isfinite(p.r):
            continue
        raw.append(SPoint(z=min(blank_l, max(0.0, p.z)), r=min(blank_r, max(0.0, p.r))))
    if len(raw) < 2:
        return []
    raw.sort(key=lambda x: x.z)
    merged: List[SPoint] = []
    for p in raw:
        if merged and abs(merged[-1].z - p.z) < 0.06:
            if (p.r > merged[-1].r) if keep == "max" else (p.r < merged[-1].r):
                merged[-1].r = p.r
        else:
            merged.append(p.copy())
    if len(merged) < 2:
        return []
    return [{"id": _next_branch_id(), "z": p.z, "r": p.r, "smooth": False} for p in merged]


def normalize_sketch(raw: Any) -> Optional[List[SketchSeg]]:
    global _seg_uid
    if not isinstance(raw, list) or not raw:
        return None

    def ok_pt(v: Any) -> bool:
        return (
            isinstance(v, dict)
            and isinstance(v.get("z"), (int, float))
            and isinstance(v.get("r"), (int, float))
            and math.isfinite(float(v["z"]))
            and math.isfinite(float(v["r"]))
        )

    out: List[SketchSeg] = []
    for s in raw:
        if not isinstance(s, dict) or not ok_pt(s.get("a")) or not ok_pt(s.get("b")):
            continue
        kind = s.get("kind")
        if kind not in ("line", "quad", "cubic", "arc"):
            continue
        if kind == "quad" and not ok_pt(s.get("c1")):
            continue
        if kind == "cubic" and (not ok_pt(s.get("c1")) or not ok_pt(s.get("c2"))):
            continue
        if kind == "arc" and not ok_pt(s.get("via")):
            continue
        sid = int(s["id"]) if isinstance(s.get("id"), (int, float)) else new_seg_id()
        fillet_raw = s.get("filletOf")
        fillet_of = (
            (int(fillet_raw[0]), int(fillet_raw[1]))
            if isinstance(fillet_raw, (list, tuple)) and len(fillet_raw) == 2
            else None
        )
        arc_div = (
            max(2, min(500, int(round(float(s["arcDivisions"])))))
            if isinstance(s.get("arcDivisions"), (int, float)) and math.isfinite(float(s["arcDivisions"]))
            else None
        )
        out.append(
            SketchSeg(
                id=sid,
                kind=kind,
                a=SPoint(z=float(s["a"]["z"]), r=float(s["a"]["r"])),
                b=SPoint(z=float(s["b"]["z"]), r=float(s["b"]["r"])),
                c1=SPoint(z=float(s["c1"]["z"]), r=float(s["c1"]["r"])) if ok_pt(s.get("c1")) else None,
                c2=SPoint(z=float(s["c2"]["z"]), r=float(s["c2"]["r"])) if ok_pt(s.get("c2")) else None,
                via=SPoint(z=float(s["via"]["z"]), r=float(s["via"]["r"])) if ok_pt(s.get("via")) else None,
                polylineId=int(s["polylineId"]) if isinstance(s.get("polylineId"), (int, float)) else None,
                filletOf=fillet_of,
                arcDivisions=arc_div,
            )
        )
    for s in out:
        _seg_uid = max(_seg_uid, s.id)
    return out if out else None
