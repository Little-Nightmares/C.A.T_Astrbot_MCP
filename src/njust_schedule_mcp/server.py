"""MCP 服务器入口 - 注册所有工具，提供课表/成绩/考试查询功能"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from io import BytesIO
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.utilities.types import Image
from PIL import Image as PILImage, ImageDraw

from .cache import CacheManager
from .config import get_config, set_config
from .image_gen import render_schedule_to_png
from .portal.client import PortalClient, PortalError
from .portal.parsers import (
    ExamsParseResult,
    ExamItem,
    GradeItemParsed,
    GradesParseResult,
    LessonsParseResult,
    ScheduleOccurrence,
    format_exams_text,
    format_grades_text,
    format_schedule_text,
    format_section_time,
)

logger = logging.getLogger(__name__)

# ============================================================
# 初始化
# ============================================================

mcp = FastMCP(
    name="njust-schedule-mcp",
    instructions=(
        "NJUST 教务系统 MCP 服务器，提供课表查询、成绩查询、考试安排查询等功能。"
        "所有工具会自动处理登录和缓存。"
    ),
)

# 全局客户端和缓存
_client: PortalClient | None = None
_cache: CacheManager | None = None


def _get_client() -> PortalClient:
    """获取全局教务系统客户端"""
    global _client
    if _client is None:
        config = get_config()
        if not config.portal_username or not config.portal_password:
            raise PortalError(
                "请先通过 bind_account 工具绑定教务系统账号，或设置环境变量 PORTAL_USERNAME 和 PORTAL_PASSWORD",
                "NOT_CONFIGURED",
            )
        _client = PortalClient(
            username=config.portal_username,
            password=config.portal_password,
            cache_dir=config.cache_dir,
        )
    return _client


def _get_cache() -> CacheManager:
    """获取全局缓存管理器"""
    global _cache
    if _cache is None:
        config = get_config()
        _cache = CacheManager(
            cache_dir=config.cache_dir,
            default_ttl_minutes=config.cache_ttl_minutes,
        )
    return _cache


def _serialize_grades(items: list[GradeItemParsed]) -> list[dict]:
    """序列化成绩列表"""
    return [
        {
            "record_key": g.record_key,
            "term": g.term,
            "course_code": g.course_code,
            "course_name": g.course_name,
            "score": g.score,
            "score_numeric": g.score_numeric,
            "score_flag": g.score_flag,
            "credit": g.credit,
            "course_attribute": g.course_attribute,
        }
        for g in items
    ]


def _serialize_lessons(result: LessonsParseResult) -> dict:
    """序列化课表结果"""
    return {
        "term": result.term,
        "available_terms": result.available_terms,
        "entries": [
            {
                "course_code": e.course_code,
                "course_name": e.course_name,
                "teacher": e.teacher,
                "weekday": e.weekday,
                "weekday_label": e.weekday_label,
                "block_start": e.block_start,
                "block_end": e.block_end,
                "week_text": e.week_text,
                "week_numbers": e.week_numbers,
                "location": e.location,
                "credit": e.credit,
            }
            for e in result.entries
        ],
    }


def _serialize_exams(result: ExamsParseResult) -> list[dict]:
    """序列化考试安排"""
    return [
        {
            "course_name": e.course_name,
            "course_code": e.course_code,
            "exam_date": e.exam_date,
            "exam_time": e.exam_time,
            "location": e.location,
            "seat_number": e.seat_number,
            "exam_type": e.exam_type,
        }
        for e in result.items
    ]


# ============================================================
# MCP 工具定义
# ============================================================


@mcp.tool
def bind_account(
    username: Annotated[str, "教务系统学号"],
    password: Annotated[str, "教务系统密码"],
    semester_start_date: Annotated[str, "学期第一天日期（周一），格式 YYYY-MM-DD，如 2026-03-02"] = "",
) -> str:
    """
    绑定教务系统账号密码，并设置学期开始日期。绑定后会自动验证账号有效性。

    使用示例：bind_account(username="学号", password="密码", semester_start_date="2026-03-02")
    """
    global _client
    try:
        config = get_config()
        client = PortalClient(
            username=username,
            password=password,
            cache_dir=config.cache_dir,
        )
        # 验证账号
        result = client.login(username, password)
        _client = client

        # 设置学期开始日期
        msg = f"✅ 教务系统账号绑定成功！\n学号: {username}\n会话已建立，可以开始查询课表、成绩等信息。"
        if semester_start_date:
            os.environ["SEMESTER_START_DATE"] = semester_start_date
            # 刷新配置单例
            from .config import load_config
            set_config(load_config())
            msg += f"\n📅 学期开始日期已设为: {semester_start_date}"
        return msg
    except PortalError as e:
        return f"❌ 绑定失败: {e.message}"
    except Exception as e:
        logger.exception("绑定账号异常")
        return "❌ 绑定失败: 内部错误，请查看日志获取详细信息"


@mcp.tool
def query_schedule(
    term: Annotated[str, "学期，如 '2024-2025-2'，为空查当前学期"] = "",
) -> str:
    """
    查询指定学期的课表信息，返回格式化的课表文本。

    使用示例：query_schedule(term="2024-2025-2")
    """
    try:
        client = _get_client()
        cache = _get_cache()
        result = _get_cached_or_fetch_lessons(client, cache, term or None)
        return format_schedule_text(result)
    except PortalError as e:
        return f"❌ 查询失败: {e.message}"
    except Exception as e:
        logger.exception("查询课表异常")
        return "❌ 查询课表失败，请稍后重试"


def _get_cached_or_fetch_lessons(
    client: PortalClient,
    cache: CacheManager,
    term: str | None = None,
    ttl_hours: int | None = None,
) -> LessonsParseResult:
    """获取课表（优先缓存，过期则抓取）"""
    config = get_config()
    cache_key = f"schedule_{term or 'current'}"
    ttl = timedelta(hours=ttl_hours or config.schedule_cache_ttl_hours)

    cached = cache.get(cache_key, ttl=ttl)
    if cached:
        return LessonsParseResult(
            term=cached.get("term"),
            available_terms=cached.get("available_terms", []),
            entries=[_build_entry(e) for e in cached.get("entries", [])],
        )

    result = client.get_lessons(term)
    cache.set(cache_key, _serialize_lessons(result))
    return result


def _build_entry(e: dict) -> ScheduleOccurrence:
    """从字典构建 ScheduleOccurrence"""
    return ScheduleOccurrence(
        course_code=e.get("course_code"),
        class_no=e.get("class_no"),
        course_name=e.get("course_name", ""),
        teacher=e.get("teacher"),
        weekday=e.get("weekday", 1),
        weekday_label=e.get("weekday_label", ""),
        block_start=e.get("block_start", 1),
        block_end=e.get("block_end", 1),
        block_label_start=e.get("block_label_start", ""),
        block_label_end=e.get("block_label_end", ""),
        time_text=e.get("time_text", ""),
        week_text=e.get("week_text", ""),
        week_numbers=e.get("week_numbers", []),
        location=e.get("location"),
        credit=e.get("credit"),
        course_attribute=e.get("course_attribute"),
        selection_stage=e.get("selection_stage"),
    )


def _get_current_week() -> int | None:
    """根据学期开始日期计算当前周次，未配置则返回 None"""
    config = get_config()
    if not config.semester_start_date:
        logger.debug("未配置 SEMESTER_START_DATE，无法计算当前周次")
        return None
    try:
        start = datetime.strptime(config.semester_start_date, "%Y-%m-%d").date()
        today = datetime.now().date()
        week = max(1, (today - start).days // 7 + 1)
        logger.info("当前周次: 第 %d 周 (学期开始: %s)", week, config.semester_start_date)
        return week
    except ValueError:
        logger.warning("学期开始日期格式错误: %s", config.semester_start_date)
        return None


@mcp.tool
def query_today_schedule() -> str:
    """
    查询今天的课程安排。自动根据当前日期计算周次和星期。

    使用示例：query_today_schedule()
    """
    try:
        client = _get_client()
        cache = _get_cache()
        config = get_config()

        # 计算当前周次和星期
        now = datetime.now()
        weekday = now.isoweekday()  # 1=周一, 7=周日
        current_week = _get_current_week()

        # 获取课表
        result = _get_cached_or_fetch_lessons(client, cache)

        # 过滤今天的课程（同时按周次过滤）
        today_label = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"][weekday]
        today_entries = [
            e for e in result.entries
            if e.weekday == weekday
            and (current_week is None or current_week in e.week_numbers)
        ]

        if not today_entries:
            week_info = f"（第 {current_week} 周）" if current_week else ""
            return f"📅 今天是{today_label}{week_info}，没有课程 🎉"

        lines = [
            f"## 📅 今天是{today_label}的课程\n",
            f"学期: {result.term or '未知'}",
        ]
        if current_week:
            lines.append(f"**周次: 第 {current_week} 周**（以下为第 {current_week} 周今天的课程）\n")
        else:
            lines.append("")
        for entry in sorted(today_entries, key=lambda e: e.block_start):
            time_str = format_section_time(entry.block_start, entry.block_end)
            lines.append(
                f"### ⏰ {time_str}\n"
                f"**{entry.course_name}**\n"
                f"- 📍 地点: {entry.location or '待定'}\n"
                f"- 👨‍🏫 教师: {entry.teacher or '未知'}\n"
            )

        return "\n".join(lines)
    except PortalError as e:
        return f"❌ 查询失败: {e.message}"
    except Exception as e:
        logger.exception("查询今日课程异常")
        return "❌ 查询今日课程失败，请稍后重试"


@mcp.tool
def query_week_schedule(
    week: Annotated[int, "周次，0 或不传表示当前周，传入具体数字查指定周（如 8 查第 8 周）"] = 0,
) -> str:
    """
    查询指定周次的课程安排，按天分组显示。

    使用示例：
    - query_week_schedule()       # 查当前周
    - query_week_schedule(week=0) # 查当前周
    - query_week_schedule(week=8) # 查第 8 周
    """
    try:
        client = _get_client()
        cache = _get_cache()

        # 获取课表
        result = _get_cached_or_fetch_lessons(client, cache)

        # 确定查询周次
        if week == 0:
            current_week = _get_current_week()
            if current_week is None:
                return "⚠️ 未配置学期开始日期（SEMESTER_START_DATE），无法计算当前周次。请在 MCP 配置的 args 中添加 --semester-start-date YYYY-MM-DD，或通过 bind_account 工具绑定。"
            week = current_week

        return format_schedule_text(result, week=week)
    except PortalError as e:
        return f"❌ 查询失败: {e.message}"
    except Exception as e:
        logger.exception("查询本周课程异常")
        return "❌ 查询本周课程失败，请稍后重试"


@mcp.tool
def generate_schedule_image(
    week: Annotated[int, "周次，0 表示本周"] = 0,
) -> Image:
    """
    生成日历样式的周课表图片。返回 PNG 格式的图片，可以直接发送给用户。

    使用示例：generate_schedule_image(week=5)  # 生成第5周的课表图片
    """
    try:
        client = _get_client()
        cache = _get_cache()
        config = get_config()

        # 获取课表
        result = _get_cached_or_fetch_lessons(client, cache)

        # 如果 week=0，计算当前周次
        if week == 0:
            current_week = _get_current_week()
            if current_week is None:
                current_week = 1
            week = current_week

        term = result.term or "未知学期"
        png_bytes = render_schedule_to_png(
            entries=result.entries,
            week=week,
            term=term,
        )

        return Image(data=png_bytes, format="png")
    except PortalError as e:
        # 返回错误文本图片
        img = PILImage.new("RGB", (400, 100), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), f"生成失败: {e.message}", fill=(255, 0, 0))
        draw.text((10, 40), "请检查账号绑定状态", fill=(128, 128, 128))
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return Image(data=buffer.getvalue(), format="png")
    except Exception as e:
        logger.exception("生成课表图片异常")
        img = PILImage.new("RGB", (400, 100), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "生成失败，请查看日志", fill=(255, 0, 0))
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return Image(data=buffer.getvalue(), format="png")


@mcp.tool
def query_grades(
    term: Annotated[str, "学期，如 '2024-2025-2'，为空查全部学期"] = "",
) -> str:
    """
    查询成绩信息，返回格式化的成绩列表。

    使用示例：query_grades() 或 query_grades(term="2024-2025-2")
    """
    try:
        client = _get_client()
        cache = _get_cache()
        config = get_config()

        # 检查缓存
        cache_key = "grades"
        cached = cache.get(
            cache_key, ttl=timedelta(hours=config.grades_cache_ttl_hours)
        )
        if cached:
            items = [
                GradeItemParsed(
                    record_key=g["record_key"],
                    term=g["term"],
                    course_code=g.get("course_code"),
                    course_name=g["course_name"],
                    score=g.get("score"),
                    score_numeric=g.get("score_numeric"),
                    score_flag=g.get("score_flag"),
                    credit=g.get("credit"),
                    course_attribute=g.get("course_attribute"),
                )
                for g in cached
            ]
            result = GradesParseResult(items=items)
        else:
            result = client.get_grades()
            cache.set(cache_key, _serialize_grades(result.items))

        # 更新成绩快照（用于变更检测）
        cache.set_raw("grades_snapshot", _serialize_grades(result.items))

        return format_grades_text(result, term or None)
    except PortalError as e:
        return f"❌ 查询失败: {e.message}"
    except Exception as e:
        logger.exception("查询成绩异常")
        return "❌ 查询成绩失败，请稍后重试"


@mcp.tool
def query_exams(
    term: Annotated[str, "学期，如 '2024-2025-2'，为空查当前学期"] = "",
) -> str:
    """
    查询考试安排，返回格式化的考试列表。

    使用示例：query_exams() 或 query_exams(term="2024-2025-2")
    """
    try:
        client = _get_client()
        cache = _get_cache()
        config = get_config()

        # 检查缓存
        cache_key = "exams"
        cached = cache.get(
            cache_key, ttl=timedelta(hours=config.exams_cache_ttl_hours)
        )
        if cached:
            items = [
                ExamItem(
                    course_name=e["course_name"],
                    course_code=e.get("course_code"),
                    exam_date=e["exam_date"],
                    exam_time=e["exam_time"],
                    location=e.get("location"),
                    seat_number=e.get("seat_number"),
                    exam_type=e.get("exam_type"),
                )
                for e in cached
            ]
            result = ExamsParseResult(items=items)
        else:
            result = client.get_exams()
            cache.set(cache_key, _serialize_exams(result))

        return format_exams_text(result)
    except PortalError as e:
        return f"❌ 查询失败: {e.message}"
    except Exception as e:
        logger.exception("查询考试安排异常")
        return "❌ 查询考试安排失败，请稍后重试"


@mcp.tool
def check_grade_changes() -> str:
    """
    检查是否有新成绩或成绩变动。供 AstrBot 主动型 Agent 定时调用。

    对比上次查询的成绩快照，返回新增或变更的成绩记录。
    如果没有变动，返回"暂无新成绩"。

    使用示例：check_grade_changes()
    """
    try:
        client = _get_client()
        cache = _get_cache()

        # 加载上次快照
        old_data = cache.get_raw("grades_snapshot")
        old_map: dict[str, dict] = {}
        if old_data:
            for g in old_data:
                old_map[g["record_key"]] = g

        # 获取最新成绩（绕过缓存，确保获取最新数据）
        result = client.get_grades()
        new_items = result.items

        # 对比
        new_keys = {g.record_key for g in new_items}
        old_keys = set(old_map.keys())

        added_keys = new_keys - old_keys
        changed_items = []
        for g in new_items:
            if g.record_key in old_keys:
                old_score = old_map[g.record_key].get("score")
                if g.score != old_score:
                    changed_items.append(g)

        # 更新快照
        cache.set_raw("grades_snapshot", _serialize_grades(new_items))
        # 同时更新缓存
        cache.set("grades", _serialize_grades(new_items))

        if not added_keys and not changed_items:
            return "📊 暂无新成绩变动"

        lines = ["## 📊 成绩变动通知\n"]
        if added_keys:
            lines.append(f"### 🆕 新增成绩 ({len(added_keys)} 门)\n")
            for g in new_items:
                if g.record_key in added_keys:
                    score_display = g.score or "未出分"
                    lines.append(
                        f"- **{g.course_name}** ({g.term}): {score_display} | {g.credit or '-'} 学分"
                    )
            lines.append("")

        if changed_items:
            lines.append(f"### 📝 成绩变更 ({len(changed_items)} 门)\n")
            for g in changed_items:
                old_score = old_map[g.record_key].get("score", "未出分")
                lines.append(
                    f"- **{g.course_name}**: {old_score} → {g.score}"
                )
            lines.append("")

        return "\n".join(lines)
    except PortalError as e:
        return f"❌ 检查失败: {e.message}"
    except Exception as e:
        logger.exception("检查成绩变动异常")
        return "❌ 检查成绩变动失败，请稍后重试"


@mcp.tool
def check_upcoming_exams(
    days: Annotated[int, "提前多少天提醒"] = 7,
) -> str:
    """
    检查未来指定天数内的考试安排。供 AstrBot 主动型 Agent 定时调用。

    使用示例：check_upcoming_exams(days=7)  # 检查未来7天内的考试
    """
    try:
        client = _get_client()
        cache = _get_cache()
        config = get_config()

        # 获取考试安排（绕过缓存）
        result = client.get_exams()
        cache.set("exams", _serialize_exams(result))

        if not result.items:
            return "📝 暂无考试安排"

        # 尝试解析考试日期并过滤
        now = datetime.now()
        upcoming = []
        for exam in result.items:
            try:
                # 尝试解析日期格式（适配多种格式）
                exam_date_str = exam.exam_date.strip()
                # 常见格式: 2025-01-15, 2025年1月15日, 01/15
                for fmt in [
                    "%Y-%m-%d",
                    "%Y年%m月%d日",
                    "%Y/%m/%d",
                    "%m/%d",
                    "%m-%d",
                ]:
                    try:
                        exam_date = datetime.strptime(exam_date_str, fmt)
                        if fmt in ("%m/%d", "%m-%d"):
                            exam_date = exam_date.replace(year=now.year)
                        break
                    except ValueError:
                        continue
                else:
                    # 无法解析日期，包含在结果中
                    upcoming.append(exam)
                    continue

                delta = (exam_date - now).days
                if 0 <= delta <= days:
                    upcoming.append(exam)
            except Exception:
                upcoming.append(exam)

        if not upcoming:
            return f"📝 未来 {days} 天内没有考试 🎉"

        lines = [f"## 📝 未来 {days} 天内的考试\n"]
        for exam in upcoming:
            lines.append(f"### {exam.course_name}\n")
            lines.append(f"- 📅 日期: {exam.exam_date}")
            lines.append(f"- ⏰ 时间: {exam.exam_time}")
            if exam.location:
                lines.append(f"- 📍 地点: {exam.location}")
            if exam.seat_number:
                lines.append(f"- 💺 座位号: {exam.seat_number}")
            lines.append("")

        return "\n".join(lines)
    except PortalError as e:
        return f"❌ 检查失败: {e.message}"
    except Exception as e:
        logger.exception("检查近期考试异常")
        return "❌ 检查近期考试失败，请稍后重试"


@mcp.tool
def refresh_cache() -> str:
    """
    手动清除所有缓存并重新抓取数据。当数据可能已更新时使用。

    使用示例：refresh_cache()
    """
    try:
        cache = _get_cache()
        cache.invalidate_all()

        # 重新抓取
        client = _get_client()
        config = get_config()

        # 抓取课表
        lessons = client.get_lessons()
        cache.set("schedule_current", _serialize_lessons(lessons))

        # 抓取成绩
        grades = client.get_grades()
        cache.set("grades", _serialize_grades(grades.items))
        cache.set_raw("grades_snapshot", _serialize_grades(grades.items))

        # 抓取考试
        exams = client.get_exams()
        cache.set("exams", _serialize_exams(exams))

        return (
            f"✅ 缓存已刷新！\n"
            f"- 课表: {len(lessons.entries)} 条记录 ({lessons.term})\n"
            f"- 成绩: {len(grades.items)} 条记录\n"
            f"- 考试: {len(exams.items)} 条记录"
        )
    except PortalError as e:
        return f"❌ 刷新失败: {e.message}"
    except Exception as e:
        logger.exception("刷新缓存异常")
        return "❌ 刷新缓存失败，请稍后重试"


# ============================================================
# 服务器入口
# ============================================================


def main():
    """MCP 服务器入口"""
    import argparse

    parser = argparse.ArgumentParser(description="NJUST 教务系统 MCP 服务器")
    parser.add_argument("--username", help="教务系统学号")
    parser.add_argument("--password", help="教务系统密码")
    parser.add_argument("--semester-start-date", help="学期第一天日期 (YYYY-MM-DD)")
    args = parser.parse_args()

    # 命令行参数优先级最高，写入环境变量
    if args.username:
        os.environ["PORTAL_USERNAME"] = args.username
    if args.password:
        os.environ["PORTAL_PASSWORD"] = args.password
    if args.semester_start_date:
        os.environ["SEMESTER_START_DATE"] = args.semester_start_date

    # 刷新配置单例，确保包含命令行参数
    from .config import load_config as _load_config
    set_config(_load_config())

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("NJUST 教务系统 MCP 服务器启动中...")

    config = get_config()
    if config.portal_username and config.portal_password:
        logger.info("已加载教务系统账号配置")
    else:
        logger.info(
            "未配置教务系统账号，请通过 bind_account 工具绑定"
        )

    mcp.run()


if __name__ == "__main__":
    main()
