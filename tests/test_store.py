import pandas as pd

from vnsignal.store import read_csv, read_json, upsert_csv, write_json


def bars(rows):
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])


def test_upsert_creates_sorted_file(tmp_path):
    path = tmp_path / "X.csv"
    added, changed = upsert_csv(path, bars([("2024-01-03", 1, 1, 1, 1, 10), ("2024-01-02", 2, 2, 2, 2, 20)]))
    assert (added, changed) == (2, 0)
    assert list(read_csv(path)["date"]) == ["2024-01-02", "2024-01-03"]


def test_upsert_no_duplicate_and_overwrites(tmp_path):
    path = tmp_path / "X.csv"
    upsert_csv(path, bars([("2024-01-02", 2, 2, 2, 2, 20), ("2024-01-03", 1, 1, 1, 1, 10)]))
    added, changed = upsert_csv(path, bars([("2024-01-03", 5, 5, 5, 5, 50), ("2024-01-04", 3, 3, 3, 3, 30)]))
    df = read_csv(path)
    assert (added, changed) == (1, 1)
    assert list(df["date"]) == ["2024-01-02", "2024-01-03", "2024-01-04"]
    assert df["date"].is_unique
    assert df.loc[df["date"] == "2024-01-03", "close"].item() == 5


def test_upsert_same_data_is_noop(tmp_path):
    path = tmp_path / "X.csv"
    data = bars([("2024-01-02", 2, 2, 2, 2, 20), ("2024-01-03", 1, 1, 1, 1, 10)])
    upsert_csv(path, data)
    mtime, content = path.stat().st_mtime_ns, path.read_bytes()
    assert upsert_csv(path, data) == (0, 0)
    assert path.stat().st_mtime_ns == mtime
    assert path.read_bytes() == content


def test_upsert_dedupes_input(tmp_path):
    path = tmp_path / "X.csv"
    upsert_csv(path, bars([("2024-01-02", 1, 1, 1, 1, 10), ("2024-01-02", 2, 2, 2, 2, 20)]))
    df = read_csv(path)
    assert len(df) == 1 and df["close"].item() == 2


def test_write_json_skips_when_only_ignored_keys_change(tmp_path):
    path = tmp_path / "X.json"
    assert write_json(path, {"a": 1, "fetched_at": "t1"}, ignore_keys=("fetched_at",))
    assert not write_json(path, {"a": 1, "fetched_at": "t2"}, ignore_keys=("fetched_at",))
    assert read_json(path)["fetched_at"] == "t1"
    assert write_json(path, {"a": 2, "fetched_at": "t3"}, ignore_keys=("fetched_at",))
    assert read_json(path) == {"a": 2, "fetched_at": "t3"}
