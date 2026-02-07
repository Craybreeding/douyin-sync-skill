#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration Module for Douyin Sync Skill
使用环境变量进行配置
"""

import os


def get_config():
    """获取配置信息"""
    config = {
        # 飞书应用配置
        "feishu_app_id": os.environ.get("FEISHU_APP_ID"),
        "feishu_app_secret": os.environ.get("FEISHU_APP_SECRET"),

        # 抖音 API 配置
        "douyin_api_key": os.environ.get("DOUYIN_API_KEY"),
        "douyin_api_url": os.environ.get(
            "DOUYIN_API_URL",
            "https://api.tikhub.io/api/v1/douyin/web/fetch_video_detail"
        ),
    }

    return config


def validate_config(config, require_feishu=True):
    """
    验证配置完整性

    Args:
        config: 配置字典
        require_feishu: 是否需要飞书配置（单视频查询模式不需要）

    Returns:
        (bool, str): (是否有效, 错误信息)
    """
    missing = []

    if not config.get("douyin_api_key"):
        missing.append("DOUYIN_API_KEY")

    if require_feishu:
        if not config.get("feishu_app_id"):
            missing.append("FEISHU_APP_ID")
        if not config.get("feishu_app_secret"):
            missing.append("FEISHU_APP_SECRET")

    if missing:
        return False, f"缺少必需的环境变量: {', '.join(missing)}"

    return True, ""


# API URLs
FEISHU_OPEN_API_URL = "https://open.feishu.cn/open-apis/bitable/v1/apps"
AUTH_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
