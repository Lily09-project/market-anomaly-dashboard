from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_pages_under_test", ROOT / "scripts/build_pages.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


@pytest.mark.parametrize("value", ["inf", "-inf", "Infinity", "1e999", "invalid"])
def test_public_numbers_fail_closed(value):
    with pytest.raises(ValueError):
        builder.number(value)


@pytest.mark.parametrize("value", ["", "nan", "None", "null", None])
def test_missing_numbers_are_null_not_zero(value):
    assert builder.number(value) is None


def test_number_precision():
    assert math.isclose(builder.number("0.123456"), 0.123456)


def test_public_input_cannot_escape_root(tmp_path):
    with pytest.raises(ValueError):
        builder.safe_path(tmp_path, "../outside.txt")


def test_csv_only_exports_allowlisted_columns(tmp_path):
    (tmp_path / "public.csv").write_text("player_id,score,secret\n0000000001,1.25,PRIVATE\n", encoding="utf-8")
    rows = builder.read_rows(tmp_path, "public.csv", [("player_id", "ID", "text"), ("score", "Score", "number")])
    assert rows == [{"player_id": "0000000001", "score": 1.25}]
    assert "PRIVATE" not in json.dumps(rows)


def test_missing_required_public_column_fails(tmp_path):
    (tmp_path / "public.csv").write_text("other\n1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing required"):
        builder.read_rows(tmp_path, "public.csv", [("required", "Required", "text")])


def test_duplicate_public_identity_fails(tmp_path):
    (tmp_path / "public.csv").write_text("id,score\nA,1\nA,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        builder.dataset(tmp_path, "test", "Test", "public.csv",
                        [("id", "ID", "text"), ("score", "Score", "number")],
                        identity=["id"], group="id", group_label="ID", value="score", date=None, chart_label="Score")


def test_invalid_date_fails(tmp_path):
    (tmp_path / "public.csv").write_text("date\nnot-a-date\n", encoding="utf-8")
    with pytest.raises(ValueError):
        builder.read_rows(tmp_path, "public.csv", [("date", "Date", "date")])


def test_oversized_input_rejected(tmp_path, monkeypatch):
    (tmp_path / "public.csv").write_text("id\nA\n", encoding="utf-8")
    monkeypatch.setattr(builder, "MAX_FILE_BYTES", 1)
    with pytest.raises(ValueError, match="oversized"):
        builder.safe_path(tmp_path, "public.csv")


def test_output_never_publishes_unexpected_files(tmp_path):
    (tmp_path / "pages-dist").mkdir()
    (tmp_path / "pages-dist" / ".env").write_text("PRIVATE", encoding="utf-8")
    with pytest.raises(ValueError, match="Unexpected"):
        builder.write_release(tmp_path, {"schema_version": "pages-data/1", "datasets": [{"fields": [{"key": "a"}], "group": "a", "value": "a", "identity": ["a"], "date": None, "rows": [{"a": 1}]}]})


def test_release_uses_explicit_asset_inventory(tmp_path):
    (tmp_path / "web").mkdir()
    for name in builder.ASSETS:
        (tmp_path / "web" / name).write_text("asset " + name, encoding="utf-8")
    (tmp_path / "web" / ".env").write_text("PRIVATE", encoding="utf-8")
    payload = {"schema_version": "pages-data/1", "datasets": [{"fields": [{"key": "a"}], "group": "a", "value": "a", "identity": ["a"], "date": None, "rows": [{"a": 1}]}]}
    out = builder.write_release(tmp_path, payload)
    assert {path.name for path in out.iterdir()} == builder.OUTPUT_FILES
    text = (out / "data.json").read_text(encoding="utf-8")
    manifest = json.loads((out / "integrity.json").read_text(encoding="utf-8"))
    assert manifest["data_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert "PRIVATE" not in text


def test_static_assets_do_not_use_remote_scripts_or_html_injection():
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    js = (ROOT / "web/app.js").read_text(encoding="utf-8")
    assert "Content-Security-Policy" in html
    assert "script-src 'self'" in html
    assert "innerHTML" not in js
    assert "eval(" not in js
    assert "textContent" in js
    assert "crypto.subtle.digest" in js
    assert "URL.revokeObjectURL" in js


def test_deploy_job_is_main_only_and_has_minimal_permissions():
    text = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
    assert "github.ref == 'refs/heads/main'" in text
    assert "github.event_name != 'pull_request'" in text
    assert "pages: write" in text and "id-token: write" in text
    assert "path: pages-dist" in text
    assert "pull_request_target" not in text
    assert "continue-on-error" not in text


def test_cloud_build_uses_explicit_constraints():
    text = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
    assert "-c requirements-dev.lock.txt" in text
