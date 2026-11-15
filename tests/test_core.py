"""Unit tests for the pure (no Earth Engine) logic. Run:  python -m pytest -q"""
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ghostlakes import archive, common, infill, radar, terrain  # noqa: E402


# ---------------------------------------------------------------- radar rule
@pytest.mark.parametrize("before,after,ok", [
    (-21.0, -16.0, True),     # dark water -> 5 dB brighter
    (-17.0, -14.0, True),     # exactly on both thresholds
    (-16.9, -10.0, False),    # 'before' too bright to be open water
    (-21.0, -18.5, False),    # only +2.5 dB
    (-21.9, -23.2, False),    # still water (the rejected Abidjan site)
    (None, -10.0, False),     # missing radar data never confirms
    (-20.0, None, False),
])
def test_radar_rule(before, after, ok):
    assert radar.is_confirmed(before, after) is ok


# ---------------------------------------------------------------- optical dating
def test_change_months_basic():
    s = [("2025-01", 0.9), ("2025-02", 0.8), ("2025-03", 0.4), ("2025-04", 0.1), ("2025-05", 0.05)]
    assert infill.change_months(s) == ("2025-02", "2025-04")


def test_change_months_skips_clouds():
    assert infill.change_months([("2025-01", 0.9), ("2025-02", None), ("2025-03", None), ("2025-04", 0.1)]) \
        == ("2025-01", "2025-04")


def test_change_months_uses_last_wet_month():
    # land, water again, then land: the fill is the LAST transition
    assert infill.change_months([("2024-01", 0.9), ("2024-02", 0.1), ("2024-03", 0.9), ("2024-04", 0.1)]) \
        == ("2024-03", "2024-04")


def test_change_months_never_land():
    assert infill.change_months([("2024-01", 0.9), ("2024-02", 0.7)]) == ("2024-02", None)


# ---------------------------------------------------------------- radar dating
def test_radar_change_detects_persistent_step():
    s = [("2023-02-01", -21.0), ("2023-03-01", -20.0), ("2023-04-01", -21.5),
         ("2024-01-01", -20.5), ("2024-02-01", -15.0), ("2024-03-01", -14.0),
         ("2024-04-01", -15.5), ("2024-05-01", -14.5)]
    r = radar.change_date(s)
    assert r["base_db"] == -21.0
    assert r["radar_land_from"] == "2024-02-01"
    assert r["radar_last_water"] == "2024-01-01"


def test_radar_change_ignores_single_bright_spike():
    s = [("2023-02-01", -21.0), ("2023-03-01", -21.0), ("2024-01-01", -14.0),  # a boat
         ("2024-02-01", -21.0), ("2024-03-01", -20.5), ("2024-04-01", -21.0)]
    assert radar.change_date(s)["radar_land_from"] is None


def test_radar_change_no_baseline():
    assert radar.change_date([("2024-01-01", -15.0)]) is None


# ---------------------------------------------------------------- validation metric
def test_auc_vs():
    base = np.array([0.1, 0.2, 0.3, 0.4])
    assert terrain.auc_vs(base, np.array([0.5])) == 1.0
    assert terrain.auc_vs(base, np.array([0.0])) == 0.0
    assert terrain.auc_vs(base, np.array([0.3])) == pytest.approx(0.625)   # 2 below + half a tie
    assert terrain.auc_vs(base, np.array([])) is None


# ---------------------------------------------------------------- geometry
def test_to_px_corners():
    b = [-4.0, 5.0, -3.0, 6.0]
    assert common.to_px(-4.0, 6.0, b, (100, 200)) == (0.0, 0.0)          # top-left
    assert common.to_px(-3.0, 5.0, b, (100, 200)) == (100.0, 200.0)      # bottom-right


# ---------------------------------------------------------------- summary tables
def _patch(lat, lon, area, **props):
    return {"type": "Feature", "geometry": None, "properties": {"lat": lat, "lon": lon, "area_ha": area, **props}}


def test_screen_csv_covers_every_city(tmp_path):
    for name, feats in {"a": [_patch(1, 2, 3.0, vv_before=-20, vv_after=-15)],
                        "b": [_patch(4, 5, 1.0, vv_before=-20, vv_after=-19)]}.items():
        (tmp_path / f"{name}.geojson").write_text(json.dumps({"features": feats}))
    rows = infill.write_screen_csv(str(tmp_path))
    assert {r[0] for r in rows} == {"a", "b"}
    assert [r[6] for r in sorted(rows)] == [True, False]
    assert (tmp_path / "all.csv").read_text().count("\n") == 3      # header + 2 rows


def test_archive_summary_handles_missing_values(tmp_path):
    (tmp_path / "x.geojson").write_text(json.dumps({"features": [_patch(1.123456, 2.0, 2.04)]}))
    archive.write_summary(str(tmp_path))
    assert (tmp_path / "all_patches.csv").read_text().splitlines()[1] == "x,1.12346,2.0,2.0,None,None"


def test_screen_boxes_include_all_groups():
    b = infill.screen_boxes()
    assert {"abidjan", "lusaka", "manila", "ro_bucuresti"} <= set(b)
    assert all(len(v) == 4 and v[0] < v[2] and v[1] < v[3] for v in b.values())
