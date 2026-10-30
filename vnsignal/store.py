"""Đọc/ghi file data idempotent: CSV upsert theo khoá, JSON chỉ ghi khi đổi nội dung."""

import json
from pathlib import Path

import pandas as pd


def read_csv(path: Path, key: str = "date") -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, dtype={key: str})


def upsert_csv(path: Path, new: pd.DataFrame, key: str = "date") -> tuple[int, int]:
    """Gộp `new` vào file theo `key`: dòng mới thêm vào, dòng trùng key bị ghi đè
    bằng bản mới, không bao giờ duplicate, luôn sort theo key.

    Trả về (số dòng thêm, số dòng thay đổi). Không ghi file nếu cả hai = 0.
    """
    old = read_csv(path, key)
    if new.empty:
        return 0, 0
    new = new.drop_duplicates(key, keep="last").copy()
    new[key] = new[key].astype(str)

    if old.empty:
        added, changed = len(new), 0
        merged = new
    else:
        old_idx = old.set_index(key)
        new_idx = new.set_index(key)[old_idx.columns]
        common = new_idx.index.intersection(old_idx.index)
        added = len(new_idx.index.difference(old_idx.index))
        diff = (old_idx.loc[common] != new_idx.loc[common]).any(axis=1)
        changed = int(diff.sum())
        merged = pd.concat([old_idx.drop(common), new_idx]).reset_index()

    if added == 0 and changed == 0:
        return 0, 0
    merged = merged.sort_values(key).reset_index(drop=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(path, index=False, lineterminator="\n")
    return added, changed


def read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict, ignore_keys: tuple[str, ...] = ()) -> bool:
    """Ghi JSON (sort key, UTF-8). Bỏ qua nếu nội dung — trừ `ignore_keys` — không đổi.
    Trả về True nếu đã ghi."""
    old = read_json(path)
    if old is not None:
        strip = lambda d: {k: v for k, v in d.items() if k not in ignore_keys}  # noqa: E731
        if strip(old) == strip(json.loads(json.dumps(data))):
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    return True
