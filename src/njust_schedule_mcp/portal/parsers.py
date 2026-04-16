"""HTML 解析器 - 解析教务系统页面（登录表单、课表、成绩、考试）

参考 cat-schedule 项目的 parsers.py 实现，适配 NJUST 强智科技教务系统。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

# 星期映射
WEEKDAY_MAP = {
    "一": (1, "星期一"),
    "二": (2, "星期二"),
    "三": (3, "星期三"),
    "四": (4, "星期四"),
    "五": (5, "星期五"),
    "六": (6, "星期六"),
    "日": (7, "星期日"),
    "天": (7, "星期日"),
}

# NJUST 江阴校区节次-时间映射表
# 上午: 8:00 开始，每节 45 分钟，节间 5 分钟，第 2 节后大休息 15 分钟
# 下午: 14:00 开始，每节 45 分钟，节间 5 分钟，第 7 节后大休息 15 分钟
# 晚上: 19:00 开始，每节 45 分钟，节间 5 分钟
SECTION_TIME_TABLE: dict[int, tuple[str, str]] = {
    1: ("08:00", "08:45"),
    2: ("08:50", "09:35"),
    3: ("09:50", "10:35"),
    4: ("10:40", "11:25"),
    5: ("11:30", "12:15"),
    6: ("14:00", "14:45"),
    7: ("14:50", "15:35"),
    8: ("15:50", "16:35"),
    9: ("16:40", "17:25"),
    10: ("17:30", "18:15"),
    11: ("19:00", "19:45"),
    12: ("19:50", "20:35"),
    13: ("20:40", "21:25"),
}


def format_section_time(block_start: int, block_end: int) -> str:
    """将节次编号转换为具体时间，如 6,7 → '14:00-15:35'"""
    start = SECTION_TIME_TABLE.get(block_start)
    end = SECTION_TIME_TABLE.get(block_end)
    if start and end:
        return f"{start[0]}-{end[1]}"
    return f"第 {block_start}-{block_end} 节"

WEEKDAY_LABELS = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def normalize_text(value: str | None) -> str:
    """标准化文本：去除多余空白"""
    return re.sub(r"\s+", " ", (value or "").strip())


# ============================================================
# 登录表单解析
# ============================================================


@dataclass
class LoginFormMeta:
    """登录表单元数据"""

    action: str
    method: str
    username_field: str
    password_field: str
    captcha_field: str
    hidden_fields: dict[str, str] = field(default_factory=dict)
    captcha_image_url: str | None = None


def _input_key(input_tag: Tag) -> str:
    """获取 input 标签的 name 或 id"""
    return (input_tag.get("name") or input_tag.get("id") or "").strip()


def _matches_any(text: str, keywords: list[str]) -> bool:
    """检查文本是否包含任一关键词"""
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def parse_login_form(html: str) -> LoginFormMeta:
    """
    解析登录页面表单

    Args:
        html: 登录页面 HTML

    Returns:
        LoginFormMeta: 登录表单元数据
    """
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form")
    if not form:
        raise ValueError("教务系统登录表单未找到")

    hidden_fields: dict[str, str] = {}
    visible_inputs: list[Tag] = []

    for input_tag in form.find_all("input"):
        input_name = _input_key(input_tag)
        if not input_name:
            continue
        input_type = (input_tag.get("type") or "text").lower()
        if input_type == "hidden":
            hidden_fields[input_name] = input_tag.get("value", "")
            continue
        if input_type in {"submit", "button", "reset", "image", "checkbox", "radio"}:
            continue
        visible_inputs.append(input_tag)

    password_input = next(
        (item for item in visible_inputs if (item.get("type") or "text").lower() == "password"),
        None,
    )

    captcha_input = next(
        (
            item
            for item in visible_inputs
            if _matches_any(
                _input_key(item),
                ["captcha", "randomcode", "verify", "safecode", "checkcode", "rand"],
            )
        ),
        None,
    )
    if not captcha_input:
        captcha_input = next(
            (
                item
                for item in visible_inputs
                if item is not password_input
                and item.find_parent("td")
                and item.find_parent("td").find("img")
            ),
            None,
        )

    username_input = next(
        (
            item
            for item in visible_inputs
            if item is not password_input
            and item is not captcha_input
            and _matches_any(
                _input_key(item), ["user", "account", "login", "name", "xh", "zjh", "number"]
            )
        ),
        None,
    )
    if not username_input:
        username_input = next(
            (
                item
                for item in visible_inputs
                if item is not password_input and item is not captcha_input
            ),
            None,
        )

    captcha_img = (
        form.find("img", id=re.compile("safecode", re.I))
        or form.find("img", src=re.compile("verify|captcha|safecode|randomcode", re.I))
        or soup.find("img", id=re.compile("safecode", re.I))
        or soup.find("img", src=re.compile("verify|captcha|safecode|randomcode", re.I))
    )

    return LoginFormMeta(
        action=form.get("action") or "/",
        method=(form.get("method") or "post").upper(),
        username_field=_input_key(username_input) or "USERNAME",
        password_field=_input_key(password_input) or "PASSWORD",
        captcha_field=_input_key(captcha_input) or "RANDOMCODE",
        hidden_fields=hidden_fields,
        captcha_image_url=captcha_img.get("src") if captcha_img else None,
    )


def is_login_page(html: str) -> bool:
    """判断是否为登录页面"""
    soup = BeautifulSoup(html, "html.parser")
    return bool(soup.find("input", attrs={"name": "USERNAME"})) and bool(
        soup.find("input", attrs={"name": "PASSWORD"})
    )


def extract_login_error(html: str) -> str | None:
    """提取登录错误信息"""
    soup = BeautifulSoup(html, "html.parser")
    red_font = soup.find("font", attrs={"color": "red"})
    if red_font:
        value = normalize_text(red_font.get_text(" ", strip=True))
        if value:
            return value
    # 尝试其他错误提示方式
    alert_div = soup.find("div", class_=re.compile("alert|error|msg", re.I))
    if alert_div:
        value = normalize_text(alert_div.get_text(" ", strip=True))
        if value:
            return value
    return None


# ============================================================
# 课表解析
# ============================================================


@dataclass
class CourseTimeSegment:
    """课程时间段"""

    weekday: int
    weekday_label: str
    start_section: int | None
    end_section: int | None
    time_text: str
    location: str | None = None


@dataclass
class CourseDetailRow:
    """课程明细行"""

    course_code: str | None
    class_no: str | None
    course_name: str
    teacher: str | None
    segments: list[CourseTimeSegment] = field(default_factory=list)
    credit: str | None = None
    course_attribute: str | None = None
    selection_stage: str | None = None


@dataclass
class ScheduleOccurrence:
    """课表条目"""

    course_code: str | None
    class_no: str | None
    course_name: str
    teacher: str | None
    weekday: int
    weekday_label: str
    block_start: int
    block_end: int
    block_label_start: str
    block_label_end: str
    time_text: str
    week_text: str
    week_numbers: list[int]
    location: str | None
    credit: str | None
    course_attribute: str | None
    selection_stage: str | None
    raw_payload: dict = field(default_factory=dict)


@dataclass
class LessonsParseResult:
    """课表解析结果"""

    term: str | None
    available_terms: list[str]
    entries: list[ScheduleOccurrence]
    raw_summary: dict = field(default_factory=dict)


def parse_week_numbers(week_text: str) -> list[int]:
    """
    解析周次文本，如 "1-16周", "1-8周,10-16周", "1,3,5,7,9,11,13,15周"

    Args:
        week_text: 周次文本

    Returns:
        排序后的周次列表
    """
    body = normalize_text(week_text).replace("(周)", "").replace("周", "")
    if not body:
        return []
    weeks: set[int] = set()
    for token in re.split(r"[，,]", body):
        token = token.strip()
        if not token:
            continue
        odd_only = "单" in token
        even_only = "双" in token
        token = token.replace("单", "").replace("双", "")
        range_match = re.match(r"(\d+)-(\d+)", token)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            for value in range(start, end + 1):
                if odd_only and value % 2 == 0:
                    continue
                if even_only and value % 2 == 1:
                    continue
                weeks.add(value)
            continue
        if token.isdigit():
            value = int(token)
            if odd_only and value % 2 == 0:
                continue
            if even_only and value % 2 == 1:
                continue
            weeks.add(value)
    return sorted(weeks)


def parse_time_segment_text(
    time_text: str, location: str | None
) -> CourseTimeSegment | None:
    """解析时间段文本，如 '星期一(01-02小节)'"""
    time_text = normalize_text(time_text)
    match = re.search(r"星期([一二三四五六日天])\((\d{2})-(\d{2})小节\)", time_text)
    if not match:
        return None
    weekday, weekday_label = WEEKDAY_MAP[match.group(1)]
    return CourseTimeSegment(
        weekday=weekday,
        weekday_label=weekday_label,
        start_section=int(match.group(2)),
        end_section=int(match.group(3)),
        time_text=time_text,
        location=normalize_text(location) or None,
    )


def _parse_schedule_details(soup: BeautifulSoup) -> dict[str, list[CourseDetailRow]]:
    """解析课表下方的明细表 #dataList"""
    rows = soup.select("#dataList tr")
    result: dict[str, list[CourseDetailRow]] = {}
    for row in rows[1:]:
        cells = row.find_all("td")
        if len(cells) < 10:
            continue
        course_name = normalize_text(cells[3].get_text(" ", strip=True))
        teacher = normalize_text(cells[4].get_text(" ", strip=True)) or None
        time_lines = [
            normalize_text(chunk)
            for chunk in cells[5].get_text("\n", strip=True).split("\n")
            if normalize_text(chunk)
        ]
        location_values = [
            normalize_text(item)
            for item in (cells[7].get_text(" ", strip=True) or "").split(",")
        ]
        segments: list[CourseTimeSegment] = []
        for index, time_line in enumerate(time_lines):
            location = location_values[index] if index < len(location_values) else None
            parsed = parse_time_segment_text(time_line, location)
            if parsed:
                segments.append(parsed)
        detail = CourseDetailRow(
            course_code=normalize_text(cells[1].get_text(" ", strip=True)) or None,
            class_no=normalize_text(cells[2].get_text(" ", strip=True)) or None,
            course_name=course_name,
            teacher=teacher,
            segments=segments,
            credit=normalize_text(cells[6].get_text(" ", strip=True)) or None,
            course_attribute=normalize_text(cells[8].get_text(" ", strip=True)) or None,
            selection_stage=normalize_text(cells[9].get_text(" ", strip=True)) or None,
        )
        result.setdefault(course_name, []).append(detail)
    return result


def _finalize_segment(
    current: dict[str, str | None], target: list[dict[str, str | None]]
) -> None:
    """将当前解析的片段添加到目标列表"""
    course_name = normalize_text(current.get("course_name"))
    if not course_name:
        return
    target.append(
        {
            "course_name": course_name,
            "teacher": normalize_text(current.get("teacher")) or None,
            "week_text": normalize_text(current.get("week_text")) or "",
            "location": normalize_text(current.get("location")) or None,
            "group_name": normalize_text(current.get("group_name")) or None,
        }
    )


def _iter_cell_segments(div: Tag) -> list[dict[str, str | None]]:
    """迭代解析课表格子中的课程片段"""
    segments: list[dict[str, str | None]] = []
    raw_html = div.decode_contents()
    chunks = [chunk.strip() for chunk in re.split(r"-{5,}", raw_html) if chunk.strip()]
    for chunk in chunks:
        fragment = BeautifulSoup(chunk, "html.parser")
        current: dict[str, str | None] = {}
        all_lines = [
            normalize_text(line)
            for line in fragment.get_text("\n", strip=True).split("\n")
            if normalize_text(line)
        ]
        if all_lines:
            current["course_name"] = all_lines[0]
        for child in fragment.find_all("font"):
            label = normalize_text(child.get("title"))
            value = normalize_text(child.get_text(" ", strip=True))
            if "老师" in label:
                current["teacher"] = value
            elif "周次" in label:
                current["week_text"] = value
            elif "教室" in label:
                current["location"] = value
            elif "分组" in label:
                current["group_name"] = value
        _finalize_segment(current, segments)
    return segments


def _match_detail(
    course_name: str,
    teacher: str | None,
    location: str | None,
    weekday: int,
    detail_map: dict[str, list[CourseDetailRow]],
) -> tuple[CourseDetailRow | None, CourseTimeSegment | None]:
    """匹配课程明细"""
    best_detail: CourseDetailRow | None = None
    best_segment: CourseTimeSegment | None = None
    best_score = -1
    for detail in detail_map.get(course_name, []):
        for segment in detail.segments:
            if segment.weekday != weekday:
                continue
            score = 0
            if teacher and detail.teacher and teacher in detail.teacher:
                score += 2
            if location and segment.location and location == segment.location:
                score += 3
            elif location and segment.location and location in segment.location:
                score += 2
            if score > best_score:
                best_score = score
                best_detail = detail
                best_segment = segment
    return best_detail, best_segment


def _detail_match_score(
    item: dict, detail: CourseDetailRow, segment: CourseTimeSegment
) -> int:
    """计算明细匹配分数"""
    score = 0
    teacher = item.get("teacher")
    location = item.get("location")
    if teacher and detail.teacher and teacher in detail.teacher:
        score += 4
    if location and segment.location and location == segment.location:
        score += 6
    elif location and segment.location and location in segment.location:
        score += 4
    return score


def _matching_order_key(item: dict) -> tuple:
    """排序键"""
    return (
        item["course_name"],
        item["weekday"],
        item["block_start"],
        item["block_end"],
        item["week_text"],
        item["teacher"] or "",
        item["location"] or "",
    )


def _assign_detail_segments(
    merged_entries: list[dict],
    detail_map: dict[str, list[CourseDetailRow]],
) -> list[tuple[dict, CourseDetailRow | None, CourseTimeSegment | None]]:
    """为合并后的条目分配明细信息"""
    assignments: list[tuple[dict, CourseDetailRow | None, CourseTimeSegment | None]] = []
    grouped_entries: dict[str, list[dict]] = {}
    for item in merged_entries:
        grouped_entries.setdefault(item["course_name"], []).append(item)

    for course_name, course_items in grouped_entries.items():
        candidates: list[tuple[int, CourseDetailRow, CourseTimeSegment]] = []
        for detail_index, detail in enumerate(detail_map.get(course_name, [])):
            for segment in detail.segments:
                candidates.append((detail_index, detail, segment))

        used_indices: set[int] = set()
        for item in sorted(course_items, key=_matching_order_key):
            same_weekday = [
                (index, detail, segment)
                for index, (detail_index, detail, segment) in enumerate(candidates)
                if index not in used_indices and segment.weekday == item["weekday"]
            ]
            if same_weekday:
                chosen_index, chosen_detail, chosen_segment = max(
                    same_weekday,
                    key=lambda entry: (
                        _detail_match_score(item, entry[1], entry[2]),
                        -entry[0],
                    ),
                )
                used_indices.add(chosen_index)
                assignments.append((item, chosen_detail, chosen_segment))
                continue

            detail, detail_segment = _match_detail(
                item["course_name"],
                item["teacher"],
                item["location"],
                item["weekday"],
                detail_map,
            )
            assignments.append((item, detail, detail_segment))

    assignments.sort(key=lambda entry: _matching_order_key(entry[0]))
    return assignments


def parse_lessons_html(html: str) -> LessonsParseResult:
    """
    解析课表页面 HTML

    Args:
        html: 课表页面 HTML

    Returns:
        LessonsParseResult: 解析结果
    """
    soup = BeautifulSoup(html, "html.parser")

    # 解析学期选择器
    selected_term_option = soup.select_one("#xnxq01id option[selected]")
    term = (
        normalize_text(selected_term_option.get_text(strip=True))
        if selected_term_option
        else None
    )
    available_terms = [
        normalize_text(option.get_text(strip=True))
        for option in soup.select("#xnxq01id option")
    ]

    # 解析明细表
    detail_map = _parse_schedule_details(soup)

    # 解析周课表格子
    grid_rows = soup.select("#kbtable tr")[1:]
    raw_entries: list[dict] = []

    for row_index, row in enumerate(grid_rows, start=1):
        header = row.find("th")
        if not header:
            continue
        block_label = normalize_text(header.get_text(" ", strip=True))
        cells = row.find_all("td")

        for weekday_index, cell in enumerate(cells, start=1):
            detail_div = cell.find("div", class_="kbcontent")
            if not detail_div:
                continue
            for segment in _iter_cell_segments(detail_div):
                if not segment["course_name"]:
                    continue
                raw_entries.append(
                    {
                        "course_name": segment["course_name"],
                        "teacher": segment["teacher"],
                        "week_text": segment["week_text"],
                        "week_numbers": parse_week_numbers(segment["week_text"] or ""),
                        "location": segment["location"],
                        "weekday": weekday_index,
                        "weekday_label": f"星期{'一二三四五六日'[weekday_index - 1]}",
                        "block_index": row_index,
                        "block_label": block_label,
                    }
                )

    # 排序并合并相邻节次
    raw_entries.sort(
        key=lambda item: (
            item["course_name"],
            item["teacher"] or "",
            item["location"] or "",
            item["weekday"],
            item["week_text"],
            item["block_index"],
        )
    )

    merged_entries: list[dict] = []
    for entry in raw_entries:
        if not merged_entries:
            merged_entries.append(
                {**entry, "block_start": entry["block_index"], "block_end": entry["block_index"]}
            )
            continue
        previous = merged_entries[-1]
        same_key = all(
            previous[key] == entry[key]
            for key in ["course_name", "teacher", "location", "weekday", "week_text", "weekday_label"]
        )
        if same_key and previous["block_end"] + 1 == entry["block_index"]:
            previous["block_end"] = entry["block_index"]
            previous["block_label_end"] = entry["block_label"]
        else:
            merged_entries.append(
                {**entry, "block_start": entry["block_index"], "block_end": entry["block_index"]}
            )

    # 分配明细信息并生成最终条目
    entries: list[ScheduleOccurrence] = []
    for item, detail, detail_segment in _assign_detail_segments(merged_entries, detail_map):
        block_start = (
            detail_segment.start_section
            if detail_segment and detail_segment.start_section is not None
            else item["block_start"]
        )
        block_end = (
            detail_segment.end_section
            if detail_segment and detail_segment.end_section is not None
            else item["block_end"]
        )
        entries.append(
            ScheduleOccurrence(
                course_code=detail.course_code if detail else None,
                class_no=detail.class_no if detail else None,
                course_name=item["course_name"],
                teacher=item["teacher"],
                weekday=item["weekday"],
                weekday_label=item["weekday_label"],
                block_start=block_start,
                block_end=block_end,
                block_label_start=item.get("block_label", str(block_start)),
                block_label_end=item.get("block_label_end", str(block_end)),
                time_text=detail_segment.time_text if detail_segment else "",
                week_text=item["week_text"],
                week_numbers=item["week_numbers"],
                location=item["location"],
                credit=detail.credit if detail else None,
                course_attribute=detail.course_attribute if detail else None,
                selection_stage=detail.selection_stage if detail else None,
            )
        )

    return LessonsParseResult(
        term=term,
        available_terms=available_terms,
        entries=entries,
    )


# ============================================================
# 成绩解析
# ============================================================


@dataclass
class GradeItemParsed:
    """成绩条目"""

    record_key: str
    term: str
    course_code: str | None
    course_name: str
    score: str | None
    score_numeric: float | None
    score_flag: str | None
    grade_point_text: str | None
    credit: str | None
    total_hours: str | None
    assessment_method: str | None
    course_attribute: str | None
    course_nature: str | None
    raw_payload: dict = field(default_factory=dict)


@dataclass
class GradesParseResult:
    """成绩解析结果"""

    items: list[GradeItemParsed]
    raw_summary: dict = field(default_factory=dict)


def _generate_record_key(item: dict) -> str:
    """基于稳定字段生成成绩记录唯一键"""
    raw = f"{item.get('term', '')}|{item.get('course_code', '')}|{item.get('course_name', '')}|{item.get('credit', '')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_score(score_text: str) -> tuple[str | None, float | None, str | None]:
    """
    解析成绩文本

    Returns:
        (score_str, score_numeric, score_flag)
        score_flag: "优秀"/"良好"/"中等"/"及格"/"不及格" 等等级制标记
    """
    text = normalize_text(score_text)
    if not text or text in ("", "--", "-", "暂无"):
        return None, None, None

    # 等级制
    grade_flags = {"优秀", "良好", "中等", "及格", "不及格", "合格", "不合格", "免修"}
    if text in grade_flags:
        return text, None, text

    # 数值
    try:
        numeric = float(text)
        return text, numeric, None
    except ValueError:
        return text, None, None


def parse_grades_html(html: str) -> GradesParseResult:
    """
    解析成绩页面 HTML

    Args:
        html: 成绩页面 HTML

    Returns:
        GradesParseResult: 解析结果
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[GradeItemParsed] = []

    # 尝试从 #dataList 表格解析
    rows = soup.select("#dataList tr")
    if not rows:
        # 备选：查找其他成绩表格
        rows = soup.select("table.datelist tr")
    if not rows:
        rows = soup.select("table tr")

    for row in rows[1:]:  # 跳过表头
        cells = row.find_all("td")
        if len(cells) < 6:
            continue

        # 尝试适配不同列数的成绩表
        # 常见列序：序号, 学期, 课程编号, 课程名称, 成绩, 学分, 学时, 考核方式, 课程属性, 课程性质
        # 或简化版：序号, 学期, 课程编号, 课程名称, 成绩, 学分
        item: dict = {}
        if len(cells) >= 10:
            item["term"] = normalize_text(cells[1].get_text(strip=True))
            item["course_code"] = normalize_text(cells[2].get_text(strip=True)) or None
            item["course_name"] = normalize_text(cells[3].get_text(strip=True))
            score_text = normalize_text(cells[4].get_text(strip=True))
            item["credit"] = normalize_text(cells[5].get_text(strip=True)) or None
            item["total_hours"] = normalize_text(cells[6].get_text(strip=True)) or None
            item["assessment_method"] = normalize_text(cells[7].get_text(strip=True)) or None
            item["course_attribute"] = normalize_text(cells[8].get_text(strip=True)) or None
            item["course_nature"] = normalize_text(cells[9].get_text(strip=True)) or None
        elif len(cells) >= 6:
            item["term"] = normalize_text(cells[1].get_text(strip=True))
            item["course_code"] = normalize_text(cells[2].get_text(strip=True)) or None
            item["course_name"] = normalize_text(cells[3].get_text(strip=True))
            score_text = normalize_text(cells[4].get_text(strip=True))
            item["credit"] = normalize_text(cells[5].get_text(strip=True)) or None
            item["total_hours"] = None
            item["assessment_method"] = None
            item["course_attribute"] = None
            item["course_nature"] = None
        else:
            continue

        score_str, score_numeric, score_flag = _parse_score(score_text)
        item["score"] = score_str
        item["score_numeric"] = score_numeric
        item["score_flag"] = score_flag

        items.append(
            GradeItemParsed(
                record_key=_generate_record_key(item),
                term=item["term"],
                course_code=item["course_code"],
                course_name=item["course_name"],
                score=score_str,
                score_numeric=score_numeric,
                score_flag=score_flag,
                grade_point_text=None,
                credit=item["credit"],
                total_hours=item["total_hours"],
                assessment_method=item["assessment_method"],
                course_attribute=item["course_attribute"],
                course_nature=item["course_nature"],
            )
        )

    return GradesParseResult(items=items)


# ============================================================
# 考试安排解析
# ============================================================


@dataclass
class ExamItem:
    """考试安排条目"""

    course_name: str
    course_code: str | None
    exam_date: str
    exam_time: str
    location: str | None
    seat_number: str | None
    exam_type: str | None
    notes: str | None


@dataclass
class ExamsParseResult:
    """考试安排解析结果"""

    items: list[ExamItem]


def parse_exams_html(html: str) -> ExamsParseResult:
    """
    解析考试安排页面 HTML

    Args:
        html: 考试安排页面 HTML

    Returns:
        ExamsParseResult: 解析结果
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[ExamItem] = []

    # 尝试从 #dataList 表格解析
    rows = soup.select("#dataList tr")
    if not rows:
        rows = soup.select("table.datelist tr")
    if not rows:
        rows = soup.select("table tr")

    for row in rows[1:]:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        # 常见列序：序号, 课程名称/编号, 考试日期, 考试时间, 考试地点, 座位号, 考试形式
        item: dict = {}
        if len(cells) >= 7:
            item["course_name"] = normalize_text(cells[1].get_text(strip=True))
            item["course_code"] = normalize_text(cells[2].get_text(strip=True)) or None
            item["exam_date"] = normalize_text(cells[3].get_text(strip=True))
            item["exam_time"] = normalize_text(cells[4].get_text(strip=True))
            item["location"] = normalize_text(cells[5].get_text(strip=True)) or None
            item["seat_number"] = normalize_text(cells[6].get_text(strip=True)) or None
            item["exam_type"] = normalize_text(cells[7].get_text(strip=True)) if len(cells) > 7 else None
        elif len(cells) >= 5:
            item["course_name"] = normalize_text(cells[1].get_text(strip=True))
            item["course_code"] = None
            item["exam_date"] = normalize_text(cells[2].get_text(strip=True))
            item["exam_time"] = normalize_text(cells[3].get_text(strip=True))
            item["location"] = normalize_text(cells[4].get_text(strip=True)) or None
            item["seat_number"] = normalize_text(cells[5].get_text(strip=True)) if len(cells) > 5 else None
            item["exam_type"] = None
        else:
            item["course_name"] = normalize_text(cells[1].get_text(strip=True))
            item["course_code"] = None
            item["exam_date"] = normalize_text(cells[2].get_text(strip=True))
            item["exam_time"] = normalize_text(cells[3].get_text(strip=True))
            item["location"] = normalize_text(cells[4].get_text(strip=True)) if len(cells) > 4 else None
            item["seat_number"] = None
            item["exam_type"] = None

        items.append(
            ExamItem(
                course_name=item["course_name"],
                course_code=item["course_code"],
                exam_date=item["exam_date"],
                exam_time=item["exam_time"],
                location=item["location"],
                seat_number=item["seat_number"],
                exam_type=item["exam_type"],
                notes=None,
            )
        )

    return ExamsParseResult(items=items)


# ============================================================
# 格式化输出
# ============================================================


def format_schedule_text(result: LessonsParseResult, week: int | None = None) -> str:
    """
    将课表格式化为 Markdown 文本

    Args:
        result: 课表解析结果
        week: 指定周次（None 表示全部）

    Returns:
        Markdown 格式的课表文本
    """
    if not result.entries:
        return "暂无课表数据"

    header = f"## 📚 课表 ({result.term or '未知学期'})\n\n"

    if week is not None:
        header += f"**第 {week} 周**\n\n"

    # 按星期分组
    weekday_entries: dict[int, list[ScheduleOccurrence]] = {}
    for entry in result.entries:
        if week is not None and week not in entry.week_numbers:
            continue
        weekday_entries.setdefault(entry.weekday, []).append(entry)

    if not weekday_entries:
        return f"第 {week} 周没有课程 🎉"

    lines = [header]
    for day in range(1, 8):
        entries = weekday_entries.get(day, [])
        if not entries:
            continue
        label = WEEKDAY_LABELS[day]
        lines.append(f"### {label}\n")
        for entry in sorted(entries, key=lambda e: e.block_start):
            time_str = format_section_time(entry.block_start, entry.block_end)
            location_str = f"📍 {entry.location}" if entry.location else ""
            teacher_str = f"👨‍🏫 {entry.teacher}" if entry.teacher else ""
            credit_str = f"({entry.credit} 学分)" if entry.credit else ""
            lines.append(
                f"- **{entry.course_name}** {credit_str}\n"
                f"  - ⏰ {time_str} {location_str} {teacher_str}\n"
                f"  - 📅 周次: {entry.week_text}"
            )
        lines.append("")

    return "\n".join(lines)


def format_grades_text(result: GradesParseResult, term: str | None = None) -> str:
    """
    将成绩格式化为 Markdown 文本

    Args:
        result: 成绩解析结果
        term: 指定学期（None 表示全部）

    Returns:
        Markdown 格式的成绩文本
    """
    if not result.items:
        return "暂无成绩数据"

    items = result.items
    if term:
        items = [g for g in items if g.term == term]
        if not items:
            return f"{term} 学期暂无成绩"

    header = f"## 📊 成绩查询"
    if term:
        header += f" ({term})"
    header += "\n\n"

    # 计算统计
    scored = [g for g in items if g.score_numeric is not None]
    if scored:
        avg = sum(g.score_numeric for g in scored) / len(scored)
        total_credit = sum(float(g.credit or 0) for g in items if g.credit)
        header += f"**已出分: {len(scored)}/{len(items)} | 平均分: {avg:.1f} | 总学分: {total_credit}**\n\n"

    lines = [header]
    lines.append("| 课程名称 | 学期 | 成绩 | 学分 | 课程属性 |")
    lines.append("|---------|------|------|------|---------|")
    for item in items:
        score_display = item.score or "未出分"
        lines.append(
            f"| {item.course_name} | {item.term} | {score_display} "
            f"| {item.credit or '-'} | {item.course_attribute or '-'} |"
        )

    return "\n".join(lines)


def format_exams_text(result: ExamsParseResult) -> str:
    """
    将考试安排格式化为 Markdown 文本

    Args:
        result: 考试安排解析结果

    Returns:
        Markdown 格式的考试安排文本
    """
    if not result.items:
        return "暂无考试安排"

    lines = ["## 📝 考试安排\n"]
    for item in result.items:
        lines.append(f"### {item.course_name}\n")
        lines.append(f"- 📅 日期: {item.exam_date}")
        lines.append(f"- ⏰ 时间: {item.exam_time}")
        if item.location:
            lines.append(f"- 📍 地点: {item.location}")
        if item.seat_number:
            lines.append(f"- 💺 座位号: {item.seat_number}")
        if item.exam_type:
            lines.append(f"- 📋 形式: {item.exam_type}")
        lines.append("")

    return "\n".join(lines)
