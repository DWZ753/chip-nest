"""一次性备份：把用户当前的 ChipNest 库做一致性快照 + JSON 导出。"""
import datetime as dt
import hashlib
import json
import os
import sqlite3
from pathlib import Path

SRC = Path(os.environ["APPDATA"]) / "ChipNest" / "chipnest.db"
stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
TARGETS = [
    SRC.parent / "backups" / f"chipnest-{stamp}.db",
    Path(r"E:/esp32/chipnest-backups") / f"chipnest-{stamp}.db",
]


def snapshot(dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{SRC.as_posix()}?mode=ro", uri=True)
    try:
        out = sqlite3.connect(dst)
        try:
            src.backup(out)          # 连 WAL 里未落盘的数据一起快照
            out.commit()
        finally:
            out.close()
    finally:
        src.close()


def dump_json(db: Path, dst: Path) -> dict:
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    payload: dict = {"exported_at": dt.datetime.now().isoformat(timespec="seconds"),
                     "source": str(SRC)}
    counts = {}
    for table in ("components", "component_slots", "layout_configs",
                  "transactions", "lookup_cache"):
        try:
            rows = [dict(r) for r in con.execute(f"SELECT * FROM {table}")]
        except sqlite3.OperationalError:
            rows = []
        payload[table] = rows
        counts[table] = len(rows)
    con.close()
    dst.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return counts


def main() -> None:
    print("源库:", SRC, f"({SRC.stat().st_size} 字节)")
    first = None
    for dst in TARGETS:
        snapshot(dst)
        digest = hashlib.sha256(dst.read_bytes()).hexdigest()
        counts = dump_json(dst, dst.with_suffix(".json"))
        if first is None:
            first = counts
        print(f"备份 -> {dst}  ({dst.stat().st_size} 字节, sha256 {digest[:16]}…)")
        print("   条数:", counts)

    con = sqlite3.connect(f"file:{TARGETS[0].as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT zone, layer, slot, name, value, package, quantity, threshold "
        "FROM components ORDER BY zone, layer, slot"
    ).fetchall()
    print(f"\n元件 {len(rows)} 个：")
    for r in rows[:12]:
        print(f"   {r['zone']}区/{r['layer']}层/{r['slot']}格  {r['name']}"
              f"  {r['value'] or ''} {r['package'] or ''}  ×{r['quantity']} 阈值{r['threshold']}")
    if len(rows) > 12:
        print(f"   …另有 {len(rows) - 12} 个")
    layout = con.execute("SELECT * FROM layout_configs").fetchall()
    for l in layout:
        print("\n布局:", dict(l))
    con.close()


main()
