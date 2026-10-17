import json
import unittest
import urllib.request
from kharratcode.ai import parse_illustrator, transform_ai_segments
from kharratcode.dxf import build_dxf
from kharratcode.lathe import (
    PRESETS,
    STRATEGIES,
    apply_gcode_ovr,
    generate,
    make_ops,
    normalize_params,
    preset_points,
    rotational_envelope,
    tool_profile,
)
from kharratcode.server import generate_from_sketch_or_points, start_background_server
from kharratcode.sketch import (
    SPoint,
    arc_info,
    branch_path_points,
    branch_points,
    chain_polyline,
    flatten_sketch,
    make_seg,
    normalize_sketch,
    order_chain,
    seg_bounds,
    sketch_from_points,
    sketch_from_wall,
    split_chain_at,
)


class TestKharratCodePythonEngine(unittest.TestCase):
    def test_sketch_geometry_and_flatten(self) -> None:
        line = make_seg("line", [SPoint(0, 10), SPoint(50, 20)])
        arc = make_seg("arc", [SPoint(50, 20), SPoint(100, 15), SPoint(75, 25)])
        self.assertIsNotNone(line)
        self.assertIsNotNone(arc)
        assert line is not None and arc is not None
        info = arc_info(arc)
        self.assertIsNotNone(info)
        bounds = seg_bounds(arc)
        self.assertGreaterEqual(bounds.maxR, 25.0 - 1e-3)
        flat = flatten_sketch([line, arc], blank_r=40.0, blank_l=120.0)
        self.assertGreater(len(flat), 5)

    def test_all_presets_generate_gcode_and_dxf(self) -> None:
        for preset in PRESETS:
            if preset.get("empty"):
                continue
            pts = preset_points(preset)
            strat_id = preset.get("strategy", "g71")
            strat = next((s for s in STRATEGIES if s["id"] == strat_id), STRATEGIES[0])
            for fmt in ("modal", "std"):
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
                inner_pts = None
                outer_finish_pts = None
                if preset.get("wall") and preset.get("split"):
                    wall_dicts = [{"z": w[0], "r": w[1], "smooth": w[2]} for w in preset["wall"]]
                    segs = sketch_from_wall(wall_dicts)
                    chain = order_chain(segs)
                    poly = chain_polyline(chain)
                    sp = split_chain_at(poly, SPoint(z=float(preset["split"]["z"]), r=float(preset["split"]["r"])))
                    blank_r = params.blankD / 2.0
                    from kharratcode.lathe import PPoint

                    pts = [PPoint.from_dict(p) for p in branch_points(sp.outer, blank_r, params.blankL, "max")]
                    outer_finish_pts = [PPoint.from_dict(p) for p in branch_path_points(sp.outer, blank_r, params.blankL)]
                    inner_pts = [PPoint.from_dict(p) for p in branch_path_points(sp.inner, blank_r, params.blankL)]

                res = generate(pts, params, inner_pts, outer_finish_pts)
                self.assertGreater(len(res.lines), 5, f"Preset {preset['id']} ({fmt}) produced too few lines")
                self.assertGreater(len(res.segs), 2, f"Preset {preset['id']} ({fmt}) produced too few segs")
                self.assertEqual(res.lines[0], "%")
                self.assertEqual(res.lines[-1], "%")

                dxf = build_dxf(res.segs, params.ops, params.blankL, params.blankD / 2.0)
                self.assertIn("LWPOLYLINE", dxf.text)
                self.assertGreater(dxf.vertexCount, 2)

    def test_ai_import_parser(self) -> None:
        sample_eps = """%!PS-Adobe-3.0 EPSF-3.0
%%Creator: Adobe Illustrator(R) 8.0
0 0 m
100 50 l
150 60 180 40 200 30 c
S
"""
        doc = parse_illustrator(sample_eps)
        self.assertEqual(len(doc.segments), 2)
        transformed = transform_ai_segments(doc, 1.0)
        self.assertEqual(len(transformed), 2)

    def test_http_server_endpoints(self) -> None:
        server, port = start_background_server("127.0.0.1", 0)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health") as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(data["status"], "ok")
                self.assertEqual(data["engine"], "python")

            req_body = json.dumps(
                {
                    "points": [{"id": 1, "z": 0, "r": 20, "smooth": False}, {"id": 2, "z": 100, "r": 25, "smooth": False}],
                    "params": {"blankD": 60, "blankL": 100, "format": "modal"},
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/generate",
                data=req_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as resp:
                gen = json.loads(resp.read().decode("utf-8"))
                self.assertGreater(len(gen["lines"]), 5)
                self.assertGreater(gen["cutLen"], 0)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
