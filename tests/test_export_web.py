from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from run_all import run
from src import export_web
from src.analytics import risk

FILES = ("overview.json", "regimes.json", "events.json", "backtest.json", "stress.json", "provenance.json")


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("web-data")
    run("sample", out_dir=out)
    return out


def _load(path: Path, name: str):
    return json.loads((path / name).read_text(encoding="utf-8"))


def test_pipeline_is_byte_for_byte_reproducible(exported: Path, tmp_path: Path) -> None:
    run("sample", out_dir=tmp_path)
    for name in (*FILES, "manifest.json"):
        assert (exported / name).read_bytes() == (tmp_path / name).read_bytes(), name


def test_manifest_hashes_match(exported: Path) -> None:
    manifest = _load(exported, "manifest.json")
    assert manifest["schema_version"] == export_web.SCHEMA_VERSION
    assert set(manifest["files"]) == set(FILES)
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((exported / name).read_bytes()).hexdigest() == digest


def test_overview_has_aligned_series(exported: Path) -> None:
    overview = _load(exported, "overview.json")
    assert len(overview["symbols"]) == 4
    for s in overview["symbols"]:
        assert len(s["close"]) == len(overview["dates"])
        assert s["cvar95_daily"] >= s["var95_daily"]
    assert [s["is_control"] for s in overview["symbols"]].count(True) == 1


def test_regimes_recover_the_truth_and_flag_the_control(exported: Path) -> None:
    payload = _load(exported, "regimes.json")["symbols"]
    for symbol, regime in payload.items():
        assert all(abs(sum(row) - 1) < 1e-3 for row in regime["transition"])
        assert regime["vol_annual"] == sorted(regime["vol_annual"])
        assert regime["segments"][0][0] == 0
        if symbol == "RANDOM":
            assert regime["accuracy"] is None
            assert regime["bic_choice"] == 1  # no evidence of regimes in a random walk
        else:
            assert regime["accuracy"] >= 0.8
            assert sum(map(sum, regime["confusion"])) == regime["segments"][-1][1] + 1


def test_event_study_finds_the_injected_rebound(exported: Path) -> None:
    payload = _load(exported, "events.json")
    validation = payload["validation"]
    assert validation["recall"] >= 0.7 and validation["precision"] >= 0.8
    negative = payload["study"]["negative"]
    assert negative["post_low"][2] > 0  # CAR(+1..+3) after negative shocks is significantly positive
    positive = payload["study"]["positive"]
    assert positive["post_low"][2] <= 0 <= positive["post_high"][2]
    assert payload["control_events"] == 0


def test_backtest_reports_overfitting_metrics(exported: Path) -> None:
    payload = _load(exported, "backtest.json")["symbols"]
    for result in payload.values():
        n = len(result["grid"])
        assert len(result["is_sharpe"]) == len(result["oos_sharpe"]) == n
        assert 0 <= result["pbo"] <= 1
        assert 0 <= result["dsr"]["dsr"] <= 1
        assert result["causal_check"] == "passed"
        folds = result["walk_forward"]
        assert all(a["test_end"] < b["test_start"] or a["test_end"] <= b["test_start"] for a, b in zip(folds, folds[1:]))
        assert all(f["train_start"] < f["test_start"] for f in folds)


def test_stress_parity_cases_reproduce(exported: Path) -> None:
    overview = _load(exported, "overview.json")
    closes = {s["symbol"]: s["close"] for s in overview["symbols"]}
    for case in _load(exported, "stress.json")["parity"]:
        import numpy as np

        returns = np.diff(np.log(np.array(closes[case["symbol"]])))
        summary = risk.summarise(risk.block_bootstrap(returns, case["horizon"], case["block"], case["paths"], case["seed"]))
        assert summary["var95"] == pytest.approx(case["var95"], abs=1e-12)
        assert summary["cvar99"] == pytest.approx(case["cvar99"], abs=1e-12)


def test_finmind_source_quality_requires_matching_real_source_metadata(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw_path = raw_dir / "market_finmind.csv"
    raw_path.write_text("date,symbol,close\\n2026-01-02,2330,100\\n", encoding="utf-8")
    digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    metadata_path = tmp_path / "source_metadata.json"
    metadata_path.write_text(json.dumps({
        "provider": "finmind", "status": "success", "data_source": "API Data",
        "is_simulated_data": False, "row_count": 1, "source_row_count": 2,
        "excluded_no_trade_rows": 1, "data_file_sha256": digest,
    }), encoding="utf-8")
    config = {"data": {"raw_dir": raw_dir, "source_metadata_path": metadata_path}}
    assert export_web._finmind_source_quality(config, "finmind", False) == {
        "source_row_count": 2, "usable_price_rows": 1, "excluded_no_trade_rows": 1,
    }
    raw_path.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        export_web._finmind_source_quality(config, "finmind", False)


def test_provenance_marks_simulated_data(exported: Path) -> None:
    provenance = _load(exported, "provenance.json")
    assert provenance["is_simulated"] is True
    assert provenance["source_quality"] is None
    assert provenance["truth"] == {"regimes": True, "injected_events": True}
    assert "不構成任何投資建議" in provenance["disclaimer"]


def test_short_history_fails_clearly(exported: Path, tmp_path: Path) -> None:
    from src.utils import load_config, project_path

    cleaned = pd.read_csv(project_path(load_config()["data"]["cleaned_path"]), dtype={"symbol": "string"})
    short = cleaned[cleaned["date"] >= "2025-06-01"]
    path = tmp_path / "short.csv"
    short.to_csv(path, index=False)
    with pytest.raises(export_web.InsufficientHistoryError):
        export_web.export(tmp_path / "out", cleaned_path=path)


def test_cli_writes_to_the_requested_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.argv", ["export_web", "--out", str(tmp_path / "cli")])
    export_web.main()
    assert (tmp_path / "cli" / "manifest.json").exists()
    assert "overview.json" in capsys.readouterr().out


def stress_fixture(exported: Path) -> dict:
    """What web/src/lib/fixtures/stress-parity.json must contain."""
    closes = {s["symbol"]: s["close"] for s in _load(exported, "overview.json")["symbols"]}
    parity = _load(exported, "stress.json")["parity"]
    return {"closes": {symbol: closes[symbol] for symbol in sorted({c["symbol"] for c in parity})}, "parity": parity}


def test_web_stress_fixture_matches_the_export(exported: Path) -> None:
    """The Vitest parity test reads this fixture; regenerate it when the export changes."""
    fixture = Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "fixtures" / "stress-parity.json"
    assert json.loads(fixture.read_text(encoding="utf-8")) == stress_fixture(exported), (
        "stale fixture: run `python -c \"from tests.test_export_web import write_stress_fixture; write_stress_fixture()\"`"
    )


def write_stress_fixture() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = stress_fixture(root / "web" / "public" / "data")
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    (root / "web" / "src" / "lib" / "fixtures" / "stress-parity.json").write_text(text + "\n", encoding="utf-8", newline="\n")
