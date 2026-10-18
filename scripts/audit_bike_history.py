"""Apply saved historical evidence to the current bike-lane layer."""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "bike_lanes_singlepart.geojson"
OUT = ROOT / "outputs/history"


def main():
    evidence = json.loads((ROOT / "data/history_evidence.json").read_text())
    sources = {item["id"]: item for item in evidence["sources"]}
    raw = INPUT.read_bytes()
    features = json.loads(raw)["features"]
    rows = []
    for index, feature in enumerate(features):
        properties = feature["properties"]
        gid = str(properties["global_id"])
        row = {
            "feature_index": index,
            "global_id": gid,
            "part_number": properties["part_number"],
            "name": properties["Bike lane name"],
            "location": properties["Location"],
            "status": "unknown",
            "event_year": "",
            "event_date": "",
            "source_url": "",
            "evidence": "История этого отрезка не проверена.",
            "spatial_confidence": "not_verified",
            "baseline_2015_concern": 0,
        }
        annotation = evidence["annotations"].get(gid)
        if annotation:
            annotation = annotation.copy()
            expected = annotation.pop("expected_properties", {})
            for key, value in expected.items():
                if properties[key] != value:
                    raise ValueError(f"Historical match changed: {gid}, {key}")
            row["source_url"] = sources[annotation.pop("source_id")]["url"]
            row.update(annotation)
        rows.append(row)

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "lane_history.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    summary = {key: value for key, value in evidence.items() if key != "annotations"}
    summary.update(
        input=INPUT.name,
        input_sha256=hashlib.sha256(raw).hexdigest(),
        n_features=len(features),
        n_unique_global_ids=len({row["global_id"] for row in rows}),
        feature_status_counts=dict(Counter(row["status"] for row in rows)),
        n_features_with_baseline_concern=sum(
            row["baseline_2015_concern"] for row in rows
        ),
        n_department_culture_features=sum(
            "КУЛЬТУРЫ" in feature["properties"]["Departmental affiliation"]
            for feature in features
        ),
        lane_type_counts=dict(
            Counter(feature["properties"]["Bike lane type"] for feature in features)
        ),
    )
    (OUT / "history_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Частей: {len(rows)}; разметка: {summary['feature_status_counts']}")


if __name__ == "__main__":
    main()
