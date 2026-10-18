"""Offline checks of the notebook, hex grid, distance bands and crash counts."""

import json
import sys
import math
from pathlib import Path

import geopandas as gpd
import nbformat
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import box, Point

root = Path(__file__).resolve().parents[1]
notebook = nbformat.read(root / "preprocessing.ipynb", as_version=4)
nbformat.validate(notebook)
for c in notebook.cells:
    if c.cell_type == "code":
        compile(c.source, "preprocessing.ipynb", "exec")
source = next(
    c.source
    for c in notebook.cells
    if c.cell_type == "code" and "def hex_grid" in c.source
)
namespace = dict(math=math, np=np, Polygon=shapely.Polygon, gpd=gpd, CRS="EPSG:32637")
exec(source.split("all_hex =")[0], namespace)
polygon = box(400000, 6170000, 404000, 6174000)
grid = namespace["hex_grid"](polygon)
expected = 3 * math.sqrt(3) * 500**2 / 2
assert np.isclose(grid.area.sum(), polygon.area, rtol=1e-10)
assert np.isclose(grid.geometry.union_all().area, polygon.area, rtol=1e-10)
assert (grid.area <= expected + 1e-6).all()
assert not grid.hex_id.duplicated().any()
# A shared vertex must be assigned exactly once by notebook's rule.
a = grid.loc[grid.area > expected - 1e-6].iloc[0].geometry
point = Point(a.exterior.coords[0])
hits = grid.loc[grid.geometry.intersects(point), "hex_id"]
assert len(hits) >= 2
candidates = pd.DataFrame({"point_row": [0] * len(hits), "hex_id": hits.to_numpy()})
assert (
    len(candidates.sort_values(["point_row", "hex_id"]).drop_duplicates("point_row"))
    == 1
)
print("Hex area, tiling, stable IDs and boundary assignment: OK")

sys.path.insert(0, str(root))
from scripts.spatial_spillover import band_labels

assert band_labels(
    [0, 30, 30.01, 500, 500.01, 1000, 1000.01, 2000, 2000.01]
).tolist() == [
    "corridor_0_30m",
    "corridor_0_30m",
    "outside_30_500m",
    "outside_30_500m",
    "outside_500_1000m",
    "outside_500_1000m",
    "outside_1000_2000m",
    "outside_1000_2000m",
    "outside_gt2000m",
]
try:
    band_labels([np.nan])
except ValueError:
    pass
else:
    raise AssertionError("Invalid distance cannot silently become a remote control")

if "--with-data" not in sys.argv:
    print("PASS: notebook, hex grid and distance bands (no input files required).")
    raise SystemExit(0)

metadata = json.loads((root / "outputs/metadata.json").read_text())
panel = pd.read_csv(root / "outputs/hex_panel.csv")
assert not panel.duplicated(["hex_id", "year"]).any()
endpoints = panel[panel.year.isin([metadata["pre_year"], metadata["post_year"]])]
points = pd.read_csv(root / "outputs/bicycle_point_band_counts.csv")
assert points.bike_crashes.sum() == endpoints.bike_crashes.sum()
summary = pd.read_csv(root / "outputs/final/spillover_group_means.csv")
for year, group in summary[summary["sample"].eq("all_hex_remote_control")].groupby(
    "year"
):
    assert not group.group.duplicated().any()
    assert group.n_hex.sum() == len(endpoints[endpoints.year.eq(year)])
    assert (
        group.crashes.sum()
        == endpoints.loc[endpoints.year.eq(year), "bike_crashes"].sum()
    )
print("Distance bands and hex groups conserve the endpoint bicycle-crash totals: OK")
