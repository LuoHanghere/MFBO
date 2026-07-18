"""Fluent Meshing (watertight) utilities for the C3X fluid domain.

CAD bridge findings (PyFluent 0.20.0 + Fluent Meshing 2024R2, headless):
  * Historical finding: native SpaceClaim **.scdoc** attachment failed before
    the workstation CAD readers were reconfigured.
  * Current finding (2026-07-03): native SCDOC import works with
    ``UseBodyLabels='Yes'``.  The production native-CAD path is implemented by
    ``scripts/run_fluent_native_cad_mesh.py``.
  * Headless SpaceClaim DocumentSave only writes .scdoc / **.sat** (ACIS) / .fmd.
    .fmd is faceted (rejected by watertight import); .pmdb needs Workbench.
  * **.sat imports reliably** (~5 s) but may not carry SpaceClaim named
    selections unless Fluent's geometry-label import is explicitly enabled.
  * Fix: import with UseBodyLabels='Yes' and CadImportOptions.OneZonePer='face'
    -> one zone per CAD face, then merge/rename zones into BC groups by
    location as a fallback (classify_zone).

So the boundary tagging that build_fluid_domain.py does in SpaceClaim is redone
here on the imported zones, using the SAME geometric rules.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

# CAD import options for the watertight "Import Geometry" task. OneZonePer=face
# so the boundary faces arrive as separate zones we can group by location.
IMPORT_CAD_OPTIONS = {
    "OneZonePer": "face",
    "ExtractFeatures": True,
    "FeatureAngle": 40.0,
    "ImportNamedSelections": True,
    "ImportPartNames": True,
}

EPS_MM = 0.5

# The .sat stores geometry as mm-magnitude numbers but Fluent reads ACIS in its
# native units and treats them as METRES (axial extent reads ~234 not 0.234).
# Scale the mesh by this factor before solving.
GEOMETRY_TO_SI = 0.001


@dataclass
class DomainBounds:
    x_in: float
    x_out: float
    pitch_mm: float
    span_mm: float
    te_x_mm: float = 78.16   # axial chord (TE)
    y_low: float | None = None
    y_high: float | None = None
    physical_pitch_mm: float | None = None

    @classmethod
    def from_passage_json(cls, path: str | Path, span_mm: float) -> "DomainBounds":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        pitch = float(d.get("periodic_width_mm", d["pitch_mm"]))
        y_low = d.get("y_low")
        y_high = d.get("y_high")
        return cls(
            float(d["x_in"]),
            float(d["x_out"]),
            pitch,
            float(span_mm),
            y_low=float(y_low) if y_low is not None else None,
            y_high=float(y_high) if y_high is not None else None,
            physical_pitch_mm=float(d.get("physical_pitch_mm", pitch)),
        )

    @property
    def pitch_candidates_mm(self) -> tuple[float, ...]:
        if self.physical_pitch_mm is None or abs(self.physical_pitch_mm - self.pitch_mm) < 1.0e-9:
            return (self.pitch_mm,)
        return (self.pitch_mm, self.physical_pitch_mm)


def classify_zone(bbox_mm: tuple, b: DomainBounds) -> str:
    """Map a face-zone bounding box (x0,y0,z0,x1,y1,z1 in mm) to a BC group name.

    Mirrors build_fluid_domain.py's SpaceClaim-side classification:
      span_*  : planar in z (dz~0), low/high by z
      inlet   : planar in x at x_in;  outlet: planar in x at x_out
      periodic: side face touching x_in or x_out (extension lines)
      vane_wall: everything else (blade surfaces)
    Periodic low/high still need the +pitch pairing done on the full set.
    """
    x0, y0, z0, x1, y1, z1 = bbox_mm
    dz, dx, dy = z1 - z0, x1 - x0, y1 - y0
    cy = 0.5 * (y0 + y1)
    cz = 0.5 * (z0 + z1)
    if dz < EPS_MM:
        return "span_low" if cz < b.span_mm * 0.5 else "span_high"
    axial = b.x_out - b.x_in
    if b.y_low is not None and dy < EPS_MM and dx > 0.5 * axial and abs(cy - b.y_low) < EPS_MM:
        return "periodic_low"
    if b.y_high is not None and dy < EPS_MM and dx > 0.5 * axial and abs(cy - b.y_high) < EPS_MM:
        return "periodic_high"
    if dx < EPS_MM and abs(0.5 * (x0 + x1) - b.x_in) < EPS_MM:
        return "inlet"
    if dx < EPS_MM and abs(0.5 * (x0 + x1) - b.x_out) < EPS_MM:
        return "outlet"
    touches_in = abs(x0 - b.x_in) < EPS_MM or abs(x1 - b.x_in) < EPS_MM
    touches_out = abs(x0 - b.x_out) < EPS_MM or abs(x1 - b.x_out) < EPS_MM
    # Surface-mesh wrappers can span inlet->outlet; those are not periodic extensions.
    if touches_in and touches_out:
        return "vane_wall"
    if touches_in or touches_out:
        return "periodic"   # split into low/high by +pitch pairing on caller side
    return "vane_wall"


@dataclass
class CaseFaceZone:
    name: str
    bbox_mm: tuple[float, float, float, float, float, float]
    n_faces: int


def face_zone_bboxes_from_case(case_path: str | Path) -> dict[str, CaseFaceZone]:
    """Read Fluent HDF5 mesh/case and return face-zone bounding boxes in mm.

    Fluent solver cases are stored in SI units after the meshing->solver switch.
    The geometry pipeline works in mm for classification, so coordinates are
    converted back to mm here.
    """
    zones: dict[str, CaseFaceZone] = {}
    with h5py.File(case_path, "r") as f:
        zt = f["meshes/1/faces/zoneTopology"]
        zone_ids = zt["id"][()]
        mins = zt["minId"][()]
        maxs = zt["maxId"][()]
        raw_names = zt["name"][0].decode("utf-8")
        names = raw_names.split(";")

        face_nodes_group = f["meshes/1/faces/nodes"]
        face_nodes_key = next(iter(face_nodes_group.keys()))
        n_nodes_per_face = face_nodes_group[face_nodes_key]["nnodes"][()]
        flat_nodes = face_nodes_group[face_nodes_key]["nodes"][()]
        coords_group = f["meshes/1/nodes/coords"]
        coords_key = next(iter(coords_group.keys()))
        coords_mm = coords_group[coords_key][()] * 1000.0
        offsets = np.concatenate([[0], np.cumsum(n_nodes_per_face)])

        for zone_id, name, lo, hi in zip(zone_ids, names, mins, maxs):
            if name.startswith("interior"):
                continue
            node_ids: list[int] = []
            for face_idx in range(int(lo) - 1, int(hi)):
                node_ids.extend(flat_nodes[offsets[face_idx]:offsets[face_idx + 1]])
            if not node_ids:
                continue
            pts = coords_mm[np.asarray(node_ids, dtype=np.int64) - 1]
            mn = pts.min(axis=0)
            mx = pts.max(axis=0)
            zones[name] = CaseFaceZone(
                name=name,
                bbox_mm=(float(mn[0]), float(mn[1]), float(mn[2]),
                         float(mx[0]), float(mx[1]), float(mx[2])),
                n_faces=int(hi) - int(lo) + 1,
            )
    return zones


def classify_split_case_boundaries(case_path: str | Path, b: DomainBounds,
                                   *, eps_mm: float = 1.0) -> dict:
    """Classify solver-split face zones into BC groups and periodic pairs.

    After watertight volume meshing, Fluent can merge the external boundary into
    one wall zone. Splitting by significant angle recovers many wall zones. This
    routine filters tiny split slivers near span caps back into vane_wall and
    pairs only translationally matching periodic candidates.
    """
    zones = face_zone_bboxes_from_case(case_path)
    groups = {k: [] for k in GROUP_NAMES}
    candidates: list[tuple[str, float, float]] = []
    axial = b.x_out - b.x_in

    for name, z in zones.items():
        x0, y0, z0, x1, y1, z1 = z.bbox_mm
        dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
        cx, cy, cz = 0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1)

        # True span caps cover most of the passage footprint. Tiny angle-split
        # faces on the blade near z=0/z=span can also have dz~0; keep those wall.
        if dz < eps_mm and (dx > 0.7 * axial or dy > 0.7 * b.pitch_mm):
            groups["span_low" if cz < b.span_mm * 0.5 else "span_high"].append(name)
        elif b.y_low is not None and dy < eps_mm and dx > 0.5 * axial and abs(cy - b.y_low) < eps_mm:
            groups["periodic_low"].append(name)
        elif b.y_high is not None and dy < eps_mm and dx > 0.5 * axial and abs(cy - b.y_high) < eps_mm:
            groups["periodic_high"].append(name)
        elif dx < eps_mm and abs(cx - b.x_in) < eps_mm and dy > 0.5 * b.pitch_mm:
            groups["inlet"].append(name)
        elif dx < eps_mm and abs(cx - b.x_out) < eps_mm and dy > 0.5 * b.pitch_mm:
            groups["outlet"].append(name)
        elif (abs(x0 - b.x_in) < eps_mm or abs(x1 - b.x_out) < eps_mm) and z.n_faces > 10:
            candidates.append((name, cx, cy))
        else:
            groups["vane_wall"].append(name)

    used: set[int] = set()
    periodic_pairs: list[tuple[str, str]] = []
    for i, (name, cx, cy) in enumerate(candidates):
        if i in used:
            continue
        match = None
        is_low = True
        for j, (other, ox, oy) in enumerate(candidates):
            if i == j or j in used:
                continue
            for pitch_i in b.pitch_candidates_mm:
                if abs(ox - cx) < 3.0 and abs((cy + pitch_i) - oy) < 3.0:
                    match, is_low = j, True
                    break
                if abs(ox - cx) < 3.0 and abs((cy - pitch_i) - oy) < 3.0:
                    match, is_low = j, False
                    break
            if match is not None:
                break
        if match is None:
            groups["vane_wall"].append(name)
            used.add(i)
            continue
        low, high = (name, candidates[match][0]) if is_low else (candidates[match][0], name)
        groups["periodic_low"].append(low)
        groups["periodic_high"].append(high)
        periodic_pairs.append((low, high))
        used.add(i)
        used.add(match)

    groups["periodic_pairs"] = periodic_pairs
    return groups


GROUP_NAMES = ("inlet", "outlet", "span_low", "span_high",
               "periodic_low", "periodic_high", "vane_wall")


def assign_groups(zone_bboxes_mm: dict, b: DomainBounds) -> dict:
    """Map {zone_id: bbox_mm} -> {group_name: [zone_id,...]}.

    Periodic faces are paired by +pitch in y so each pair is split into
    periodic_low / periodic_high (matching translational-periodic BC setup).
    """
    groups = {k: [] for k in GROUP_NAMES}
    periodic = []  # (zone_id, cx, cy)
    for zid, bb in zone_bboxes_mm.items():
        g = classify_zone(bb, b)
        if g == "periodic":
            periodic.append((zid, 0.5 * (bb[0] + bb[3]), 0.5 * (bb[1] + bb[4])))
        else:
            groups[g].append(zid)

    used = set()
    for i in range(len(periodic)):
        if i in used:
            continue
        zid, cx, cy = periodic[i]
        match, is_low = None, True
        for j in range(len(periodic)):
            if j == i or j in used:
                continue
            zj, cxj, cyj = periodic[j]
            for pitch_i in b.pitch_candidates_mm:
                if abs(cxj - cx) < EPS_MM and abs((cy + pitch_i) - cyj) < 3.0:
                    match, is_low = j, True
                    break
                if abs(cxj - cx) < EPS_MM and abs((cy - pitch_i) - cyj) < 3.0:
                    match, is_low = j, False
                    break
            if match is not None:
                break
        if match is not None:
            lo, hi = (zid, periodic[match][0]) if is_low \
                else (periodic[match][0], zid)
            groups["periodic_low"].append(lo)
            groups["periodic_high"].append(hi)
            used.add(i)
            used.add(match)
        else:
            groups["periodic_low"].append(zid)
            used.add(i)
    return groups


def get_zone_bboxes_mm(meshing_utilities, expected_axial_mm: float,
                       *, boundary_only: bool = False) -> dict:
    """Return {zone_id: bbox_mm} for all face zones, auto-correcting m vs mm."""
    ids = list(meshing_utilities.get_face_zones(filter="*"))
    if boundary_only:
        ids = [
            zid for zid in ids
            if str(meshing_utilities.get_zone_type(zone_id=zid)).lower() != "interior"
        ]
    raw, gx0, gx1 = {}, None, None
    for zid in ids:
        bb = meshing_utilities.get_bounding_box_of_zone_list(zone_id_list=[zid])
        (x0, y0, z0), (x1, y1, z1) = bb[0], bb[1]
        raw[zid] = (x0, y0, z0, x1, y1, z1)
        gx0 = x0 if gx0 is None else min(gx0, x0)
        gx1 = x1 if gx1 is None else max(gx1, x1)
    scale = 1000.0 if (gx1 - gx0) < expected_axial_mm / 10.0 else 1.0
    return {zid: tuple(c * scale for c in v) for zid, v in raw.items()}


WATERTIGHT_SURFACE_CONTROLS = {"MinSize": 0.2, "MaxSize": 4.0, "GrowthRate": 1.2}


def estimate_first_cell_mm(*, y_plus: float, reynolds: float,
                           length_mm: float) -> float:
    """Heuristic first-layer height [mm] for target y+ (turbulent, high Re)."""
    # Calibrated order-of-magnitude for compressor/vane external flows.
    h = 1.5 * length_mm / (reynolds ** 0.8) * y_plus
    return float(max(0.001, min(h, 0.05)))


def _apply_bl_control(m, *, n_prism: int, growth_rate: float,
                      first_height_mm: float | None,
                      zone_names: list[str] | None) -> None:
    """Configure prism BL via the watertight workflow task (no custom TUI)."""
    bl = m.workflow.TaskObject["Add Boundary Layers"]
    args: dict = {
        "BLControlName": "smooth-transition_1",
        "NumberOfLayers": n_prism,
        "Rate": growth_rate,
        "OffsetMethodType": "first-height" if first_height_mm is not None else "smooth-transition",
    }
    if first_height_mm is not None:
        args["FirstHeight"] = first_height_mm
    if zone_names:
        for key in ("ZoneSelectionList", "BLZoneList"):
            try:
                bl.arguments.set_state({**args, key: zone_names})
                return
            except Exception:
                pass
    bl.arguments.set_state(args)


def _run_task(wf, name: str, args: dict | None = None) -> None:
    t = wf.TaskObject[name]
    if args:
        t.arguments.set_state(args)
    t.Execute()


def build_watertight_mesh(m, sat_path, b: DomainBounds, out_msh=None, *,
                          n_prism: int = 8, volume_fill: str = "poly-hexcore",
                          surface_controls: dict = None,
                          prism_growth_rate: float = 1.2,
                          first_height_mm: float | None = None,
                          bl_zone_names: list[str] | None = None,
                          extra_face_targets: dict[str, tuple] | None = None,
                          hole_diameter_mm: float | None = None) -> dict:
    """Full no-film watertight mesh: import .sat -> re-tag BC zones -> surface
    mesh -> describe -> boundaries/regions -> prism BL -> volume mesh -> write.

    Returns the {group: [zone_id]} BC map. Validated 2026-06 on the C3X no-film
    slice (poly-hexcore, 8 prism layers). NOTE: scale the mesh by GEOMETRY_TO_SI
    in the solver (the .sat is mm-magnitude read as metres).
    """
    wf = m.workflow
    wf.InitializeWorkflow(WorkflowType="Watertight Geometry")
    _run_task(wf, "Import Geometry",
              {
                  "FileName": str(sat_path),
                  "UseBodyLabels": "Yes",
                  "CadImportOptions": IMPORT_CAD_OPTIONS,
              })

    groups = tag_zones(
        m, b, rename=True, extra_face_targets=extra_face_targets,
        hole_diameter_mm=hole_diameter_mm,
    )

    _run_task(wf, "Generate the Surface Mesh",
              {"CFDSurfaceMeshControls": surface_controls or WATERTIGHT_SURFACE_CONTROLS})

    # Keep import-time BC zone names; re-tagging after surface mesh mis-classifies
    # the extra envelope wrapper Fluent adds on fine surface meshes.

    _run_task(wf, "Describe Geometry",
              {"SetupType": "The geometry consists of only fluid regions with no voids"})
    _run_task(wf, "Update Boundaries")
    _run_task(wf, "Update Regions")

    bl_zones = bl_zone_names if bl_zone_names is not None else ["vane_wall"]
    _apply_bl_control(m, n_prism=n_prism, growth_rate=prism_growth_rate,
                      first_height_mm=first_height_mm, zone_names=bl_zones)
    _run_task(wf, "Add Boundary Layers")

    _run_task(wf, "Generate the Volume Mesh", {
        "VolumeFill": volume_fill,
        "ReMergeZones": "No",
        "MergeCellZones": False,
        "PrismPreferences": {"MergeBoundaryLayers": "no"},
        "VolumeMeshPreferences": {
            "PrepareZoneNames": "yes",
            "MergeBodyLabels": "no",
        },
    })

    if out_msh:
        m.tui.file.write_mesh(str(out_msh))
    return groups


def _bbox_center(bb: tuple) -> tuple[float, float, float]:
    return (0.5 * (bb[0] + bb[3]), 0.5 * (bb[1] + bb[4]), 0.5 * (bb[2] + bb[5]))


def _dist3(a: tuple, b: tuple) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)))


def _claim_extra_targets(bboxes: dict, targets: dict[str, tuple]) -> dict[str, list]:
    """Claim imported face zones nearest to explicit target points.

    `targets` maps boundary name -> (x_mm, y_mm, z_mm, tolerance_mm).
    Claimed zone ids are removed from the regular geometric classifier so
    coolant/plenum inlets do not get merged into `vane_wall`.
    """
    claimed: dict[str, list] = {}
    used: set = set()
    for name, spec in targets.items():
        pt = tuple(float(v) for v in spec[:3])
        tol = float(spec[3]) if len(spec) > 3 else 2.0
        best, best_d = None, 1.0e99
        for zid, bb in bboxes.items():
            if zid in used:
                continue
            d = _dist3(_bbox_center(bb), pt)
            if d < best_d:
                best, best_d = zid, d
        if best is not None and best_d <= tol:
            claimed[name] = [best]
            used.add(best)
    for zid in used:
        bboxes.pop(zid, None)
    return claimed


def _claim_film_hole_walls(bboxes: dict, diameter_mm: float | None) -> list:
    """Remove and return lateral film-hole zones using their z extent.

    All current C3X cylinders lie in the XY plane. After boolean union their
    lateral wall has a z extent of one diameter, while vane and plenum side
    walls span the full 14.85 mm period. This remains stable as row positions
    and in-plane injection angles change.
    """
    if diameter_mm is None:
        return []
    diameter = float(diameter_mm)
    claimed = []
    for zid, bb in list(bboxes.items()):
        dx, dy, dz = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]
        if 0.75 * diameter <= dz <= 1.25 * diameter and max(dx, dy) >= 1.5 * diameter:
            claimed.append(zid)
            bboxes.pop(zid, None)
    return claimed


def tag_zones(m, b: DomainBounds, rename: bool = True,
              extra_face_targets: dict[str, tuple] | None = None,
              hole_diameter_mm: float | None = None,
              boundary_only: bool = False) -> dict:
    """Classify imported face zones into BC groups and (optionally) rename+merge
    them into the 7 named boundary zones. Returns the {group: [zone_id]} map."""
    mu = m.meshing_utilities
    bboxes = get_zone_bboxes_mm(mu, b.x_out - b.x_in, boundary_only=boundary_only)
    extra_groups = _claim_extra_targets(bboxes, extra_face_targets or {})
    hole_walls = _claim_film_hole_walls(bboxes, hole_diameter_mm)
    groups = assign_groups(bboxes, b)
    groups["film_hole_wall"] = hole_walls
    groups.update(extra_groups)
    if rename:
        for g, zl in groups.items():
            for k, zid in enumerate(zl):
                mu.rename_face_zone(zone_id=zid, new_name="%s_%d" % (g, k))
            if len(zl) > 1:
                mu.merge_face_zones_with_same_prefix(prefix=g + "_")
    return groups
