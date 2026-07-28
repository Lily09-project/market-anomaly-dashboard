from __future__ import annotations

import pandas as pd

from src.utils import atomic_write_dataframe, write_json


def test_atomic_write_dataframe_replaces_existing_complete_file(tmp_path) -> None:
    path = tmp_path / "output.csv"
    atomic_write_dataframe(pd.DataFrame({"value": [1, 2]}), path)
    atomic_write_dataframe(pd.DataFrame({"value": [3, 4]}), path)

    written = pd.read_csv(path)
    assert written["value"].tolist() == [3, 4]
    assert list(tmp_path.glob(".output.csv.*.tmp")) == []


def test_write_json_replaces_existing_complete_file(tmp_path) -> None:
    path = tmp_path / "summary.json"
    write_json({"status": "old"}, path)
    write_json({"status": "new", "rows": 2}, path)

    assert path.read_text(encoding="utf-8") == '{\n  "status": "new",\n  "rows": 2\n}'
    assert list(tmp_path.glob(".summary.json.*.tmp")) == []
