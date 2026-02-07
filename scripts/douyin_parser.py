#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Douyin Data Parser
将抖音API响应解析为飞书多维表格格式或JSON输出
"""

import time
import logging
from typing import Dict, List, Optional


class DouyinParser:
    """抖音数据解析器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def parse_video(self, api_response: Dict) -> Optional[Dict]:
        """
        解析视频数据

        Args:
            api_response: API返回的完整响应

        Returns:
            飞书表格格式的记录字典
        """
        try:
            video_data = api_response.get('data', {})

            if not video_data:
                self.logger.error("API响应中没有数据")
                return None

            video_url = video_data.get('share_url') or ''

            # 处理视频下架/失效逻辑
            is_deleted = False
            status_obj = video_data.get('status', {})
            if status_obj and status_obj.get('is_delete') is True:
                is_deleted = True

            desc = video_data.get('desc') or ''
            aweme_id = str(video_data.get('aweme_id') or '')

            if is_deleted or (aweme_id and not desc and not video_data.get('create_time')):
                desc = "视频已下架"

            result = {
                "视频ID": aweme_id,
                "视频链接": {"text": "查看视频", "link": video_url} if video_url else None,
                "标题描述": desc,
                "作者昵称": (video_data.get('author') or {}).get('nickname') or '',
                "作者ID": (video_data.get('author') or {}).get('unique_id') or '',
                "发布时间": self._timestamp_to_datetime(video_data.get('create_time', 0)),
                "视频时长(秒)": round((video_data.get('duration') or 0) / 1000, 2),
                "采集时间": int(time.time() * 1000),
            }

            # 提取统计数据
            stats = video_data.get('statistics', {})
            try:
                result.update({
                    "播放量": int(stats.get('play_count', 0)),
                    "点赞数": int(stats.get('digg_count', 0)),
                    "评论数": int(stats.get('comment_count', 0)),
                    "分享数": int(stats.get('share_count', 0)),
                    "收藏数": int(stats.get('collect_count', 0)),
                })
            except (ValueError, TypeError) as e:
                self.logger.error(f"统计数据转换失败: {e}")
                result.update({
                    "播放量": 0, "点赞数": 0, "评论数": 0, "分享数": 0, "收藏数": 0
                })

            # 数据来源
            data_source = video_data.get('_data_source', 'Web API')
            result["数据来源"] = data_source

            # 话题标签
            result["话题标签"] = self._extract_hashtags(video_data.get('text_extra', []))

            # 商品信息
            promotions = video_data.get('promotions', [])
            if promotions and len(promotions) > 0:
                result["是否挂车"] = True
                product = promotions[0]
                result["商品标题"] = product.get('title', '')
                result["商品价格(元)"] = round(product.get('price', 0) / 100, 2)
                result["商品销量"] = product.get('sales', 0)
                product_url = product.get('url', '')
                result["商品链接"] = {"text": "查看商品", "link": product_url} if product_url else None
            else:
                result["是否挂车"] = False
                result["商品标题"] = ""
                result["商品价格(元)"] = 0
                result["商品销量"] = 0
                result["商品链接"] = None

            self.logger.info(f"数据解析成功: {result['标题描述'][:30] if result['标题描述'] else '无标题'}...")

            return result

        except Exception as e:
            self.logger.error(f"数据解析失败: {str(e)}")
            return None

    def parse_video_simple(self, api_response: Dict) -> Optional[Dict]:
        """
        解析视频数据（简化版，用于单视频查询的JSON输出）

        Args:
            api_response: API返回的完整响应

        Returns:
            简化的视频数据字典
        """
        try:
            video_data = api_response.get('data', {})

            if not video_data:
                return None

            is_deleted = False
            status_obj = video_data.get('status', {})
            if status_obj and status_obj.get('is_delete') is True:
                is_deleted = True

            stats = video_data.get('statistics', {})

            return {
                "aweme_id": str(video_data.get('aweme_id') or ''),
                "url": video_data.get('share_url') or f"https://www.douyin.com/video/{video_data.get('aweme_id')}",
                "title": video_data.get('desc') or ("视频已下架" if is_deleted else ''),
                "author": {
                    "nickname": (video_data.get('author') or {}).get('nickname') or '',
                    "unique_id": (video_data.get('author') or {}).get('unique_id') or ''
                },
                "create_time": video_data.get('create_time', 0),
                "duration_seconds": round((video_data.get('duration') or 0) / 1000, 2),
                "statistics": {
                    "play_count": int(stats.get('play_count', 0)),
                    "digg_count": int(stats.get('digg_count', 0)),
                    "comment_count": int(stats.get('comment_count', 0)),
                    "share_count": int(stats.get('share_count', 0)),
                    "collect_count": int(stats.get('collect_count', 0)),
                },
                "hashtags": self._extract_hashtags(video_data.get('text_extra', [])),
                "is_deleted": is_deleted,
                "data_source": video_data.get('_data_source', 'Web API'),
                "fetched_at": int(time.time())
            }

        except Exception as e:
            self.logger.error(f"数据解析失败: {str(e)}")
            return None

    def _timestamp_to_datetime(self, timestamp: int) -> int:
        """时间戳转毫秒时间戳（飞书日期字段格式）"""
        if not timestamp:
            return 0
        try:
            return int(timestamp) * 1000
        except Exception:
            return 0

    def _extract_hashtags(self, text_extra: List[Dict]) -> str:
        """提取话题标签"""
        hashtags = []
        for item in text_extra:
            if item.get('type') == 1:
                tag = item.get('hashtag_name', '')
                if tag:
                    hashtags.append(f"#{tag}")
        return " ".join(hashtags)
