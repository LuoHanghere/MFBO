"""Inspect face zones in a Fluent mesh file (meshing mode)."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bofm.cfd.fluent as F

ap = argparse.ArgumentParser()
ap.add_argument("--mesh", required=True)
ap.add_argument("--cores", type=int, default=1)
ap.add_argument("--out-json")
args = ap.parse_args()

m = None
try:
    m = F.launch(mode="meshing", processor_count=args.cores, ui_mode="no_gui")
    m.tui.file.read_mesh(str(Path(args.mesh).resolve()))
    mu = m.meshing_utilities
    ids = list(mu.get_face_zones(filter="*"))
    names = list(mu.convert_zone_ids_to_name_strings(zone_id_list=ids))
    zones = []
    for zid, name in zip(ids, names):
        bbox = mu.get_bounding_box_of_zone_list(zone_id_list=[zid])
        zones.append(
            {
                "id": int(zid),
                "name": str(name),
                "type": str(mu.get_zone_type(zone_id=zid)),
                "face_count": int(mu.get_face_zone_count(face_zone_id_list=[zid])),
                "bbox": bbox,
            }
        )
    for zone in zones:
        print(zone["id"], zone["name"], zone["type"])
    if args.out_json:
        out = Path(args.out_json).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"mesh": str(Path(args.mesh).resolve()), "zones": zones}, indent=2), encoding="utf-8")
finally:
    if m is not None:
        m.exit()
