#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Douyin API Wrapper
封装抖音视频数据获取API
"""

import re
import logging
import time
import requests
from typing import Dict, Optional, List


class DouyinAPI:
    """抖音API客户端"""

    def __init__(self, api_key: str, api_url: Optional[str] = "https://api.tikhub.io/api/v1/douyin/web/fetch_video_detail"):
        """
        初始化API客户端

        Args:
            api_key: API密钥
            api_url: API端点URL（可选，默认为单个视频详情接口）
        """
        self.api_key = api_key
        self.api_url = api_url
        self.logger = logging.getLogger(__name__)

    def _resolve_redirects(self, url: str) -> str:
        """解析短链接重定向"""
        if "v.douyin.com" in url or "douyin.com/share/" in url:
            try:
                self.logger.info(f"正在解析短链接: {url}")
                resp = requests.head(url, allow_redirects=True, timeout=10)
                return resp.url
            except Exception as e:
                self.logger.warning(f"解析重定向失败: {e}")
        return url

    def _extract_aweme_id(self, input_str: str) -> Optional[str]:
        """
        从输入字符串中提取视频ID
        支持：纯ID、URL、包含ID的文本
        """
        input_str = str(input_str).strip()

        # 1. 尝试解析短链接
        if "http" in input_str:
            url_match = re.search(r'(https?://[^\s]+)', input_str)
            if url_match:
                full_url = self._resolve_redirects(url_match.group(1))
                input_str = full_url

        # 2. 泛匹配：查找任何19位数字（抖音视频ID通常是19位数字）
        match = re.search(r'\d{19}', input_str)
        if match:
            return match.group(0)

        # 3. 兼容旧的匹配规则 (以防ID长度变化)
        patterns = [
            r'/video/(\d+)',
            r'aweme_id=(\d+)',
            r'modal_id=(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, input_str)
            if match:
                return match.group(1)

        return None

    def fetch_video(self, url: str) -> Optional[Dict]:
        """
        获取单个视频数据（支持TikHub API）

        Args:
            url: 抖音视频URL或视频ID

        Returns:
            视频数据字典，失败返回None
        """
        if not self.api_url:
            self.logger.warning("API URL未配置")
            return None

        try:
            aweme_id = self._extract_aweme_id(url)
            if not aweme_id:
                self.logger.error(f"无法从URL提取视频ID: {url}")
                return None

            self.logger.info(f"正在获取视频数据: {aweme_id}")

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            params = {"aweme_id": aweme_id}

            data = None
            response = None

            # 重试逻辑
            for attempt in range(3):
                try:
                    self.logger.info(f"请求尝试 {attempt+1}/3: {aweme_id}")
                    response = requests.get(
                        self.api_url,
                        headers=headers,
                        params=params,
                        timeout=30
                    )

                    if response.status_code == 200:
                        data = response.json()
                        if data:
                            break
                    elif response.status_code == 404:
                        # 回退到 Mobile API V3
                        self.logger.info(f"Web API 404, 尝试 Mobile API V3 回退...")
                        try:
                            mobile_url = "https://api.tikhub.io/api/v1/douyin/app/v3/fetch_one_video"
                            mobile_resp = requests.get(
                                mobile_url,
                                headers=headers,
                                params={"aweme_id": aweme_id},
                                timeout=20
                            )

                            if mobile_resp.status_code == 200:
                                mobile_data = mobile_resp.json()
                                if mobile_data.get("code") == 200 and mobile_data.get("data", {}).get("aweme_detail"):
                                    self.logger.info(f"Mobile API 回退成功: {aweme_id}")
                                    data = mobile_data
                                    break
                        except Exception as fb_err:
                            self.logger.warning(f"回退失败: {fb_err}")

                        # 如果回退也失败，返回"已下架"结构
                        try:
                            err_data = response.json()
                            if err_data.get("detail") == "Not Found":
                                self.logger.info(f"视频 {aweme_id} 已下架")
                                return {
                                    "code": 0,
                                    "data": {
                                        "aweme_id": aweme_id,
                                        "desc": "视频不存在或已下架",
                                        "create_time": 0,
                                        "status": {"is_delete": True},
                                        "statistics": {},
                                        "author": {},
                                        "share_url": ""
                                    }
                                }
                        except Exception:
                            pass

                        self.logger.warning(f"API 返回状态 {response.status_code} (尝试 {attempt+1})")
                    else:
                        self.logger.warning(f"API 返回状态 {response.status_code} (尝试 {attempt+1})")

                except requests.exceptions.Timeout:
                    self.logger.warning(f"请求超时 (尝试 {attempt+1})")
                except requests.exceptions.RequestException as e:
                    self.logger.warning(f"请求失败: {e} (尝试 {attempt+1})")

                if attempt < 2:
                    time.sleep(2)

            if response is None:
                self.logger.error("3次尝试后仍无法连接API")
                return None

            if not data or data.get('code') != 200:
                self.logger.error(f"API返回错误: {data.get('message', '未知错误') if data else 'Empty Data'}")
                return None

            # 转换TikHub格式
            data_data = data.get('data', {})
            tik_data = data_data.get('aweme_detail', {})

            if not tik_data:
                filter_detail = data_data.get('filter_detail', {})
                if filter_detail:
                    self.logger.warning(f"视频可能已删除或不可见: {filter_detail.get('detail_msg')}")
                    return {
                        "code": 0,
                        "data": {
                            "aweme_id": filter_detail.get('aweme_id', aweme_id),
                            "desc": "视频已下架",
                            "create_time": 0,
                            "status": {"is_delete": True},
                            "statistics": {},
                            "author": {},
                            "share_url": ""
                        }
                    }

                self.logger.error("API返回数据中缺少 aweme_detail")
                return None

            # 补充统计数据（播放量）
            self._supplement_statistics(aweme_id, tik_data, headers)

            # 格式转换
            share_url_value = f"https://www.douyin.com/video/{aweme_id}" if aweme_id else url

            converted_data = {
                "code": 0,
                "data": {
                    "aweme_id": tik_data.get('aweme_id'),
                    "share_url": share_url_value,
                    "desc": tik_data.get('desc'),
                    "create_time": tik_data.get('create_time'),
                    "duration": tik_data.get('video', {}).get('duration', 0),
                    "author": {
                        "nickname": (tik_data.get('author') or {}).get('nickname'),
                        "unique_id": (tik_data.get('author') or {}).get('unique_id')
                    },
                    "statistics": {
                        "digg_count": tik_data.get('statistics', {}).get('digg_count', 0),
                        "comment_count": tik_data.get('statistics', {}).get('comment_count', 0),
                        "share_count": tik_data.get('statistics', {}).get('share_count', 0),
                        "collect_count": tik_data.get('statistics', {}).get('collect_count', 0),
                        "play_count": tik_data.get('statistics', {}).get('play_count', 0)
                    },
                    "text_extra": tik_data.get('text_extra', []),
                    "promotions": []
                }
            }

            self.logger.info(f"数据获取成功")
            return converted_data

        except requests.exceptions.RequestException as e:
            self.logger.error(f"API请求失败: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"处理响应失败: {str(e)}")
            return None

    def _supplement_statistics(self, aweme_id: str, tik_data: Dict, headers: Dict):
        """补充统计数据（特别是播放量）"""
        for attempt in range(3):
            try:
                stats_url = "https://api.tikhub.io/api/v1/douyin/app/v3/fetch_video_statistics"
                self.logger.info(f"正在补充统计数据: {aweme_id} (尝试 {attempt+1})")

                stats_response = requests.get(
                    stats_url,
                    headers=headers,
                    params={"aweme_ids": aweme_id},
                    timeout=10
                )

                if stats_response.status_code == 200:
                    stats_data = stats_response.json()
                    if stats_data.get('code') == 200:
                        stats_list = stats_data.get('data', {}).get('statistics_list', [])
                        if stats_list:
                            app_stats = stats_list[0]
                            self.logger.info(f"获取到播放量: {app_stats.get('play_count')}")

                            if 'statistics' not in tik_data:
                                tik_data['statistics'] = {}

                            # 采用最大值策略
                            for key in ['play_count', 'digg_count', 'comment_count', 'share_count', 'collect_count']:
                                app_val = app_stats.get(key, 0)
                                web_val = tik_data['statistics'].get(key, 0)
                                final_val = max(app_val, web_val)
                                if final_val > 0:
                                    tik_data['statistics'][key] = final_val

                            break
            except Exception as e:
                self.logger.warning(f"获取补充统计数据失败 (尝试 {attempt+1}/3): {e}")

            if attempt < 2:
                time.sleep(1)

    def fetch_videos_batch(self, aweme_ids: List[str]) -> Dict[str, Optional[Dict]]:
        """
        批量获取多个视频数据

        Args:
            aweme_ids: 视频ID列表

        Returns:
            字典，key为aweme_id，value为视频数据（失败则为None）
        """
        if not aweme_ids:
            return {}

        results = {}

        try:
            web_batch_url = "https://api.tikhub.io/api/v1/douyin/web/fetch_multi_video"

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            batch_size = 50
            for i in range(0, len(aweme_ids), batch_size):
                batch_ids = aweme_ids[i:i+batch_size]

                self.logger.info(f"[Web API] 批量获取 {len(batch_ids)} 个视频基础数据...")

                response = requests.post(
                    web_batch_url,
                    headers=headers,
                    json=batch_ids,
                    timeout=60
                )

                if response.status_code == 200:
                    try:
                        data = response.json()
                        if data.get('code') == 200:
                            data_field = data.get('data')

                            if isinstance(data_field, str):
                                import json as json_module
                                try:
                                    data_field = json_module.loads(data_field)
                                except Exception:
                                    data_field = None

                            aweme_list = []
                            if data_field:
                                if isinstance(data_field, list):
                                    aweme_list = data_field
                                else:
                                    aweme_list = data_field.get('aweme_list') or data_field.get('aweme_details') or []

                            if aweme_list:
                                for aweme_detail in aweme_list:
                                    aweme_id = str(aweme_detail.get('aweme_id'))
                                    if not aweme_id:
                                        continue

                                    share_url_value = f"https://www.douyin.com/video/{aweme_id}"

                                    converted_data = {
                                        "code": 0,
                                        "data": {
                                            "aweme_id": aweme_detail.get('aweme_id'),
                                            "share_url": share_url_value,
                                            "desc": aweme_detail.get('desc'),
                                            "create_time": aweme_detail.get('create_time'),
                                            "duration": aweme_detail.get('video', {}).get('duration', 0),
                                            "author": {
                                                "nickname": (aweme_detail.get('author') or {}).get('nickname'),
                                                "unique_id": (aweme_detail.get('author') or {}).get('unique_id')
                                            },
                                            "_data_source": "Web API",
                                            "statistics": {
                                                "digg_count": aweme_detail.get('statistics', {}).get('digg_count', 0),
                                                "comment_count": aweme_detail.get('statistics', {}).get('comment_count', 0),
                                                "share_count": aweme_detail.get('statistics', {}).get('share_count', 0),
                                                "collect_count": aweme_detail.get('statistics', {}).get('collect_count', 0),
                                                "play_count": aweme_detail.get('statistics', {}).get('play_count', 0)
                                            },
                                            "text_extra": aweme_detail.get('text_extra', []),
                                            "promotions": []
                                        }
                                    }

                                    results[aweme_id] = converted_data
                    except Exception as e:
                        self.logger.error(f"[Web API] 解析异常: {e}")
                else:
                    self.logger.error(f"[Web API] HTTP错误: {response.status_code}")

                # 标记缺失视频，尝试单条回退
                for aweme_id in batch_ids:
                    if aweme_id not in results:
                        results[aweme_id] = None
                        self.logger.warning(f"[Web API] 视频 {aweme_id} 未返回，尝试单条获取回退...")

                        fallback_url = f"https://www.douyin.com/video/{aweme_id}"
                        single_data = self.fetch_video(fallback_url)

                        if single_data and single_data.get('code') == 0:
                            self.logger.info(f"[Fallback] 成功通过单条接口挽救视频 {aweme_id}")
                            results[aweme_id] = single_data
                        else:
                            self.logger.error(f"[Fallback] 单条接口也未能获取视频 {aweme_id}")

            # 补充播放量
            successful_ids = [vid for vid, data in results.items() if data is not None]

            if successful_ids:
                self.logger.info(f"[App API] 补充 {len(successful_ids)} 个视频的播放量...")

                app_stats_url = "https://api.tikhub.io/api/v1/douyin/app/v3/fetch_video_statistics"

                for i in range(0, len(successful_ids), 2):
                    batch_ids = successful_ids[i:i+2]

                    try:
                        stats_response = requests.get(
                            app_stats_url,
                            headers=headers,
                            params={"aweme_ids": ",".join(batch_ids)},
                            timeout=30
                        )

                        if stats_response.status_code == 200:
                            stats_data = stats_response.json()
                            if stats_data.get('code') == 200:
                                stats_list = stats_data.get('data', {}).get('statistics_list', [])

                                for stat in stats_list:
                                    vid = str(stat.get('aweme_id'))
                                    try:
                                        play_count = int(stat.get('play_count', 0))
                                    except Exception:
                                        play_count = 0

                                    if vid in results and results[vid]:
                                        results[vid]['data']['statistics']['play_count'] = play_count
                                        results[vid]['data']['_data_source'] = "App API"
                                        self.logger.info(f"[App API] 视频 {vid} 播放量更新: {play_count}")

                    except Exception as e:
                        self.logger.error(f"[App API] 补充播放量失败: {e}")

            self.logger.info(f"批量获取完成：成功 {sum(1 for v in results.values() if v)} / {len(aweme_ids)}")
            return results

        except Exception as e:
            self.logger.error(f"批量获取失败: {str(e)}")
            return {aweme_id: None for aweme_id in aweme_ids}

    def translate_content(self, content: str, target_lang: str = "zh-Hans") -> Optional[Dict]:
        """
        翻译内容（使用 TikHub 翻译 API）

        Args:
            content: 需要翻译的内容（最大5000字符）
            target_lang: 目标语言代码，默认简体中文
                - zh-Hans: 简体中文
                - zh-Hant: 繁体中文
                - en: 英语
                - ja: 日语
                - ko: 韩语
                - 等等...

        Returns:
            翻译结果字典，失败返回 None
        """
        if not content:
            self.logger.warning("翻译内容为空")
            return None

        # 限制内容长度
        if len(content) > 5000:
            self.logger.warning(f"内容超过5000字符，将截断")
            content = content[:5000]

        try:
            translate_url = "https://api.tikhub.io/api/v1/tiktok/app/v3/fetch_content_translate"

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "trg_lang": target_lang,
                "src_content": content
            }

            self.logger.info(f"正在翻译内容到 {target_lang}...")

            response = requests.post(
                translate_url,
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 200:
                    self.logger.info("翻译成功")
                    return {
                        "success": True,
                        "source": content,
                        "target_lang": target_lang,
                        "translated": data.get('data'),
                        "raw_response": data
                    }
                else:
                    self.logger.error(f"翻译API返回错误: {data.get('message')}")
                    return {
                        "success": False,
                        "error": data.get('message'),
                        "source": content
                    }
            else:
                self.logger.error(f"翻译API HTTP错误: {response.status_code}")
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "source": content
                }

        except Exception as e:
            self.logger.error(f"翻译失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "source": content
            }
