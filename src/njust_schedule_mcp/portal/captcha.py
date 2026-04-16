"""验证码识别模块 - 使用 ddddocr 识别教务系统验证码

参考 cat-schedule 的 captcha.py 实现，采用多变体图像预处理 + 投票策略提高识别率。
"""

from __future__ import annotations

import io
import logging
from collections import Counter
from dataclasses import dataclass

from PIL import Image

logger = logging.getLogger(__name__)

# 验证码允许的字符集（参考 cat-schedule）
CAPTCHA_CHARSET = set(
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
)

# 验证码预期长度（4 位，参考 cat-schedule）
CAPTCHA_EXPECTED_LENGTH = 4


@dataclass
class CaptchaResult:
    """验证码识别结果"""

    code: str
    confidence: float = 0.0


def _normalize_captcha_code(value: str | None) -> str:
    """规范化验证码识别结果：去除空白、过滤非法字符、截断到预期长度"""
    import re

    text = re.sub(r"\s+", "", (value or ""))
    text = "".join(char for char in text if char in CAPTCHA_CHARSET)
    if CAPTCHA_EXPECTED_LENGTH and len(text) > CAPTCHA_EXPECTED_LENGTH:
        text = text[:CAPTCHA_EXPECTED_LENGTH]
    return text


def _image_to_bytes(img: Image.Image) -> bytes:
    """将 PIL Image 转换为 PNG 字节"""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class CaptchaSolver:
    """验证码识别器，基于 ddddocr，采用多变体预处理 + 投票策略"""

    def __init__(self) -> None:
        try:
            import ddddocr  # noqa: F401

            self._ocr = ddddocr.DdddOcr(show_ad=False, beta=True)
            self._available = True
            logger.info("ddddocr 验证码识别器初始化成功 (beta 模式)")
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
        识别验证码图片（多变体预处理 + 投票策略）

        参考 cat-schedule 的 DdddOcrCaptchaSolver：
        对输入图像生成 5 种变体，分别识别后投票选择最优结果。

        Args:
            image_bytes: 验证码图片的二进制数据

        Returns:
            CaptchaResult: 识别结果
        """
        if not self._available:
            raise RuntimeError("ddddocr 未安装，无法识别验证码")

        img = Image.open(io.BytesIO(image_bytes))

        # 生成多种图像变体（参考 cat-schedule）
        variants: list[tuple[str, bytes]] = []

        # 1. 原图
        variants.append(("original", image_bytes))

        # 2. 灰度
        gray = img.convert("L")
        variants.append(("grayscale", _image_to_bytes(gray)))

        # 3. 阈值 150
        bw150 = gray.point(lambda x: 0 if x < 150 else 255, "1")
        variants.append(("threshold-150", _image_to_bytes(bw150.convert("L"))))

        # 4. 阈值 180
        bw180 = gray.point(lambda x: 0 if x < 180 else 255, "1")
        variants.append(("threshold-180", _image_to_bytes(bw180.convert("L"))))

        # 5. 反色阈值
        inverted = gray.point(lambda x: 255 - x)
        bw_inv = inverted.point(lambda x: 0 if x < 150 else 255, "1")
        variants.append(("invert-threshold", _image_to_bytes(bw_inv.convert("L"))))

        # 分别识别，投票选择最优结果
        candidates: list[str] = []
        for variant_name, variant_bytes in variants:
            try:
                raw_code = self._ocr.classification(variant_bytes)
                code = _normalize_captcha_code(raw_code)
                if code:
                    candidates.append(code)
                    logger.debug("变体 %s 识别: %s -> %s", variant_name, raw_code, code)
            except Exception as e:
                logger.debug("变体 %s 识别失败: %s", variant_name, e)

        if not candidates:
            return CaptchaResult(code="", confidence=0.0)

        # 投票：选择出现次数最多的结果
        counter = Counter(candidates)
        best_code, best_count = counter.most_common(1)[0]
        confidence = best_count / len(candidates)

        # 长度不符时降低置信度
        if CAPTCHA_EXPECTED_LENGTH and len(best_code) != CAPTCHA_EXPECTED_LENGTH:
            confidence *= 0.65

        logger.debug(
            "验证码投票结果: %s (置信度: %.2f, %d/%d 一致)",
            best_code, confidence, best_count, len(candidates),
        )

        return CaptchaResult(code=best_code, confidence=confidence)


# 全局单例
_captcha_solver: CaptchaSolver | None = None


def get_captcha_solver() -> CaptchaSolver:
    """获取全局验证码识别器单例"""
    global _captcha_solver
    if _captcha_solver is None:
        _captcha_solver = CaptchaSolver()
    return _captcha_solver
