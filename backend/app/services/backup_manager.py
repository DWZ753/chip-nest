"""本机备份策略、历史与运行期间的周期备份。"""
import asyncio
import datetime as dt
from pathlib import Path
import re
import tempfile

from fastapi import HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app import config, schemas
from app.models import BackupPreference, Transaction, utcnow


async def settings(session: AsyncSession) -> schemas.BackupSettingsOut:
    """@brief 读取本机策略；未设置时使用每日备份和 14 份保留。"""
    row = await session.get(BackupPreference, 1)
    values = schemas.BackupSettings().model_dump()
    if row is not None:
        values.update({key: getattr(row, key) for key in values})
    directory = Path(values["directory"] or config.backup_dir()).resolve()
    return schemas.BackupSettingsOut(
        **values, resolved_directory=str(directory),
        last_backup_at=row.last_backup_at if row else None,
        last_error=row.last_error if row else "",
    )


async def save_settings(
    session: AsyncSession, body: schemas.BackupSettings,
) -> schemas.BackupSettingsOut:
    """@brief 验证目录可写后保存策略，失败时保留旧设置。"""
    directory = Path(body.directory) if body.directory else config.backup_dir()
    if body.directory and not directory.is_absolute():
        raise HTTPException(status_code=422, detail="备份目录必须是完整路径")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=directory) as probe:
            probe.write(b"ChipNest")
            probe.flush()
    except OSError as exc:
        raise HTTPException(status_code=422, detail="备份目录不可写") from exc
    row = await session.get(BackupPreference, 1)
    if row is None:
        row = BackupPreference(id=1)
        session.add(row)
    values = body.model_dump()
    values["directory"] = str(directory.resolve()) if body.directory else ""
    for key, value in values.items():
        setattr(row, key, value)
    row.last_error = ""
    session.add(Transaction(
        kind="backup", delta=0, source="ui", detail="已更新备份策略",
    ))
    await session.commit()
    return await settings(session)


def read_file(directory: Path, name: str) -> schemas.BackupSnapshot:
    """@brief 只读取指定目录内由应用命名的有效备份。"""
    if not re.fullmatch(r"chipnest-backup-[\d-]+\.json", name):
        raise HTTPException(status_code=422, detail="备份文件名无效")
    path = directory / name
    if path.is_symlink() or path.resolve().parent != directory.resolve():
        raise HTTPException(status_code=422, detail="备份文件无效")
    try:
        return schemas.BackupSnapshot.model_validate_json(
            path.read_text(encoding="utf-8"),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="备份不存在") from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="备份文件无效") from exc


def history(directory: Path) -> list[schemas.BackupFileOut]:
    """@brief 列出有效备份，不把临时文件或其他 JSON 当作备份。"""
    result = []
    snapshot = None
    for path in directory.glob("chipnest-backup-*.json"):
        try:
            snapshot = read_file(directory, path.name)
            result.append(schemas.BackupFileOut(
                name=path.name, exported_at=snapshot.exported_at,
                reason=snapshot.reason, size=path.stat().st_size,
                components=len(snapshot.components),
                projects=len(snapshot.projects),
            ))
        except (HTTPException, OSError):
            continue
    return sorted(result, key=lambda item: (item.exported_at, item.name),
                  reverse=True)


def prune_automatic(directory: Path, keep_count: int) -> None:
    """@brief 只移除超出保留数量的周期备份。"""
    automatic = [item for item in history(directory) if item.reason == "auto"]
    for item in automatic[keep_count:]:
        (directory / item.name).unlink(missing_ok=True)


async def run_due(session: AsyncSession) -> bool:
    """@brief 到期时创建备份；写入失败不推进成功时间。"""
    from app.routers.system import create_snapshot

    option = await settings(session)
    if not option.enabled:
        return False
    if (option.last_backup_at is not None
            and utcnow() - option.last_backup_at
            < dt.timedelta(hours=option.interval_hours)):
        return False
    await session.rollback()
    await create_snapshot(session, "auto")
    prune_automatic(Path(option.resolved_directory), option.keep_count)
    return True


async def backup_loop() -> None:
    """@brief 应用运行期间检查周期，退出时由 lifespan 取消。"""
    from app.db import async_session

    row = None
    while True:
        async with async_session() as session:
            try:
                await run_due(session)
            except Exception as exc:
                logger.exception("周期备份失败")
                await session.rollback()
                row = await session.get(BackupPreference, 1)
                if row is None:
                    row = BackupPreference(id=1)
                    session.add(row)
                row.last_error = "自动备份失败"
                await session.commit()
        await asyncio.sleep(60)
