"""On-demand complete script output, confined to the owning job and profile."""
from pathlib import Path
import re

from fastapi import HTTPException


def read_output(job_id, filename, profile=None):
    from . import cron
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.md", filename):
        raise HTTPException(status_code=400, detail="无效的运行记录文件名")
    selected = cron._job_profile(job_id, profile)
    job = cron._found(cron._call_cron_for_profile(selected, "get_job", job_id))
    _, home = cron._cron_profile_home(selected)
    base = Path(home) / "cron" / "output"
    directory = base / job["id"]
    path = directory / filename
    if directory.is_symlink() or directory.resolve().parent != base.resolve() or path.is_symlink():
        raise HTTPException(status_code=404, detail="运行记录不存在")
    try:
        output = path.read_text(encoding="utf-8-sig", errors="replace")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="运行记录不存在或已清理") from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="暂时无法读取运行记录") from exc
    return {"output": output, "profile": selected, "job_id": job["id"]}
