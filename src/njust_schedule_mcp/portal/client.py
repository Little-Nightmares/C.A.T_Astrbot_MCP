"""教务系统 HTTP 客户端 - 登录、抓取、会话管理

参考 cat-schedule 项目的 client.py 实现。
"""

from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests

from ..config import get_config
from .captcha import CaptchaSolver, get_captcha_solver
from .parsers import (
    ExamsParseResult,
    GradesParseResult,
    LessonsParseResult,
    extract_login_error,
    is_login_page,
    parse_exams_html,
    parse_grades_html,
    parse_lessons_html,
    parse_login_form,
)

logger = logging.getLogger(__name__)


class PortalError(Exception):
    """教务系统操作异常"""

    def __init__(self, message: str, code: str = "PORTAL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class PortalSessionExpiredError(Exception):
    """教务系统会话过期"""

    pass


@dataclass
class PortalLoginResult:
    """登录结果"""

    cookies: dict[str, str]


@dataclass
class PortalPageResult:
    """页面抓取结果"""

    html: str
    cookies: dict[str, str]


def decode_response(response: requests.Response) -> str:
    """解码响应内容"""
    response.encoding = response.encoding or response.apparent_encoding or "utf-8"
    return response.text


class PortalClient:
    """NJUST 教务系统客户端"""

    def __init__(
        self,
        username: str = "",
        password: str = "",
        cache_dir: str = "",
    ) -> None:
        config = get_config()
        self.base_url = config.portal_base_url
        # 支持多个登录 URL（逗号分隔），自动回退
        self.login_base_urls = [
            u.strip() for u in config.portal_login_url.split(",") if u.strip()
        ]
        self.login_path = config.portal_login_path
        self.lessons_path = config.portal_lessons_path
        self.grades_path = config.portal_grades_path
        self.exams_path = config.portal_exams_path
        self.timeout = config.portal_timeout
        self.captcha_max_attempts = config.captcha_max_attempts

        self._username = username or config.portal_username
        self._password = password or config.portal_password
        self._captcha_solver: CaptchaSolver | None = None
        self._session_cookies: dict[str, str] = {}
        self._cache_dir = Path(cache_dir or config.cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        # 尝试加载已保存的会话
        self._load_session()

    @property
    def captcha_solver(self) -> CaptchaSolver:
        """获取验证码识别器（延迟初始化）"""
        if self._captcha_solver is None:
            self._captcha_solver = get_captcha_solver()
        return self._captcha_solver

    def _session_file(self) -> Path:
        """会话文件路径"""
        return self._cache_dir / "session.json"

    def _load_session(self) -> None:
        """从文件加载会话"""
        session_file = self._session_file()
        if session_file.is_file():
            try:
                data = json.loads(session_file.read_text(encoding="utf-8"))
                self._session_cookies = data.get("cookies", {})
                if self._session_cookies:
                    logger.info("从文件恢复会话: %d 个 cookie", len(self._session_cookies))
            except (json.JSONDecodeError, KeyError):
                self._session_cookies = {}

    def _save_session(self) -> None:
        """保存会话到文件"""
        session_file = self._session_file()
        data = {"cookies": self._session_cookies}
        session_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        # 限制文件权限为仅 owner 可读写
        session_file.chmod(0o600)

    def _clear_session(self) -> None:
        """清除会话"""
        self._session_cookies = {}
        session_file = self._session_file()
        if session_file.is_file():
            session_file.unlink()

    def _make_session(self, cookies: dict[str, str] | None = None) -> requests.Session:
        """创建 HTTP 会话"""
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            }
        )
        if cookies:
            session.cookies.update(cookies)
        return session

    def _assert_not_login_page(self, html: str) -> None:
        """检查是否被重定向到登录页"""
        if is_login_page(html):
            self._clear_session()
            raise PortalSessionExpiredError("教务系统会话已过期")

    def _looks_like_credential_error(self, message: str | None) -> bool:
        """判断是否为凭据错误（非验证码错误）"""
        message = (message or "").lower()
        if not message:
            return False
        if any(
            token in message
            for token in ["captcha", "验证码", "校验码", "随机码"]
        ):
            return False
        return any(
            token in message
            for token in ["密码", "账号", "帐户", "用户名", "user"]
        )

    def _origin_for(self, url: str) -> str:
        """提取 URL 的 origin"""
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}"

    def _append_cache_buster(self, url: str) -> str:
        """添加缓存破坏参数"""
        parts = urlsplit(url)
        query = parse_qsl(parts.query, keep_blank_values=True)
        query.append(("t", secrets.token_hex(8)))
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )

    def _ensure_logged_in(self) -> dict[str, str]:
        """确保已登录，返回有效的 cookies"""
        if self._session_cookies.get("JSESSIONID"):
            return self._session_cookies
        # 自动登录
        result = self.login()
        return result.cookies

    def _fetch_with_retry(self, fetch_fn, *args, **kwargs):
        """执行请求，会话过期时自动重新登录并重试一次"""
        try:
            return fetch_fn(*args, **kwargs)
        except PortalSessionExpiredError:
            logger.info("会话已过期，自动重新登录...")
            self._session_cookies.clear()
            self._session_file.unlink(missing_ok=True)
            result = self.login()
            self._session_cookies = result.cookies
            return fetch_fn(*args, **kwargs)

    def login(self, username: str = "", password: str = "") -> PortalLoginResult:
        """
        登录教务系统

        Args:
            username: 学号（为空使用初始化时的值）
            password: 密码（为空使用初始化时的值）

        Returns:
            PortalLoginResult: 登录结果

        Raises:
            PortalError: 登录失败
        """
        username = username or self._username
        password = password or self._password

        if not username or not password:
            raise PortalError("未提供教务系统账号或密码", "MISSING_CREDENTIALS")

        last_error = ""
        for login_base in self.login_base_urls:
            login_url = urljoin(
                login_base + "/", self.login_path.lstrip("/")
            )
            logger.info("尝试登录: %s", login_base)
            try:
                return self._try_login(login_url, username, password)
            except PortalError as e:
                last_error = str(e)
                if e.code in ("CREDENTIAL_ERROR", "MISSING_CREDENTIALS"):
                    raise
                logger.warning("登录地址 %s 不可用: %s", login_base, e)
                continue

        raise PortalError(
            f"所有登录地址均不可用: {last_error}", "NETWORK_ERROR"
        )

    def _try_login(
        self,
        login_url: str,
        username: str,
        password: str,
    ) -> PortalLoginResult:
        """尝试通过指定 URL 登录"""
        last_message = "教务系统登录失败，请检查账号、密码或验证码识别"

        for attempt in range(1, self.captcha_max_attempts + 1):
            session = self._make_session()
            try:
                response = session.get(login_url, timeout=self.timeout)
            except requests.RequestException as e:
                raise PortalError(f"无法访问教务系统登录页: {e}", "NETWORK_ERROR")

            html = decode_response(response)

            try:
                form = parse_login_form(html)
            except ValueError as e:
                raise PortalError(str(e), "LOGIN_FORM_NOT_FOUND")

            logger.info(
                "登录表单: method=%s action=%s username_field=%s captcha_field=%s",
                form.method,
                form.action,
                form.username_field,
                form.captcha_field,
            )

            # 识别验证码
            captcha_value = ""
            if form.captcha_image_url:
                try:
                    captcha_url = self._append_cache_buster(
                        urljoin(response.url, form.captcha_image_url)
                    )
                    captcha_response = session.get(
                        captcha_url,
                        timeout=self.timeout,
                        headers={
                            "Referer": response.url,
                            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                        },
                    )
                    solved = self.captcha_solver.solve(captcha_response.content)
                    captcha_value = solved.code
                    logger.debug(
                        "验证码识别 (第 %d/%d 次): %s (置信度: %.2f)",
                        attempt,
                        self.captcha_max_attempts,
                        captcha_value,
                        solved.confidence,
                    )
                except Exception as e:
                    logger.warning("验证码识别失败: %s", e)

            # 构造登录请求
            payload = {**form.hidden_fields}
            payload[form.username_field] = username
            payload[form.password_field] = password
            payload[form.captcha_field] = captcha_value

            post_url = urljoin(response.url, form.action)
            try:
                login_response = session.request(
                    form.method,
                    post_url,
                    data=payload,
                    timeout=self.timeout,
                    allow_redirects=True,
                    headers={
                        "Referer": response.url,
                        "Origin": self._origin_for(response.url),
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
            except requests.RequestException as e:
                raise PortalError(f"登录请求失败: {e}", "NETWORK_ERROR")

            login_html = decode_response(login_response)

            if not is_login_page(login_html):
                cookies = requests.utils.dict_from_cookiejar(session.cookies)
                if "JSESSIONID" not in cookies:
                    raise PortalError(
                        "未获取到教务系统会话 Cookie (JSESSIONID)",
                        "NO_SESSION",
                    )
                self._session_cookies = cookies
                self._save_session()
                logger.info("登录成功，会话已建立")
                return PortalLoginResult(cookies=cookies)

            last_message = extract_login_error(login_html) or last_message

            if self._looks_like_credential_error(last_message):
                raise PortalError(last_message, "CREDENTIAL_ERROR")

            if attempt < self.captcha_max_attempts:
                logger.warning(
                    "登录失败 (第 %d/%d 次)，重试中... %s",
                    attempt,
                    self.captcha_max_attempts,
                    last_message,
                )

        raise PortalError(last_message, "LOGIN_FAILED")

    def fetch_lessons(
        self, term: str | None = None
    ) -> PortalPageResult:
        """
        抓取课表页面

        Args:
            term: 学期（如 "2024-2025-2"），为空则查当前学期

        Returns:
            PortalPageResult: 页面结果
        """
        cookies = self._ensure_logged_in()
        session = self._make_session(cookies)
        url = urljoin(self.base_url + "/", self.lessons_path.lstrip("/"))

        try:
            response = session.get(
                url,
                params={"xnxq01id": term} if term else None,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise PortalError(f"获取课表失败: {e}", "NETWORK_ERROR")

        html = decode_response(response)
        self._assert_not_login_page(html)

        # 更新 cookies
        new_cookies = requests.utils.dict_from_cookiejar(session.cookies)
        self._session_cookies.update(new_cookies)
        self._save_session()

        return PortalPageResult(html=html, cookies=self._session_cookies)

    def fetch_grades(self) -> PortalPageResult:
        """
        抓取成绩页面

        Returns:
            PortalPageResult: 页面结果
        """
        cookies = self._ensure_logged_in()
        session = self._make_session(cookies)
        url = urljoin(self.base_url + "/", self.grades_path.lstrip("/"))

        try:
            response = session.post(
                url,
                data={
                    "kksj": "",
                    "kcxz": "",
                    "kcmc": "",
                    "xsfs": "max",
                },
                timeout=self.timeout,
                headers={
                    "Referer": url,
                    "Origin": self._origin_for(url),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
        except requests.RequestException as e:
            raise PortalError(f"获取成绩失败: {e}", "NETWORK_ERROR")

        html = decode_response(response)
        self._assert_not_login_page(html)

        new_cookies = requests.utils.dict_from_cookiejar(session.cookies)
        self._session_cookies.update(new_cookies)
        self._save_session()

        return PortalPageResult(html=html, cookies=self._session_cookies)

    def fetch_exams(self) -> PortalPageResult:
        """
        抓取考试安排页面

        Returns:
            PortalPageResult: 页面结果
        """
        cookies = self._ensure_logged_in()
        session = self._make_session(cookies)
        url = urljoin(self.base_url + "/", self.exams_path.lstrip("/"))

        try:
            response = session.get(url, timeout=self.timeout)
        except requests.RequestException as e:
            raise PortalError(f"获取考试安排失败: {e}", "NETWORK_ERROR")

        html = decode_response(response)
        self._assert_not_login_page(html)

        new_cookies = requests.utils.dict_from_cookiejar(session.cookies)
        self._session_cookies.update(new_cookies)
        self._save_session()

        return PortalPageResult(html=html, cookies=self._session_cookies)

    def get_lessons(self, term: str | None = None) -> LessonsParseResult:
        """获取并解析课表"""
        page = self._fetch_with_retry(self.fetch_lessons, term)
        return parse_lessons_html(page.html)

    def get_grades(self) -> GradesParseResult:
        """获取并解析成绩"""
        page = self._fetch_with_retry(self.fetch_grades)
        return parse_grades_html(page.html)

    def get_exams(self) -> ExamsParseResult:
        """获取并解析考试安排"""
        page = self._fetch_with_retry(self.fetch_exams)
        return parse_exams_html(page.html)
