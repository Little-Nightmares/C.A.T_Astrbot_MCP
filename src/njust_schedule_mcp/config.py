"""配置管理模块 - 从环境变量读取配置"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """MCP 服务器配置"""

    # 教务系统账号
    portal_username: str = ""
    portal_password: str = ""

    # 教务系统地址
    portal_base_url: str = "http://202.119.81.112:9080"
    portal_login_url: str = "http://202.119.81.113:8080"
    portal_login_path: str = "/"
    portal_lessons_path: str = "/njlgdx/xskb/xskb_list.do"
    portal_grades_path: str = "/njlgdx/kscj/cjcx_list"
    portal_exams_path: str = "/njlgdx/xspjgl/kscjcx_list.do"

    # 请求配置
    portal_timeout: int = 20
    captcha_max_attempts: int = 3

    # 缓存配置
    cache_dir: str = ""
    cache_ttl_minutes: int = 30

    # 课表缓存 TTL（小时）
    schedule_cache_ttl_hours: int = 6
    # 成绩缓存 TTL（小时）
    grades_cache_ttl_hours: int = 3
    # 考试缓存 TTL（小时）
    exams_cache_ttl_hours: int = 3


def load_config() -> Config:
    """从环境变量加载配置"""
    cache_dir = os.environ.get("CACHE_DIR", "")
    if not cache_dir:
        cache_dir = str(Path.home() / ".njust-schedule-mcp" / "cache")

    return Config(
        portal_username=os.environ.get("PORTAL_USERNAME", ""),
        portal_password=os.environ.get("PORTAL_PASSWORD", ""),
        portal_base_url=os.environ.get(
            "PORTAL_BASE_URL", "http://202.119.81.112:9080"
        ),
        portal_login_url=os.environ.get(
            "PORTAL_LOGIN_URL", "http://202.119.81.113:8080"
        ),
        portal_login_path=os.environ.get("PORTAL_LOGIN_PATH", "/"),
        portal_lessons_path=os.environ.get(
            "PORTAL_LESSONS_PATH", "/njlgdx/xskb/xskb_list.do"
        ),
        portal_grades_path=os.environ.get(
            "PORTAL_GRADES_PATH", "/njlgdx/kscj/cjcx_list"
        ),
        portal_exams_path=os.environ.get(
            "PORTAL_EXAMS_PATH", "/njlgdx/xspjgl/kscjcx_list.do"
        ),
        portal_timeout=int(os.environ.get("PORTAL_TIMEOUT", "20")),
        captcha_max_attempts=int(os.environ.get("CAPTCHA_MAX_ATTEMPTS", "3")),
        cache_dir=cache_dir,
        cache_ttl_minutes=int(os.environ.get("CACHE_TTL_MINUTES", "30")),
        schedule_cache_ttl_hours=int(
            os.environ.get("SCHEDULE_CACHE_TTL_HOURS", "6")
        ),
        grades_cache_ttl_hours=int(
            os.environ.get("GRADES_CACHE_TTL_HOURS", "3")
        ),
        exams_cache_ttl_hours=int(
            os.environ.get("EXAMS_CACHE_TTL_HOURS", "3")
        ),
    )


# 全局配置单例
_config: Config | None = None


def get_config() -> Config:
    """获取全局配置"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: Config) -> None:
    """设置全局配置（用于测试）"""
    global _config
    _config = config
