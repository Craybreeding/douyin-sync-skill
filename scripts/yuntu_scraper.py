#!/usr/bin/env python3
"""
巨量云图视频脚本抓取器 v2.0

功能:
1. 批量抓取视频脚本 + 支持指定视频ID查询
2. 多品牌支持 - 保存各品牌 aadvid，快速切换
3. 同步到飞书表格
4. 备用方案 - 如果云图找不到，使用 TikHub API

使用方式:
- 配合 Claude in Chrome 扩展进行浏览器自动化
- 或直接调用 TikHub API 作为备用
"""

import json
import re
import os
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict
from datetime import datetime
from pathlib import Path

# 导入现有模块
try:
    from douyin_api import DouyinAPI
    from feishu_client import FeishuClient
    from config import get_config
except ImportError:
    pass  # 模块可能不在路径中


# ============================================================================
# 品牌配置管理
# ============================================================================

BRANDS_CONFIG_FILE = Path(__file__).parent.parent / "data" / "brands_config.json"

# 默认品牌配置
DEFAULT_BRANDS = {
    "lego": {
        "name": "乐高/LEGO",
        "aadvid": "1731407744628743",
        "industry": "母婴/母婴",
        "yuntu_url": "https://yuntu.oceanengine.com/yuntu_brand/ecom/strategy/medium/talent_markting/hotcontent?aadvid=1731407744628743"
    }
    # 可以添加更多品牌...
}


def load_brands_config() -> Dict:
    """加载品牌配置"""
    if BRANDS_CONFIG_FILE.exists():
        with open(BRANDS_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return DEFAULT_BRANDS


def save_brands_config(brands: Dict):
    """保存品牌配置"""
    BRANDS_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(BRANDS_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(brands, f, ensure_ascii=False, indent=2)


def add_brand(brand_key: str, name: str, aadvid: str, industry: str = ""):
    """添加新品牌"""
    brands = load_brands_config()
    brands[brand_key] = {
        "name": name,
        "aadvid": aadvid,
        "industry": industry,
        "yuntu_url": f"https://yuntu.oceanengine.com/yuntu_brand/ecom/strategy/medium/talent_markting/hotcontent?aadvid={aadvid}"
    }
    save_brands_config(brands)
    print(f"✅ 已添加品牌: {name} (aadvid: {aadvid})")


def get_brand_url(brand_key: str) -> Optional[str]:
    """获取品牌的云图 URL"""
    brands = load_brands_config()
    if brand_key in brands:
        return brands[brand_key]["yuntu_url"]
    return None


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class VideoScript:
    """视频脚本数据结构"""
    video_id: str
    title: str
    publish_date: str
    views: str
    interaction_rate: str
    completion_rate: str
    talent_name: str
    talent_followers: str
    douyin_id: str

    # 内容公式标签
    content_formula: List[str] = field(default_factory=list)

    # 脚本内容 - 带标签的段落列表
    script_segments: List[dict] = field(default_factory=list)

    # 原始脚本文本
    raw_script: str = ""

    # 元数据
    scraped_at: str = ""
    source: str = "yuntu"  # yuntu 或 tikhub
    source_url: str = ""


# ============================================================================
# JavaScript 提取器 (用于浏览器自动化)
# ============================================================================

def get_extract_video_script_js() -> str:
    """返回用于提取视频脚本的 JavaScript 代码"""
    return '''
(function() {
    const allText = document.body.innerText;

    // 提取视频基本信息
    const titleMatch = allText.match(/[^\\n]{10,100}#[乐高|抖音|情侣|混血]/)?.[0] || '';
    const dateMatch = allText.match(/发布日期[：:]\\s*(\\d{4}-\\d{2}-\\d{2})/);
    const viewsMatch = allText.match(/总曝光量[\\s\\n]*([\\d,]+)/);
    const interactionMatch = allText.match(/总互动率[\\s\\n]*([\\d.]+%?)/);
    const completionMatch = allText.match(/完播率[\\s\\n]*([\\d.]+%?)/);

    // 达人信息
    const talentMatch = allText.match(/达人信息[\\s\\S]*?粉丝量[：:]\\s*([\\d.]+[万wW]?)/);
    const douyinIdMatch = allText.match(/抖音号[：:]\\s*(\\d+)/);

    // 本视频脚本
    const scriptMatch = allText.match(/本视频脚本[\\s\\S]*?(?=元素拆解|评论口碑|热门评论|标签分布|$)/);

    // 内容公式
    const formulaMatch = allText.match(/本视频内容公式[\\s\\S]*?(?=本视频脚本|$)/);

    return {
        title: titleMatch.trim(),
        publish_date: dateMatch ? dateMatch[1] : '',
        views: viewsMatch ? viewsMatch[1] : '',
        interaction_rate: interactionMatch ? interactionMatch[1] : '',
        completion_rate: completionMatch ? completionMatch[1] : '',
        talent_followers: talentMatch ? talentMatch[1] : '',
        douyin_id: douyinIdMatch ? douyinIdMatch[1] : '',
        content_formula: formulaMatch ? formulaMatch[0].trim() : '',
        raw_script: scriptMatch ? scriptMatch[0].trim() : '',
        source_url: window.location.href,
        scraped_at: new Date().toISOString()
    };
})();
'''


def get_search_video_by_id_js(video_id: str) -> str:
    """返回用于搜索指定视频ID的 JavaScript 代码"""
    return f'''
(function() {{
    // 在搜索框中输入视频ID
    const searchInput = document.querySelector('input[placeholder*="搜索"], input[placeholder*="视频"], input[type="text"]');
    if (searchInput) {{
        searchInput.value = '{video_id}';
        searchInput.dispatchEvent(new Event('input', {{ bubbles: true }}));

        // 触发搜索
        const searchBtn = document.querySelector('button[class*="search"], [class*="search-btn"]');
        if (searchBtn) {{
            searchBtn.click();
        }}
        return {{ success: true, message: '已搜索视频ID: {video_id}' }};
    }}
    return {{ success: false, message: '未找到搜索框' }};
}})();
'''


def get_video_list_js() -> str:
    """返回用于获取视频列表的 JavaScript 代码"""
    return '''
(function() {
    const videos = [];

    // 查找所有视频标题元素
    const titleElements = document.querySelectorAll('[class*="title"], [class*="video-name"], td:nth-child(2)');

    titleElements.forEach((el, index) => {
        const text = el.textContent.trim();
        // 过滤出视频标题（包含#标签的）
        if (text.includes('#') && text.length > 20 && text.length < 200) {
            const row = el.closest('tr') || el.closest('[class*="row"]');
            const douyinIdMatch = row?.textContent.match(/抖音号[：:]\\s*(\\d+)/);

            videos.push({
                index: index,
                title: text.substring(0, 100),
                douyin_id: douyinIdMatch ? douyinIdMatch[1] : '',
                element_class: el.className
            });
        }
    });

    // 去重
    const seen = new Set();
    const unique = videos.filter(v => {
        if (seen.has(v.title)) return false;
        seen.add(v.title);
        return true;
    });

    return {
        total: unique.length,
        videos: unique.slice(0, 20)
    };
})();
'''


# ============================================================================
# TikHub API 备用方案
# ============================================================================

def fetch_video_from_tikhub(video_id: str, api_key: str) -> Optional[Dict]:
    """
    从 TikHub API 获取视频信息（作为云图的备用方案）

    注意：TikHub 不提供完整的脚本/字幕，只有视频元数据
    """
    try:
        api = DouyinAPI(api_key)
        video_data = api.fetch_video(video_id)

        if video_data:
            return {
                "video_id": video_id,
                "title": video_data.get("desc", ""),
                "publish_date": "",  # TikHub 可能不返回
                "views": str(video_data.get("statistics", {}).get("play_count", "")),
                "interaction_rate": "",
                "completion_rate": "",
                "talent_name": video_data.get("author", {}).get("nickname", ""),
                "talent_followers": str(video_data.get("author", {}).get("follower_count", "")),
                "douyin_id": video_data.get("author", {}).get("unique_id", ""),
                "content_formula": [],
                "raw_script": "",  # TikHub 不提供脚本
                "source": "tikhub",
                "source_url": f"https://www.douyin.com/video/{video_id}",
                "scraped_at": datetime.now().isoformat(),
                "note": "TikHub API 不提供视频脚本/字幕，仅返回元数据"
            }
    except Exception as e:
        print(f"TikHub API 错误: {e}")

    return None


# ============================================================================
# 飞书同步
# ============================================================================

def sync_to_feishu(videos: List[Dict], app_id: str, app_secret: str,
                   app_token: str, table_id: str):
    """
    将视频脚本数据同步到飞书多维表格
    """
    client = FeishuClient(app_id, app_secret)

    for video in videos:
        record = {
            "视频标题": video.get("title", ""),
            "发布日期": video.get("publish_date", ""),
            "播放量": video.get("views", ""),
            "互动率": video.get("interaction_rate", ""),
            "完播率": video.get("completion_rate", ""),
            "达人名称": video.get("talent_name", ""),
            "达人粉丝数": video.get("talent_followers", ""),
            "抖音号": video.get("douyin_id", ""),
            "内容公式": ", ".join(video.get("content_formula", [])) if isinstance(video.get("content_formula"), list) else str(video.get("content_formula", "")),
            "视频脚本": video.get("raw_script", "")[:2000],  # 飞书字段有长度限制
            "数据来源": video.get("source", "yuntu"),
            "抓取时间": video.get("scraped_at", "")
        }

        try:
            client.create_record(app_token, table_id, record)
            print(f"✅ 已同步: {video.get('title', '')[:30]}...")
        except Exception as e:
            print(f"❌ 同步失败: {e}")


# ============================================================================
# 脚本解析
# ============================================================================

def parse_script_text(raw_script: str) -> List[dict]:
    """解析脚本文本，提取带标签的段落"""
    segments = []

    # 匹配 (标签名) 内容 的模式
    pattern = r'[（\(](适用人群|品牌信息|话题/玩法|适用场景|商品信息|商品卖点|使用感受|开场)[）\)]([^（\(]*?)(?=[（\(]|$)'

    matches = re.findall(pattern, raw_script, re.DOTALL)

    for tag, content in matches:
        content = content.strip()
        if content:
            segments.append({
                "tag": tag,
                "content": content
            })

    return segments


# ============================================================================
# 主要工作流
# ============================================================================

class YuntuScraper:
    """巨量云图抓取器"""

    def __init__(self, tikhub_api_key: str = None):
        self.tikhub_api_key = tikhub_api_key or os.environ.get("DOUYIN_API_KEY", "")
        self.brands = load_brands_config()
        self.results: List[VideoScript] = []

    def get_video_script(self, video_id: str, brand_key: str = None,
                         use_fallback: bool = True) -> Optional[Dict]:
        """
        获取视频脚本

        优先使用云图（需要浏览器自动化），如果找不到则使用 TikHub

        Args:
            video_id: 抖音视频ID
            brand_key: 品牌标识（用于云图查询）
            use_fallback: 是否使用 TikHub 作为备用

        Returns:
            视频脚本数据
        """
        # 首先尝试云图（需要通过浏览器自动化）
        # 这里只返回 JavaScript 代码，实际执行需要在 Claude in Chrome 中

        print(f"📋 查询视频: {video_id}")
        print(f"   云图查询需要通过浏览器自动化执行")
        print(f"   搜索 JS: get_search_video_by_id_js('{video_id}')")

        # 如果需要备用方案
        if use_fallback and self.tikhub_api_key:
            print(f"   尝试 TikHub API 备用方案...")
            result = fetch_video_from_tikhub(video_id, self.tikhub_api_key)
            if result:
                print(f"   ✅ TikHub 返回成功（注意：无脚本数据）")
                return result
            else:
                print(f"   ❌ TikHub 也未找到该视频")

        return None

    def list_brands(self):
        """列出所有已配置的品牌"""
        print("\n📦 已配置的品牌:")
        print("-" * 60)
        for key, info in self.brands.items():
            print(f"  {key}: {info['name']}")
            print(f"      aadvid: {info['aadvid']}")
            print(f"      URL: {info['yuntu_url'][:60]}...")
        print("-" * 60)


# ============================================================================
# 使用说明
# ============================================================================

USAGE = """
================================================================================
巨量云图视频脚本抓取器 v2.0 - 使用说明
================================================================================

【功能特性】
1. 批量抓取视频脚本 + 支持指定视频ID查询
2. 多品牌支持 - 保存各品牌 aadvid，快速切换
3. 同步到飞书表格
4. 备用方案 - 如果云图找不到，使用 TikHub API

【品牌管理】
  # 添加新品牌
  add_brand("brand_key", "品牌名称", "aadvid", "行业")

  # 获取品牌URL
  url = get_brand_url("lego")

【浏览器自动化】
  # 1. 导航到品牌云图页面
  navigate(get_brand_url("lego"))

  # 2. 选择时间范围（近30天）

  # 3. 提取视频列表
  javascript_exec(get_video_list_js())

  # 4. 搜索指定视频
  javascript_exec(get_search_video_by_id_js("7595883673874894143"))

  # 5. 提取视频脚本
  javascript_exec(get_extract_video_script_js())

【备用方案】
  # 如果云图找不到，使用 TikHub
  scraper = YuntuScraper(tikhub_api_key="your_key")
  result = scraper.get_video_script("video_id", use_fallback=True)

【同步到飞书】
  sync_to_feishu(videos, app_id, app_secret, app_token, table_id)

================================================================================
"""


if __name__ == "__main__":
    print(USAGE)

    # 初始化品牌配置
    save_brands_config(DEFAULT_BRANDS)
    print("✅ 品牌配置已初始化")

    # 列出品牌
    scraper = YuntuScraper()
    scraper.list_brands()
