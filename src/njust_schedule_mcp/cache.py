"""缓存管理模块 - 内存缓存 + JSON 文件持久化"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CacheManager:
    """缓存管理器，支持内存缓存和文件持久化"""

    def __init__(self, cache_dir: str, default_ttl_minutes: int = 30) -> None:
        """
        初始化缓存管理器

        Args:
            cache_dir: 缓存目录路径
            default_ttl_minutes: 默认缓存有效期（分钟）
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.default_ttl = timedelta(minutes=default_ttl_minutes)
        self._memory_cache: dict[str, tuple[Any, float]] = {}

    def _cache_file(self, key: str) -> Path:
        """获取缓存文件路径"""
        # 使用安全的文件名
        safe_key = key.replace("/", "_").replace("\\", "_").replace(" ", "_")
        return self.cache_dir / f"{safe_key}.json"

    def get(self, key: str, ttl: timedelta | None = None) -> dict | None:
        """
        读取缓存

        Args:
            key: 缓存键
            ttl: 自定义有效期（None 使用默认值）

        Returns:
            缓存数据，过期或不存在返回 None
        """
        effective_ttl = ttl or self.default_ttl

        # 先查内存缓存
        if key in self._memory_cache:
            data, timestamp = self._memory_cache[key]
            if datetime.now().timestamp() - timestamp < effective_ttl.total_seconds():
                logger.debug("内存缓存命中: %s", key)
                return data
            else:
                # 内存缓存过期，移除
                del self._memory_cache[key]

        # 查文件缓存
        cache_file = self._cache_file(key)
        if cache_file.is_file():
            try:
                file_data = json.loads(cache_file.read_text(encoding="utf-8"))
                timestamp = file_data.get("_timestamp", 0)
                if datetime.now().timestamp() - timestamp < effective_ttl.total_seconds():
                    logger.debug("文件缓存命中: %s", key)
                    result = file_data.get("data")
                    # 回填内存缓存
                    self._memory_cache[key] = (result, timestamp)
                    return result
                else:
                    logger.debug("文件缓存过期: %s", key)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("缓存文件读取失败: %s -> %s", cache_file, e)

        return None

    def set(self, key: str, data: Any, ttl: timedelta | None = None) -> None:
        """
        写入缓存

        Args:
            key: 缓存键
            data: 缓存数据（必须是 JSON 可序列化的）
            ttl: 自定义有效期（None 使用默认值）
        """
        now = datetime.now().timestamp()

        # 写入内存缓存
        self._memory_cache[key] = (data, now)

        # 写入文件缓存
        cache_file = self._cache_file(key)
        try:
            file_data = {"_timestamp": now, "data": data}
            cache_file.write_text(
                json.dumps(file_data, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            os.chmod(cache_file, 0o600)
            logger.debug("缓存写入: %s", key)
        except (TypeError, OSError) as e:
            logger.warning("缓存文件写入失败: %s -> %s", cache_file, e)

    def invalidate(self, key: str) -> None:
        """
        使缓存失效

        Args:
            key: 缓存键
        """
        # 清除内存缓存
        self._memory_cache.pop(key, None)

        # 清除文件缓存
        cache_file = self._cache_file(key)
        if cache_file.is_file():
            try:
                cache_file.unlink()
                logger.debug("缓存已清除: %s", key)
            except OSError as e:
                logger.warning("缓存文件删除失败: %s -> %s", cache_file, e)

    def invalidate_all(self) -> None:
        """清除所有缓存"""
        self._memory_cache.clear()
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
            except OSError:
                pass
        logger.info("所有缓存已清除")

    def get_raw(self, key: str) -> dict | None:
        """
        获取缓存数据（忽略 TTL），用于成绩快照等永久数据

        Args:
            key: 缓存键

        Returns:
            缓存数据
        """
        cache_file = self._cache_file(key)
        if cache_file.is_file():
            try:
                file_data = json.loads(cache_file.read_text(encoding="utf-8"))
                return file_data.get("data")
            except (json.JSONDecodeError, KeyError):
                pass
        return None

    def set_raw(self, key: str, data: Any) -> None:
        """
        设置缓存数据（忽略 TTL），用于成绩快照等永久数据

        Args:
            key: 缓存键
            data: 缓存数据
        """
        cache_file = self._cache_file(key)
        try:
            file_data = {"_timestamp": datetime.now().timestamp(), "data": data}
            cache_file.write_text(
                json.dumps(file_data, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            os.chmod(cache_file, 0o600)
        except (TypeError, OSError) as e:
            logger.warning("缓存文件写入失败: %s -> %s", cache_file, e)
