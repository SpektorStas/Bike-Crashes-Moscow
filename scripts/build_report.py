"""Build one offline HTML file from the saved R estimates and map layers."""

from pathlib import Path
from datetime import datetime, timezone
import json
import shutil
import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon, LineString

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
FINAL = OUT / "final"


def number(value, digits=3, signed=False):
    return (
        format(value, f'{"+" if signed else ""}.{digits}f')
        .replace(".", ",")
        .replace("-", "−")
    )


def records(path):
    frame = pd.read_csv(path)
    return json.loads(frame.to_json(orient="records", force_ascii=False))


def map_data(panel, years):
    meta = json.loads((OUT / "metadata.json").read_text())
    crs = meta["metric_crs"]
    hexes = gpd.read_file(OUT / "hexagons_500m.gpkg").to_crs(crs)
    boundary = gpd.read_file(ROOT / "moscow_boundary.geojson").to_crs(crs)
    bike = gpd.read_file(ROOT / "bike_lanes_singlepart.geojson").to_crs(crs)
    mkad = gpd.GeoDataFrame.from_features(
        json.loads((ROOT / "data/mkad.geojson").read_text()), crs=4326
    ).to_crs(crs)
    xmin, ymin, xmax, ymax = boundary.total_bounds
    west, south, east, north = mkad.total_bounds

    def coordinates(points):
        # Local metric coordinates keep the embedded JSON small; north points up.
        return [[round(x - xmin, 1), round(y - ymin, 1)] for x, y, *rest in points]

    def paths(geometry):
        if geometry.is_empty:
            return []
        if isinstance(geometry, Polygon):
            return [coordinates(geometry.exterior.coords)]
        if isinstance(geometry, LineString):
            return [coordinates(geometry.coords)]
        return [p for piece in geometry.geoms for p in paths(piece)]

    counts = panel.pivot(index="hex_id", columns="year", values="bike_crashes")
    features = []
    for row in hexes.itertuples():
        distance = row.distance_to_bike_m
        if row.treated_current:
            group = "core"
        elif distance <= 500:
            group = "ring_0_500m"
        elif distance <= 1000:
            group = "ring_500_1000m"
        elif distance <= 2000:
            group = "ring_1000_2000m"
        else:
            group = "remote"
        geometry = row.geometry
        # At the administrative edge a clipped hex can be multipart. The full
        # geometry is used in analysis; only its largest component is drawn.
        if isinstance(geometry, MultiPolygon):
            geometry = max(geometry.geoms, key=lambda x: x.area)
        features.append(
            {
                "id": row.hex_id,
                "points": paths(geometry)[0],
                "treated": int(row.treated_current),
                "group": group,
                "counts": [int(counts.loc[row.hex_id, y]) for y in years],
            }
        )
    return {
        "bbox": [0, 0, round(xmax - xmin, 1), round(ymax - ymin, 1)],
        "initial_bbox": [
            round(west - xmin, 1),
            round(south - ymin, 1),
            round(east - xmin, 1),
            round(north - ymin, 1),
        ],
        "mkad_paths": [p for g in mkad.geometry for p in paths(g)],
        "hexagons": features,
        "bike_paths": [p for g in bike.geometry for p in paths(g.simplify(12))],
        "boundary": [p for g in boundary.geometry for p in paths(g.simplify(25))],
    }


def main():
    required = [
        FINAL / "models.csv",
        FINAL / "trends.csv",
        ROOT / "report/template.html",
        OUT / "history/history_summary.json",
    ]
    for path in required:
        if not path.exists():
            raise FileNotFoundError(f"Build input missing: {path}")
    meta = json.loads((OUT / "metadata.json").read_text())
    panel = pd.read_csv(OUT / "hex_panel.csv")
    pre, post = int(meta["pre_year"]), int(meta["post_year"])
    years = list(range(pre, post + 1))
    base = panel[panel.year.eq(pre)]
    endpoint = panel[panel.year.eq(post)]
    incomplete = [
        y for y in years if panel.loc[panel.year.eq(y), "months_observed"].min() < 12
    ]
    models = records(FINAL / "models.csv")
    by_id = {row["id"]: row for row in models}
    global_did, local_did = by_id["fd_global"], by_id["fd_local"]
    local_ppml = by_id["ppml_local"]
    spillover_means = pd.read_csv(FINAL / "spillover_group_means.csv")
    local_neighbors = spillover_means[
        spillover_means["sample"].eq("common_blocks_remote_control")
    ]
    local_core_n = int(
        local_neighbors.loc[local_neighbors.group.eq("core"), "n_hex"].iloc[0]
    )
    remote = local_neighbors[local_neighbors.group.eq("control_gt2000m")].set_index(
        "year"
    )
    significant_rings = [
        row
        for row in models
        if row["id"].startswith("spillover_local_ring") and row["ci_high"] < 0
    ]
    significant_totals = [
        row
        for row in models
        if row["id"].startswith("spillover_total_") and row["ci_high"] < 0
    ]
    neighbor_finding = (
        f"Снижение с интервалом ниже нуля получено в {len(significant_rings)} из 3 соседних зон "
        f"и в {len(significant_totals)} из 3 суммарных оценок. "
        if significant_rings or significant_totals
        else "В соседних зонах статистически значимого снижения ДТП нет. "
        "Суммарные оценки для дорожек и их окружения также не показывают снижения. "
    )
    sample_labels = {
        "all_hex": "Все дорожные гексагоны",
        "common_blocks": "Общие блоки 5 км",
        "all_hex_ppml_support": "Весь город; информативные для PPML ячейки",
        "common_blocks_ppml_support": "Общие блоки; информативные для PPML ячейки",
        "all_hex_remote_control": "Весь город; контроль дальше 2 км",
        "common_blocks_remote_control": "Общие блоки; контроль дальше 2 км",
        "common_blocks_center_distance": "Общие блоки; расстояние от центра ячейки",
    }
    for row in models:
        row["sample_label"] = sample_labels.get(row["sample"], row["sample"])
        row["short_note"] = row["sample_label"]
        family = str(row.get("family", ""))
        row["primary"] = str(row.get("primary", "")).lower() in ["true", "1"]
        row["category"] = (
            "spillover"
            if "spill" in family.lower()
            or "spill" in row["id"].lower()
            or row["scale"] == "excess_crashes_total"
            else "main" if row["primary"] else "robustness"
        )
    # The animation and descriptive trend retain the entire original road sample.
    # Model-specific trimmed samples are described in the regression table.
    trends = []
    for (year, treated), group in panel[panel.year.between(pre, post)].groupby(
        ["year", "treated_current"]
    ):
        trends.append(
            {
                "year": int(year),
                "treated": int(treated),
                "mean_outcome": float(group.bike_crashes.mean()),
                "total": int(group.bike_crashes.sum()),
                "cells": len(group),
                "complete": int(year) not in incomplete,
            }
        )
    audit = json.loads((OUT / "history/history_summary.json").read_text())
    history = {
        "title": "Проверка дат открытия",
        "summary": "На улице Алябьева велополосу открыли в июне 2022 года — об этом есть "
        "официальное сообщение. Для остальных линий даты пока не установлены. "
        "Отдельная оценка эффекта по этому участку не проводилась.",
        "items": [
            {
                "label": "Линейных частей",
                "value": audit["n_features"],
                "detail": "Один маршрут может быть разбит на несколько отрезков.",
            },
            {
                "label": "Объектов по global_id",
                "value": audit["n_unique_global_ids"],
                "detail": "Объекты исходного слоя, объединяющие отрезки с одним идентификатором.",
            },
            {
                "label": "Подтверждённый новый участок",
                "value": audit["feature_status_counts"].get("new_after2015", 0),
                "detail": "Улица Алябьева, июнь 2022. Вместе с полосой изменили скоростной режим, организацию движения и светофор.",
            },
            {
                "label": "Без точной исторической разметки",
                "value": audit["feature_status_counts"]["unknown"],
                "detail": "Дата не установлена; это не означает, что участок существовал до 2015 года.",
            },
        ],
        "sources": [{"label": v["title"], "url": v["url"]} for v in audit["sources"]],
        "limitation": "Поиск был выборочным: по его результатам нельзя судить, какая доля сети появилась после 2015 года. "
        "Дата правки в OSM тоже не заменяет дату открытия. "
        "В Москве были велодорожки до 2015 года, а новые открывались и в самом 2015-м. "
        "Поэтому считать 2015 год периодом без велодорожек нельзя.",
    }
    notes = (
        json.loads((FINAL / "analysis_notes.json").read_text())
        if (FINAL / "analysis_notes.json").exists()
        else {}
    )
    payload = {
        "meta": {
            "pre_year": pre,
            "post_year": post,
            "years": years,
            "incomplete_years": incomplete,
            "n_hex": len(base),
            "n_treated": int(base.treated_current.sum()),
            "radius_m": meta["radius_m"],
            "bike_crashes_pre": int(base.bike_crashes.sum()),
            "bike_crashes_post": int(endpoint.bike_crashes.sum()),
            "raw_bicycle_crashes": meta["qa"]["bicycle_crashes_raw"],
            "assigned_bicycle_crashes": int(panel.bike_crashes.sum()),
            "generated_at": datetime.now(timezone.utc).date().isoformat(),
            "headline": "Велодорожки и ДТП: что показывают данные Москвы",
            "findings_title": "Основные результаты",
            "summary": f"Сравниваем ДТП с велосипедистами в {pre} и {post} годах на территориях "
            "с нынешними велодорожками и без них. Отдельно оцениваем изменения на соседних улицах.",
        },
        "models": models,
        "trends": trends,
        "map": map_data(panel, years),
        "group_means": records(FINAL / "group_means.csv"),
        "history_summary": history,
        "history_rows": records(OUT / "history/lane_history.csv"),
        "analysis_notes": notes,
        "conclusions": [
            {
                "title": "Абсолютное изменение",
                "text": f'Городской DiD: {number(global_did["estimate"], signed=True)} ДТП на ячейку относительно контроля. '
                f'Локальный DiD: {number(local_did["estimate"], signed=True)}, p = {number(local_did["p_value"])}. '
                "Даты открытия неизвестны, поэтому эти оценки не выделяют эффект строительства.",
            },
            {
                "title": "Относительное изменение",
                "text": f'Локальная пуассоновская модель даёт оценку {number(local_ppml["estimate"], 0, True)}%. '
                f'Её 95%-й интервал — от {number(local_ppml["ci_low"], 0, True)}% '
                f'до {number(local_ppml["ci_high"], 0, True)}%. '
                + (
                    "Интервал включает ноль: данные не позволяют уверенно определить знак изменения."
                    if local_ppml["ci_low"] <= 0 <= local_ppml["ci_high"]
                    else "Интервал не включает ноль; ограничения исторической разметки сохраняются."
                ),
            },
            {
                "title": "Соседние территории",
                "text": (
                    neighbor_finding
                    + "Проверить саму смену маршрутов по данным о ДТП нельзя: велопоток не наблюдается."
                ),
            },
        ],
        "limitations": [
            "Группы заданы по текущему слою велодорожек. Для большинства линий неизвестно, существовали ли они в 2015 и 2025 годах.",
            "Нет данных о числе велосипедных поездок. Поэтому считаем ДТП, но не риск одной поездки.",
            "В одном слое собраны уличные полосы, парковые дорожки и велопешеходные зоны. Условия движения на них различаются.",
            "Без дат открытия нельзя отделить годы до строительства от годов после него и проверить предшествующие тренды.",
            "Дороги взяты из текущей сети OSM. Её изменения и изменения регистрации ДТП могут влиять на результат. В 2016 и 2017 годах отсутствует январь; 2026 год исключён.",
            f"В локальном анализе соседей участвуют {local_core_n} из {int(base.treated_current.sum())} ячеек с велодорожками. "
            f'В удалённом контроле {int(remote.loc[pre, "crashes"])} ДТП в {pre} году '
            f'и {int(remote.loc[post, "crashes"])} в {post}-м. Суммы относятся к этой выборке.',
            "Интервал, пересекающий ноль, не доказывает отсутствие эффекта. Он показывает, что данных недостаточно, чтобы уверенно определить его знак.",
        ],
        "sources": [
            {
                "label": "OSM: дорожная сеть и граница Москвы",
                "url": "https://www.openstreetmap.org/copyright",
            },
            {
                "label": "Butts: DiD с пространственными spillovers",
                "url": "https://arxiv.org/abs/2105.03737",
            },
            {
                "label": "fixest: модели с фиксированными эффектами",
                "url": "https://lrberge.github.io/fixest/reference/feglm.html",
            },
        ],
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    # Escaping '<' prevents a source label from terminating the embedded script tag.
    encoded = encoded.replace("<", "\\u003c")
    template = (ROOT / "report/template.html").read_text()
    replacements = {
        "__REPORT_DATA__": encoded,
        "__REPORT_STYLE__": (ROOT / "report/style.css").read_text(),
        "__REPORT_SCRIPT__": (ROOT / "report/app.js").read_text(),
        "__NEIGHBOR_SAMPLE__": str(by_id["spillover_local_core"]["n_hex"]),
        "__NEIGHBOR_CORE__": str(local_core_n),
    }
    for marker, value in replacements.items():
        if template.count(marker) != 1:
            raise ValueError(f"Template must contain exactly one {marker} marker")
        template = template.replace(marker, value)
    (ROOT / "report.html").write_text(template)
    (FINAL / "report_data.json").write_text(encoded)
    saved = ROOT / "results"
    saved.mkdir(exist_ok=True)
    for name in [
        "models.csv",
        "group_means.csv",
        "trends.csv",
        "spillovers.csv",
        "spillover_totals.csv",
        "spillover_group_means.csv",
        "R_sessionInfo.txt",
        "analysis_notes.json",
    ]:
        shutil.copyfile(FINAL / name, saved / name)
    shutil.copyfile(OUT / "metadata.json", saved / "preprocessing_metadata.json")
    print(
        "Built report.html:", round((ROOT / "report.html").stat().st_size / 1024), "KB"
    )
    print(
        "Models:",
        len(models),
        "| mapped hexagons:",
        len(base),
        "| incomplete years:",
        incomplete,
    )


if __name__ == "__main__":
    main()
