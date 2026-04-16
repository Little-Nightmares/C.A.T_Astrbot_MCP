"""验证码识别模块 - 使用 ddddocr 识别教务系统验证码"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CaptchaResult:
    """验证码识别结果"""

    code: str
    confidence: float = 0.0


class CaptchaSolver:
    """验证码识别器，基于 ddddocr"""

    def __init__(self) -> None:
        try:
            import ddddocr  # noqa: F401

            self._ocr = ddddocr.DdddOcr(show_ad=False)
            self._available = True
            logger.info("ddddocr 验证码识别器初始化成功")
        except ImportError:
            self._ocr = None
            self._available = False
            logger.warning(
                "ddddocr 未安装，验证码识别不可用。请运行: pip install ddddocr"
            )

    @property
    def available(self) -> bool:
        """验证码识别器是否可用"""
        return self._available

    def solve(self, image_bytes: bytes) -> CaptchaResult:
        """
        识别验证码图片

        Args:
            image_bytes: 验证码图片的二进制数据

        Returns:
            CaptchaResult: 识别结果
        """
        if not self._available:
            raise RuntimeError("ddddocr 未安装，无法识别验证码")

        code = self._ocr.classification(image_bytes)
        logger.debug("验证码识别结果: %s", code)

        return CaptchaResult(code=code.strip(), confidence=1.0)


# 全局单例
_captcha_solver: CaptchaSolver | None = None


def get_captcha_solver() -> CaptchaSolver:
    """获取全局验证码识别器单例"""
    global _captcha_solver
    if _captcha_solver is None:
        _captcha_solver = CaptchaSolver()
    return _captcha_solver
