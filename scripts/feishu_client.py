#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Feishu Bitable Client
飞书多维表格客户端（简化版，仅保留同步所需功能）
"""

import json
import logging
import requests
from typing import List, Dict, Optional

from config import FEISHU_OPEN_API_URL, AUTH_URL


class FeishuClient:
    """飞书多维表格客户端"""

    def __init__(self, app_id: str, app_secret: str):
        """
        初始化客户端

        Args:
            app_id: 飞书应用 App ID
            app_secret: 飞书应用 App Secret
        """
        self.app_id = app_id
        self.app_secret = app_secret
        self.tenant_access_token = None
        self.headers = {"Content-Type": "application/json; charset=utf-8"}
        self.logger = logging.getLogger(__name__)

    def get_tenant_access_token(self):
        """获取 tenant_access_token"""
        payload = {"app_id": self.app_id, "app_secret": self.app_secret}
        response = requests.post(AUTH_URL, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get("code") != 0:
            raise Exception(f"获取 access token 失败: {data.get('msg')}")

        self.tenant_access_token = data.get("tenant_access_token")
        self.headers["Authorization"] = f"Bearer {self.tenant_access_token}"
        self.logger.info("飞书认证成功")

    def batch_get_records(self, app_token: str, table_id: str, record_ids: List[str]) -> List[Dict]:
        """
        批量获取记录

        Args:
            app_token: 多维表格 App Token
            table_id: 表格 ID
            record_ids: 记录 ID 列表

        Returns:
            记录列表
        """
        if not record_ids:
            return []

        all_records = []
        batch_size = 100

        for i in range(0, len(record_ids), batch_size):
            batch = record_ids[i:i + batch_size]
            url = f"{FEISHU_OPEN_API_URL}/{app_token}/tables/{table_id}/records/batch_get"
            payload = {"record_ids": batch}

            response = requests.post(url, headers=self.headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()

            if data.get("code") == 0:
                items = data.get("data", {}).get("records", [])
                all_records.extend(items)
            else:
                self.logger.warning(f"批量获取失败: {data.get('msg')}")

        return all_records

    def list_records(self, app_token: str, table_id: str, view_id: Optional[str] = None, page_size: int = 100) -> List[Dict]:
        """
        列出表格记录

        Args:
            app_token: 多维表格 App Token
            table_id: 表格 ID
            view_id: 视图 ID（可选）
            page_size: 每页大小

        Returns:
            记录列表
        """
        url = f"{FEISHU_OPEN_API_URL}/{app_token}/tables/{table_id}/records"
        params = {"page_size": page_size}
        if view_id:
            params["view_id"] = view_id

        records = []
        has_more = True
        page_token = None

        self.logger.info(f"正在获取表格记录: {table_id}")

        while has_more:
            if page_token:
                params["page_token"] = page_token

            response = requests.get(url, headers=self.headers, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 0:
                raise Exception(f"获取记录失败: {data.get('msg')}")

            items = data["data"]["items"]
            records.extend(items)

            has_more = data["data"]["has_more"]
            page_token = data["data"].get("page_token")

        self.logger.info(f"共获取 {len(records)} 条记录")
        return records

    def update_records(self, app_token: str, table_id: str, records_updates: List[Dict], field_id_type: str = "name"):
        """
        批量更新记录

        Args:
            app_token: 多维表格 App Token
            table_id: 表格 ID
            records_updates: 更新数据列表 [{"record_id": "...", "fields": {...}}]
            field_id_type: 字段标识类型 ("name" 或 "id")
        """
        if not records_updates:
            return

        url = f"{FEISHU_OPEN_API_URL}/{app_token}/tables/{table_id}/records/batch_update"
        params = {"field_id_type": field_id_type}

        batch_size = 500
        for i in range(0, len(records_updates), batch_size):
            batch = records_updates[i:i + batch_size]
            payload = {"records": batch}

            response = requests.post(url, headers=self.headers, params=params, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 0:
                self.logger.error(f"更新批次 {i} 失败: {data.get('msg')}")
                self.logger.error(f"完整响应: {json.dumps(data, ensure_ascii=False)}")
            else:
                self.logger.info(f"成功更新 {len(batch)} 条记录")

    def list_fields(self, app_token: str, table_id: str) -> List[Dict]:
        """
        列出表格字段

        Args:
            app_token: 多维表格 App Token
            table_id: 表格 ID

        Returns:
            字段列表
        """
        url = f"{FEISHU_OPEN_API_URL}/{app_token}/tables/{table_id}/fields"
        params = {"page_size": 100}

        fields = []
        has_more = True
        page_token = None

        while has_more:
            if page_token:
                params["page_token"] = page_token

            response = requests.get(url, headers=self.headers, params=params, timeout=30)

            if response.status_code != 200:
                self.logger.warning(f"获取字段失败: {response.text}")
                return []

            data = response.json()
            if data.get("code") != 0:
                self.logger.warning(f"获取字段失败 (code {data.get('code')}): {data.get('msg')}")
                return []

            items = data["data"]["items"]
            fields.extend(items)

            has_more = data["data"]["has_more"]
            page_token = data["data"].get("page_token")

        return fields
