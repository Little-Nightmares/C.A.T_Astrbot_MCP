"""课表图片生成模块 - 使用 Pillow 绘制日历样式的周课表图片"""

from __future__ import annotations

import colorsys
import io
import logging
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from .portal.parsers import ScheduleOccurrence, WEEKDAY_LABELS

logger = logging.getLogger(__name__)

# ============================================================
# 常量定义
# ============================================================

# 画布尺寸
CANVAS_WIDTH = 1200
CANVAS_HEIGHT = 900

# 表格布局
HEADER_HEIGHT = 60  # 标题区域高度
WEEKDAY_HEADER_HEIGHT = 40  # 星期表头高度
LEFT_MARGIN = 80  # 左侧节次列宽度
TOP_MARGIN = HEADER_HEIGHT + WEEKDAY_HEADER_HEIGHT
RIGHT_MARGIN = 20
BOTTOM_MARGIN = 60  # 底部信息区域

# 颜色
BG_COLOR = (255, 255, 255)
HEADER_BG = (44, 62, 80)
HEADER_TEXT = (255, 255, 255)
GRID_COLOR = (189, 195, 199)
WEEKDAY_BG = (52, 73, 94)
WEEKDAY_TEXT = (255, 255, 255)
SECTION_TEXT = (44, 62, 80)
INFO_TEXT = (127, 140, 141)

# 课程颜色调色板（HSL 色相均匀分布）
COURSE_COLORS = [
    (52, 152, 219),   # 蓝
    (231, 76, 60),    # 红
    (46, 204, 113),   # 绿
    (155, 89, 182),   # 紫
    (241, 196, 15),   # 黄
    (230, 126, 34),   # 橙
    (26, 188, 156),   # 青
    (236, 100, 159),  # 粉
    (52, 73, 94),     # 深蓝
    (22, 160, 133),   # 深青
    (192, 57, 43),    # 深红
    (142, 68, 173),   # 深紫
    (39, 174, 96),    # 深绿
    (211, 84, 0),     # 深橙
    (41, 128, 185),   # 钢蓝
]

# 节次时间映射（NJUST 江阴校区作息时间）
# 上午: 8:00 开始，每节 45 分钟，节间 5 分钟，第 2 节后大休息 15 分钟
# 下午: 14:00 开始，每节 45 分钟，节间 5 分钟，第 7 节后大休息 15 分钟
# 晚上: 19:00 开始，每节 45 分钟，节间 5 分钟
SECTION_TIMES = {
    1: "08:00-08:45",
    2: "08:50-09:35",
    3: "09:50-10:35",
    4: "10:40-11:25",
    5: "11:30-12:15",
    6: "14:00-14:45",
    7: "14:50-15:35",
    8: "15:50-16:35",
    9: "16:40-17:25",
    10: "17:30-18:15",
    11: "19:00-19:45",
    12: "19:50-20:35",
    13: "20:40-21:25",
}

TOTAL_SECTIONS = 13
TOTAL_DAYS = 7

# 字体缓存
_font_cache: dict[tuple[int, bool], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """获取字体，优先使用系统中文字体（带缓存）"""
    cache_key = (size, bold)
    if cache_key in _font_cache:
        return _font_cache[cache_key]

    font_paths = [
        # Ubuntu / Debian (fonts-noto-cjk-extra)
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJKsc-Regular.otf",
        # Ubuntu / Debian (fonts-wqy-zenhei)
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        # Ubuntu / Debian (fonts-droid-fallback)
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        # Ubuntu / Debian (fonts-noto-cjk) - 其他变体
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJKsc-Regular.otc",
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        # Windows
        "C:\\Windows\\Fonts\\msyh.ttc",
        "C:\\Windows\\Fonts\\simhei.ttf",
    ]
    for font_path in font_paths:
        try:
            font = ImageFont.truetype(font_path, size)
            _font_cache[cache_key] = font
            return font
        except (OSError, IOError):
            continue
    logger.warning("未找到中文字体，使用默认字体（中文可能无法正常显示）")
    logger.warning("Ubuntu 用户请安装: sudo apt install fonts-noto-cjk-extra")
    font = ImageFont.load_default()
    _font_cache[cache_key] = font
    return font


def _generate_course_color(index: int) -> tuple[int, int, int]:
    """为课程生成颜色"""
    if index < len(COURSE_COLORS):
        return COURSE_COLORS[index]
    # 超出调色板时，用 HSL 生成
    hue = (index * 0.618033988749895) % 1.0  # 黄金比例
    r, g, b = colorsys.hls_to_rgb(hue, 0.55, 0.7)
    return (int(r * 255), int(g * 255), int(b * 255))


def _lighten_color(
    color: tuple[int, int, int], factor: float = 0.3
) -> tuple[int, int, int]:
    """使颜色变浅"""
    r, g, b = color
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return (r, g, b)


def _darken_color(
    color: tuple[int, int, int], factor: float = 0.3
) -> tuple[int, int, int]:
    """使颜色变深"""
    r, g, b = color
    r = int(r * (1 - factor))
    g = int(g * (1 - factor))
    b = int(b * (1 - factor))
    return (r, g, b)


@dataclass
class ScheduleImageConfig:
    """课表图片配置"""

    width: int = CANVAS_WIDTH
    height: int = CANVAS_HEIGHT
    title: str = "我的课表"
    subtitle: str = ""


def render_schedule_to_png(
    entries: list[ScheduleOccurrence],
    week: int,
    term: str = "",
    config: ScheduleImageConfig | None = None,
) -> bytes:
    """
    将课表渲染为 PNG 图片

    Args:
        entries: 课表条目列表
        week: 周次
        term: 学期
        config: 图片配置

    Returns:
        PNG 图片的字节数据
    """
    cfg = config or ScheduleImageConfig(
        subtitle=f"第 {week} 周" + (f" | {term}" if term else "")
    )

    # 过滤指定周次的课程
    week_entries = [e for e in entries if week in e.week_numbers]

    # 创建画布
    img = Image.new("RGB", (cfg.width, cfg.height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # 加载字体
    font_title = _get_font(24, bold=True)
    font_subtitle = _get_font(14)
    font_weekday = _get_font(14, bold=True)
    font_section = _get_font(12)
    font_course_name = _get_font(13, bold=True)
    font_course_info = _get_font(11)

    # 计算网格尺寸
    grid_width = cfg.width - LEFT_MARGIN - RIGHT_MARGIN
    grid_height = cfg.height - TOP_MARGIN - BOTTOM_MARGIN
    cell_width = grid_width / TOTAL_DAYS
    cell_height = grid_height / TOTAL_SECTIONS

    # ---- 绘制标题 ----
    draw.rectangle([0, 0, cfg.width, HEADER_HEIGHT], fill=HEADER_BG)
    title_bbox = draw.textbbox((0, 0), cfg.title, font=font_title)
    title_x = (cfg.width - (title_bbox[2] - title_bbox[0])) // 2
    draw.text(
        (title_x, 12),
        cfg.title,
        fill=HEADER_TEXT,
        font=font_title,
    )
    if cfg.subtitle:
        sub_bbox = draw.textbbox((0, 0), cfg.subtitle, font=font_subtitle)
        sub_x = (cfg.width - (sub_bbox[2] - sub_bbox[0])) // 2
        draw.text(
            (sub_x, 40),
            cfg.subtitle,
            fill=(189, 195, 199),
            font=font_subtitle,
        )

    # ---- 绘制星期表头 ----
    weekday_y = HEADER_HEIGHT
    draw.rectangle(
        [0, weekday_y, cfg.width, weekday_y + WEEKDAY_HEADER_HEIGHT],
        fill=WEEKDAY_BG,
    )
    for day in range(1, TOTAL_DAYS + 1):
        x = LEFT_MARGIN + (day - 1) * cell_width
        label = WEEKDAY_LABELS[day]
        bbox = draw.textbbox((0, 0), label, font=font_weekday)
        text_x = x + (cell_width - (bbox[2] - bbox[0])) / 2
        text_y = weekday_y + (WEEKDAY_HEADER_HEIGHT - (bbox[3] - bbox[1])) / 2
        draw.text((text_x, text_y), label, fill=WEEKDAY_TEXT, font=font_weekday)

    # ---- 绘制网格 ----
    # 水平线
    for i in range(TOTAL_SECTIONS + 1):
        y = TOP_MARGIN + i * cell_height
        draw.line(
            [(LEFT_MARGIN, y), (cfg.width - RIGHT_MARGIN, y)],
            fill=GRID_COLOR,
            width=1,
        )
    # 垂直线
    for i in range(TOTAL_DAYS + 1):
        x = LEFT_MARGIN + i * cell_width
        draw.line(
            [(x, TOP_MARGIN), (x, TOP_MARGIN + grid_height)],
            fill=GRID_COLOR,
            width=1,
        )

    # ---- 绘制节次标签 ----
    for section in range(1, TOTAL_SECTIONS + 1):
        y = TOP_MARGIN + (section - 1) * cell_height
        # 节次号
        section_text = f"第{section}节"
        bbox = draw.textbbox((0, 0), section_text, font=font_section)
        text_x = (LEFT_MARGIN - (bbox[2] - bbox[0])) / 2
        text_y = y + (cell_height - (bbox[3] - bbox[1])) / 2 - 8
        draw.text((text_x, text_y), section_text, fill=SECTION_TEXT, font=font_section)
        # 时间
        time_text = SECTION_TIMES.get(section, "")
        if time_text:
            bbox = draw.textbbox((0, 0), time_text, font=font_course_info)
            text_x = (LEFT_MARGIN - (bbox[2] - bbox[0])) / 2
            text_y = y + (cell_height - (bbox[3] - bbox[1])) / 2 + 8
            draw.text(
                (text_x, text_y), time_text, fill=INFO_TEXT, font=font_course_info
            )

    # ---- 绘制课程方块 ----
    # 为不同课程分配颜色
    course_color_map: dict[str, tuple[int, int, int]] = {}
    color_index = 0
    for entry in week_entries:
        if entry.course_name not in course_color_map:
            course_color_map[entry.course_name] = _generate_course_color(color_index)
            color_index += 1

    for entry in week_entries:
        color = course_color_map[entry.course_name]
        light_color = _lighten_color(color, 0.7)
        dark_color = _darken_color(color, 0.2)

        # 计算方块位置
        x = LEFT_MARGIN + (entry.weekday - 1) * cell_width + 2
        y_start = TOP_MARGIN + (entry.block_start - 1) * cell_height + 2
        y_end = TOP_MARGIN + entry.block_end * cell_height - 2
        block_width = cell_width - 4
        block_height = y_end - y_start

        if block_height < 10:
            continue

        # 绘制圆角矩形背景
        draw.rounded_rectangle(
            [x, y_start, x + block_width, y_end],
            radius=6,
            fill=light_color,
            outline=color,
            width=2,
        )

        # 绘制课程名
        text_x = x + 6
        text_y = y_start + 4
        max_width = block_width - 12

        # 课程名（可能需要截断）
        course_name = entry.course_name
        bbox = draw.textbbox((0, 0), course_name, font=font_course_name)
        text_width = bbox[2] - bbox[0]
        if text_width > max_width:
            # 截断文字
            while len(course_name) > 1:
                bbox = draw.textbbox((0, 0), course_name + "...", font=font_course_name)
                if bbox[2] - bbox[0] <= max_width:
                    break
                course_name = course_name[:-1]
            course_name += "..."
        draw.text(
            (text_x, text_y),
            course_name,
            fill=dark_color,
            font=font_course_name,
        )

        # 绘制地点和教师
        info_parts = []
        if entry.location:
            info_parts.append(f"📍{entry.location}")
        if entry.teacher:
            info_parts.append(f"👨‍🏫{entry.teacher}")

        info_text = " ".join(info_parts)
        if info_text and block_height > 35:
            info_y = text_y + 20
            bbox = draw.textbbox((0, 0), info_text, font=font_course_info)
            text_width = bbox[2] - bbox[0]
            if text_width > max_width:
                while len(info_text) > 1:
                    bbox = draw.textbbox((0, 0), info_text + "...", font=font_course_info)
                    if bbox[2] - bbox[0] <= max_width:
                        break
                    info_text = info_text[:-1]
                info_text += "..."
            draw.text(
                (text_x, info_y),
                info_text,
                fill=dark_color,
                font=font_course_info,
            )

    # ---- 绘制底部信息 ----
    info_y = cfg.height - BOTTOM_MARGIN + 15
    info_text = f"共 {len(week_entries)} 门课程"
    draw.text((LEFT_MARGIN, info_y), info_text, fill=INFO_TEXT, font=font_subtitle)

    # 输出为 PNG
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
