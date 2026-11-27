"""Normalize the notification page's clock for display and chronological paging."""
from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo


def _absolute(text, now):
    # XHS shows month/day for recent notifications and includes the year on older rows.
    match = re.fullmatch(r"(\d{1,2})[-/月](\d{1,2})日?(.*)", text)
    if match:
        month, day, rest = match.groups()
        year = now.year - ((int(month), int(day)) > (now.month, now.day))
        text = f"{year:04}-{int(month):02}-{int(day):02}{rest}"
    text = text.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-")
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        return None
    value = value.astimezone(now.tzinfo) if value.tzinfo else value.replace(tzinfo=now.tzinfo)
    fmt = "%Y-%m-%d"
    if ":" in text:
        fmt += " %H:%M:%S" if re.search(r"\d{1,2}:\d{2}:\d{2}", text) else " %H:%M"
    return value, value.strftime(fmt)


def _relative(text, now):
    day = re.fullmatch(r"(今天|昨天|前天)(?:\s*(\d{1,2}:\d{2}(?::\d{2})?))?", text)
    if day:
        date = now.date() - timedelta(days={"今天": 0, "昨天": 1, "前天": 2}[day[1]])
        clock = day[2].split(":") if day[2] else []
        return _absolute(date.isoformat() + (" " + ":".join(part.zfill(2) for part in clock) if clock else ""), now)
    if text == "刚刚":
        text = "0分钟前"
    ago = re.fullmatch(r"(\d{1,5})\s*(秒|分钟|小时|天)前", text)
    if not ago:
        return None
    unit = ago[2]
    delta = timedelta(seconds=int(ago[1]) * {"秒": 1, "分钟": 60, "小时": 3600, "天": 86400}[unit])
    value = now - delta
    format_by_unit = {"秒": "%Y-%m-%d %H:%M:%S", "分钟": "%Y-%m-%d %H:%M", "小时": "%Y-%m-%d %H时", "天": "%Y-%m-%d"}
    return value, "约 " + value.strftime(format_by_unit[unit])


def platform_fields(item, observed):
    for key in ("time_absolute", "time_label"):
        raw = (item.get(key) or "").strip()
        if not raw:
            continue
        result = _absolute(raw, observed) or _relative(raw, observed)
        if result:
            value, label = result
            return {"platform_time": label, "platform_time_sort": int(value.timestamp())}
    return {}


def observation_time():
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def ordered_page(db, source, args, before, *, payload="item", tie="cursor"):
    # The secondary key disambiguates dates/times shared by many events. Unknowns sort last.
    clock = f"COALESCE(json_extract({payload}, '$.platform_time_sort'), -1)"
    condition = ""
    values = list(args)
    if before and str(before) != "0":
        match = re.fullmatch(r"(-?\d{1,12}):(\d{1,18})", str(before))
        if match:
            boundary = (int(match[1]), int(match[2]))
        elif str(before).isdigit() and len(str(before)) <= 18:
            old = db.execute("SELECT " + clock + source + f" AND {tie}=?", (*args, int(before))).fetchone()
            if not old:
                raise ValueError("消息游标已失效，请返回最新")
            boundary = (old[0], int(before))
        else:
            raise ValueError("消息游标无效")
        condition = f" AND ({clock}, {tie}) < (?, ?)"
        values.extend(boundary)
    rows = db.execute(f"SELECT *, {clock} AS sort_time" + source + condition +
                      f" ORDER BY sort_time DESC, {tie} DESC LIMIT 26", values).fetchall()
    cursor = f"{rows[24]['sort_time']}:{rows[24][tie]}" if len(rows) > 25 else None
    return rows[:25], cursor
