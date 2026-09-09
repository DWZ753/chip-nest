"""老版本库增量升级测试：冻结打包版无 alembic，用 PRAGMA+ALTER 补齐新列。

场景：v0.2.0 及更早安装包建库没有 manufacturer_part/supplier_part/zone_names，
升级后必须能无损读写（42 个老元件还在）。
"""

import sqlite3

from sqlalchemy import create_engine

from app.db import upgrade_legacy_columns

_OLD_DDL = """
CREATE TABLE components (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(64) NOT NULL,
    value VARCHAR(32),
    package VARCHAR(32),
    quantity INTEGER NOT NULL DEFAULT 0,
    threshold INTEGER NOT NULL DEFAULT 5,
    zone INTEGER NOT NULL,
    layer INTEGER NOT NULL,
    slot INTEGER NOT NULL,
    led_index INTEGER,
    search_text VARCHAR(256) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
CREATE TABLE layout_configs (
    id INTEGER PRIMARY KEY,
    zone_count INTEGER NOT NULL,
    layer_count INTEGER NOT NULL,
    row_count INTEGER NOT NULL,
    col_count INTEGER NOT NULL,
    updated_at DATETIME NOT NULL
);
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts DATETIME NOT NULL,
    kind VARCHAR(16) NOT NULL,
    component_id INTEGER,
    delta INTEGER NOT NULL,
    detail TEXT,
    source VARCHAR(16)
);
"""


def _make_old_db(path) -> None:
    con = sqlite3.connect(path)
    con.executescript(_OLD_DDL)
    con.execute(
        "INSERT INTO components (name, quantity, zone, layer, slot, search_text,"
        " created_at, updated_at) VALUES ('老电阻', 5, 1, 1, 0, 'lao',"
        " '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
    )
    con.execute(
        "INSERT INTO layout_configs (id, zone_count, layer_count, row_count,"
        " col_count, updated_at) VALUES (1, 1, 3, 1, 4, '2026-01-01 00:00:00')"
    )
    con.commit()
    con.close()


def _cols(con, table: str) -> set[str]:
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}


def test_legacy_db_upgrade_is_idempotent_and_preserves_rows(tmp_path):
    path = str(tmp_path / "old.db")
    _make_old_db(path)
    engine = create_engine(f"sqlite:///{path}")

    with engine.begin() as conn:
        upgrade_legacy_columns(conn)
        upgrade_legacy_columns(conn)  # 幂等：第二遍不报错

    con = sqlite3.connect(path)
    assert {"manufacturer_part", "supplier_part", "tags", "display_tags"} <= _cols(con, "components")
    assert "zone_names" in _cols(con, "layout_configs")
    # 老数据无损、默认值可用
    row = con.execute("SELECT name, quantity FROM components").fetchone()
    assert row == ("老电阻", 5)
    con.execute(
        "INSERT INTO layout_configs (id, zone_count, layer_count, row_count,"
        " col_count, updated_at) VALUES (2, 1, 1, 1, 1, '2026-01-01 00:00:00')"
    )
    con.commit()
    con.close()