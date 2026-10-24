from __future__ import annotations

from pathlib import Path

import run_all


def _patch(monkeypatch, calls: list[str], config: dict) -> None:
    monkeypatch.setattr(run_all, "load_config", lambda: config)
    monkeypatch.setattr(run_all, "ensure_project_dirs", lambda _config: None)
    monkeypatch.setattr(run_all, "generate_sample_data", lambda _config: calls.append("sample"))
    monkeypatch.setattr(run_all, "preprocess_data", lambda _config, mode, market_path: calls.append(f"preprocess:{mode}:{market_path}") or Path("clean.csv"))
    monkeypatch.setattr(run_all, "export", lambda target, cleaned_path: calls.append(f"export:{target.name}") or {"overview.json": "x"})


def test_sample_mode_never_calls_an_api(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    _patch(monkeypatch, calls, {"api": {"provider": "url"}})

    def forbidden(*args, **kwargs):
        raise AssertionError("sample mode must not fetch")

    monkeypatch.setattr(run_all, "fetch_market_data", forbidden)
    monkeypatch.setattr(run_all, "fetch_yfinance", forbidden)
    assert run_all.run("sample", out_dir=tmp_path / "out") == {"overview.json": "x"}
    assert calls == ["sample", "preprocess:sample:None", "export:out"]


def test_api_failure_falls_back_to_sample(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    _patch(monkeypatch, calls, {"api": {"provider": "url"}})
    monkeypatch.setattr(run_all, "fetch_market_data", lambda _config: None)
    run_all.run("api", out_dir=tmp_path / "out")
    assert calls == ["sample", "preprocess:sample:None", "export:out"]


def test_yfinance_provider_is_used_when_configured(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    _patch(monkeypatch, calls, {"api": {"provider": "yfinance", "symbols": ["2330"]}})
    monkeypatch.setattr(run_all, "fetch_yfinance", lambda _config, symbols: calls.append(f"yf:{symbols}") or Path("raw.csv"))
    run_all.run("api", out_dir=tmp_path / "out")
    assert calls == ["yf:['2330']", "preprocess:api:raw.csv", "export:out"]


def test_cli_parses_the_mode(monkeypatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(run_all, "run", lambda mode: seen.append(mode))
    monkeypatch.setattr("sys.argv", ["run_all.py", "--mode", "api"])
    run_all.main()
    assert seen == ["api"]
