"""Prepare fixed spatial exposure and point-distance diagnostics from saved preprocessing."""

from pathlib import Path
import json
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely

POINT_EDGES_M = [30.0, 500.0, 1000.0, 2000.0]
POINT_LABELS = [
    "corridor_0_30m",
    "outside_30_500m",
    "outside_500_1000m",
    "outside_1000_2000m",
    "outside_gt2000m",
]


def band_labels(distance, edges=POINT_EDGES_M, labels=POINT_LABELS):
    """Disjoint right-closed bands; every finite nonnegative distance counted once."""
    values = np.asarray(distance, dtype=float)
    if np.any(~np.isfinite(values)) or np.any(values < 0):
        raise ValueError("Distance must be finite and nonnegative")
    return np.asarray(labels)[np.searchsorted(edges, values, side="left")]


def prepare_spillovers(root=Path(".")):
    root = Path(root)
    out = root / "outputs"
    meta = json.loads((out / "metadata.json").read_text())
    crs = meta["metric_crs"]
    hexes = gpd.read_file(out / "hexagons_500m.gpkg", layer="hexagons").to_crs(crs)
    boundary = (
        gpd.read_file(root / "moscow_boundary.geojson").to_crs(crs).geometry.union_all()
    )
    bike = gpd.read_file(root / "bike_lanes_singlepart.geojson").to_crs(crs)
    bike = bike.loc[bike.geometry.notna() & ~bike.geometry.is_empty].copy()
    bike["geometry"] = shapely.make_valid(bike.geometry)
    bike = gpd.clip(bike, gpd.GeoSeries([boundary], crs=crs), keep_geom_type=True)
    bike = bike.loc[
        bike.geometry.geom_type.isin(["LineString", "MultiLineString"])
        & bike.length.gt(0)
    ]
    if bike.empty:
        raise ValueError("Empty bike layer")
    bike_union = bike.geometry.union_all()
    # Same lane definition as notebook; geometry distance, not a street-network distance.
    centroids = gpd.GeoSeries(
        gpd.points_from_xy(hexes.center_x, hexes.center_y), crs=crs
    )
    exposure = pd.DataFrame(
        {
            "hex_id": hexes.hex_id,
            "treated_current": hexes.treated_current,
            "distance_hex_edge_m": hexes.geometry.distance(bike_union),
            "distance_hex_center_m": centroids.distance(bike_union),
        }
    )
    if exposure.hex_id.duplicated().any():
        raise ValueError("Duplicate cells")
    # Verify new preprocessing matches the spatial definition of existing panel.
    if not np.allclose(
        exposure.distance_hex_edge_m, hexes.distance_to_bike_m, atol=1e-5
    ):
        raise ValueError(
            "Bike layer changed: rerun full notebook before spillover analysis"
        )
    exposure.to_csv(out / "spillover_exposure.csv", index=False)

    # Point distances distinguish accidents near a lane from other streets within the same hex.
    # A distance within 30 m does not establish that a crash happened on the lane.
    points = pd.read_csv(out / "bicycle_crashes.csv", dtype={"crash_id": str})
    assigned = pd.read_csv(
        out / "bicycle_crashes_assigned.csv", dtype={"crash_id": str}
    )
    points = points.merge(
        assigned[["crash_id", "hex_id"]],
        on="crash_id",
        how="inner",
        validate="one_to_one",
    )
    geometry = gpd.GeoSeries(
        gpd.points_from_xy(points.lon, points.lat), crs=4326
    ).to_crs(crs)
    points["distance_to_bike_m"] = geometry.distance(bike_union)
    points["distance_band"] = band_labels(points.distance_to_bike_m)
    points = points.merge(
        exposure[["hex_id", "treated_current"]], on="hex_id", validate="many_to_one"
    )
    points.to_csv(out / "bicycle_crashes_spatial.csv", index=False)
    chosen = points.loc[
        points.year.isin([meta["pre_year"], meta["post_year"]])
        & points.month.isin(meta["months"])
    ].copy()
    index = pd.MultiIndex.from_product(
        [[meta["pre_year"], meta["post_year"]], [0, 1], POINT_LABELS],
        names=["year", "treated_current", "distance_band"],
    )
    diagnostic = (
        chosen.groupby(["year", "treated_current", "distance_band"])
        .size()
        .reindex(index, fill_value=0)
        .rename("bike_crashes")
        .reset_index()
    )
    diagnostic.to_csv(out / "bicycle_point_band_counts.csv", index=False)
    assert int(diagnostic.bike_crashes.sum()) == len(chosen)
    if len(points) != len(assigned):
        raise ValueError(
            "Some assigned bicycle accidents lack coordinates in the mapped export"
        )
    (out / "spillover_metadata.json").write_text(
        json.dumps(
            {
                "pre_year": meta["pre_year"],
                "post_year": meta["post_year"],
                "months": meta["months"],
                "hex_ring_edges_m": [500, 1000, 2000],
                "point_ring_edges_m": POINT_EDGES_M,
                "distance_definition": "Euclidean distance to current bike geometry in metric CRS",
                "historical_treatment_verified": False,
                "point_band_counts_are_descriptive": True,
                "assigned_bicycle_crashes": len(points),
                "endpoint_bicycle_crashes": len(chosen),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(
        "Saved exposure for",
        len(exposure),
        "hexagons and point distances for",
        len(points),
        "bicycle crashes",
    )
    print(diagnostic.to_string(index=False))
    return exposure


if __name__ == "__main__":
    prepare_spillovers()
