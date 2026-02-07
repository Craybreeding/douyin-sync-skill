#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音数据同步脚本 - Clawbot Skill 入口

用法:
  # 模式一：飞书表格同步
  python3 sync.py sync --app-token <TOKEN> --table-id <TABLE_ID>
  python3 sync.py sync --app-token <TOKEN> --table-id <TABLE_ID> --force
  python3 sync.py sync --app-token <TOKEN> --table-id <TABLE_ID> --view-id <VIEW_ID>

  # 模式二：单视频查询
  python3 sync.py query --video-id 7567352731951164082
  python3 sync.py query --url "https://www.douyin.com/video/7567352731951164082"
  python3 sync.py query --video-id 7567352731951164082 --output json

  # 模式三：视频脚本提取 (语音识别)
  python3 sync.py script --video-id 7567352731951164082
  python3 sync.py script --video-id 7567352731951164082 --method whisper
  python3 sync.py script --video-id 7567352731951164082 --save output.json

  # 模式四：品牌管理
  python3 sync.py brands --list
  python3 sync.py brands --add lego "乐高/LEGO" 1731407744628743 "母婴/母婴"
"""

import argparse
import json
import logging
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config, validate_config
from douyin_api import DouyinAPI
from douyin_parser import DouyinParser


def setup_logging(verbose: bool = False):
    """配置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def cmd_query(args):
    """单视频查询命令"""
    config = get_config()
    is_valid, error_msg = validate_config(config, require_feishu=False)

    if not is_valid:
        print(f"错误: {error_msg}", file=sys.stderr)
        sys.exit(1)

    # 确定视频标识
    video_input = args.video_id or args.url
    if not video_input:
        print("错误: 请提供 --video-id 或 --url 参数", file=sys.stderr)
        sys.exit(1)

    api = DouyinAPI(api_key=config["douyin_api_key"], api_url=config["douyin_api_url"])
    parser = DouyinParser()

    logging.info(f"正在查询视频: {video_input}")

    raw_data = api.fetch_video(video_input)

    if not raw_data or raw_data.get('code') != 0:
        if args.output == "json":
            print(json.dumps({"error": "视频获取失败", "input": video_input}, ensure_ascii=False, indent=2))
        else:
            print(f"错误: 视频获取失败 - {video_input}")
        sys.exit(1)

    # 解析数据
    parsed_data = parser.parse_video_simple(raw_data)

    if not parsed_data:
        if args.output == "json":
            print(json.dumps({"error": "数据解析失败", "input": video_input}, ensure_ascii=False, indent=2))
        else:
            print(f"错误: 数据解析失败 - {video_input}")
        sys.exit(1)

    # 输出结果
    if args.output == "json":
        print(json.dumps(parsed_data, ensure_ascii=False, indent=2))
    else:
        print_video_info(parsed_data)


def print_video_info(data: dict):
    """格式化输出视频信息"""
    stats = data.get("statistics", {})

    print("\n" + "=" * 60)
    print(f"视频ID: {data.get('aweme_id')}")
    print(f"链接: {data.get('url')}")
    print("-" * 60)
    print(f"标题: {data.get('title', '无标题')}")
    print(f"作者: {data.get('author', {}).get('nickname', '未知')} (@{data.get('author', {}).get('unique_id', '')})")
    print(f"时长: {data.get('duration_seconds', 0)} 秒")
    print("-" * 60)
    print(f"播放量: {stats.get('play_count', 0):,}")
    print(f"点赞数: {stats.get('digg_count', 0):,}")
    print(f"评论数: {stats.get('comment_count', 0):,}")
    print(f"分享数: {stats.get('share_count', 0):,}")
    print(f"收藏数: {stats.get('collect_count', 0):,}")
    print("-" * 60)
    if data.get("hashtags"):
        print(f"话题标签: {data.get('hashtags')}")
    print(f"数据来源: {data.get('data_source', 'unknown')}")
    if data.get("is_deleted"):
        print("状态: 视频已下架")
    print("=" * 60 + "\n")


def cmd_sync(args):
    """飞书表格同步命令"""
    from feishu_client import FeishuClient

    config = get_config()
    is_valid, error_msg = validate_config(config, require_feishu=True)

    if not is_valid:
        print(f"错误: {error_msg}", file=sys.stderr)
        sys.exit(1)

    if not args.app_token or not args.table_id:
        print("错误: 请提供 --app-token 和 --table-id 参数", file=sys.stderr)
        sys.exit(1)

    # 初始化客户端
    feishu = FeishuClient(config["feishu_app_id"], config["feishu_app_secret"])
    api = DouyinAPI(api_key=config["douyin_api_key"], api_url=config["douyin_api_url"])
    parser = DouyinParser()

    try:
        # 认证
        logging.info("正在连接飞书...")
        feishu.get_tenant_access_token()

        # 获取记录
        logging.info("正在获取表格记录...")
        records = feishu.list_records(args.app_token, args.table_id, args.view_id)

        if not records:
            print("表格中没有记录")
            return

        logging.info(f"共获取 {len(records)} 条记录")

        # 分析需要更新的视频
        video_groups = {}
        for record in records:
            video_id = extract_video_id(record.get("fields", {}).get("视频ID"))
            if not video_id:
                continue

            if video_id not in video_groups:
                video_groups[video_id] = {"master": record, "duplicates": []}
            else:
                video_groups[video_id]["duplicates"].append(record)

        if not video_groups:
            print("没有有效的视频ID")
            return

        # 筛选需要获取的视频
        videos_to_fetch = []
        for vid, group in video_groups.items():
            master = group["master"]
            fields = master.get("fields", {})

            has_likes = bool(fields.get("点赞数"))
            has_plays = bool(fields.get("播放量"))
            desc_raw = fields.get("标题描述", "")

            if isinstance(desc_raw, list):
                if desc_raw and isinstance(desc_raw[0], dict):
                    desc_value = desc_raw[0].get('text', '')
                elif desc_raw:
                    desc_value = str(desc_raw[0])
                else:
                    desc_value = ""
            else:
                desc_value = str(desc_raw) if desc_raw else ""

            is_error = desc_value in ["视频已下架", ""] or desc_value.startswith("⚠️")
            has_valid_desc = bool(desc_value) and not is_error
            is_complete = has_valid_desc and (has_likes or has_plays)

            if args.force or not is_complete:
                videos_to_fetch.append(vid)

        skipped = len(video_groups) - len(videos_to_fetch)
        logging.info(f"需要更新: {len(videos_to_fetch)} 个视频, 跳过: {skipped} 个已有数据")

        if not videos_to_fetch:
            print(f"所有 {len(video_groups)} 个视频数据已是最新")
            return

        # 批量获取视频数据
        logging.info(f"正在从抖音获取数据...")
        batch_results = api.fetch_videos_batch(videos_to_fetch)

        # 解析数据
        parsed_results = {}
        for video_id, raw_data in batch_results.items():
            if raw_data:
                try:
                    parsed_data = parser.parse_video(raw_data)
                    parsed_results[video_id] = parsed_data
                except Exception as e:
                    logging.error(f"解析视频 {video_id} 失败: {e}")

        # 更新飞书
        updates = []
        updated_count = 0

        for video_id, group in video_groups.items():
            master = group["master"]

            if video_id in videos_to_fetch:
                parsed_data = parsed_results.get(video_id)
                if parsed_data:
                    updates.append({
                        "record_id": master["record_id"],
                        "fields": parsed_data
                    })
                    updated_count += 1
                else:
                    updates.append({
                        "record_id": master["record_id"],
                        "fields": {"标题描述": "视频已下架"}
                    })

        if updates:
            logging.info(f"正在更新飞书表格...")
            feishu.update_records(args.app_token, args.table_id, updates)

        # 输出结果
        result = {
            "status": "success",
            "total_records": len(records),
            "unique_videos": len(video_groups),
            "updated": updated_count,
            "skipped": skipped,
            "failed": len(videos_to_fetch) - updated_count
        }

        if args.output == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"\n同步完成:")
            print(f"  - 总记录数: {result['total_records']}")
            print(f"  - 独立视频: {result['unique_videos']}")
            print(f"  - 已更新: {result['updated']}")
            print(f"  - 已跳过: {result['skipped']}")
            print(f"  - 获取失败: {result['failed']}")

    except Exception as e:
        logging.error(f"同步失败: {e}")
        if args.output == "json":
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)


def extract_video_id(raw_value) -> str:
    """从各种飞书字段格式中提取视频ID"""
    if not raw_value:
        return ""

    if isinstance(raw_value, list):
        if not raw_value:
            return ""
        first_item = raw_value[0]
        if isinstance(first_item, dict):
            return str(first_item.get('text', "")).strip()
        return str(first_item).strip()

    return str(raw_value).strip()


def cmd_script(args):
    """视频脚本提取命令"""
    from subtitle_extractor import extract_subtitle

    video_input = args.video_id or args.url
    if not video_input:
        print("错误: 请提供 --video-id 或 --url 参数", file=sys.stderr)
        sys.exit(1)

    # 提取视频ID
    if video_input.startswith("http"):
        import re
        match = re.search(r'/video/(\d+)', video_input)
        video_id = match.group(1) if match else video_input
    else:
        video_id = video_input

    logging.info(f"正在提取视频脚本: {video_id}")

    # 先检查云图本地数据
    from pathlib import Path
    import json as json_module
    yuntu_file = Path(__file__).parent.parent / "data" / "yuntu_scripts.json"
    if yuntu_file.exists():
        try:
            with open(yuntu_file, 'r', encoding='utf-8') as f:
                yuntu_data = json_module.load(f)
            for video in yuntu_data.get("videos", []):
                if video.get("video_id") == video_id or video_id in str(video.get("title", "")):
                    logging.info("从云图缓存中找到脚本数据")
                    result = {
                        "video_id": video.get("video_id"),
                        "title": video.get("title"),
                        "method": "yuntu_cache",
                        "content_formula": video.get("content_formula", []),
                        "script_segments": video.get("script_segments", []),
                        "raw_script": video.get("raw_script", ""),
                        "talent_name": video.get("talent_name"),
                        "views": video.get("views")
                    }
                    if args.output == "json":
                        print(json.dumps(result, ensure_ascii=False, indent=2))
                    else:
                        print(f"\n{'='*60}")
                        print(f"视频: {result['title'][:50]}...")
                        print(f"达人: {result['talent_name']}")
                        print(f"播放量: {result['views']}")
                        print(f"内容公式: {result['content_formula']}")
                        print(f"{'='*60}")
                        if result['script_segments']:
                            for seg in result['script_segments']:
                                print(f"\n[{seg['tag']}]")
                                print(seg['content'])
                        elif result['raw_script']:
                            print(f"\n{result['raw_script']}")
                        print(f"\n{'='*60}")
                        print(f"数据来源: 云图缓存")
                    return
        except Exception as e:
            logging.debug(f"云图缓存读取失败: {e}")

    # 使用 Groq Whisper 语音识别提取
    result = extract_subtitle(video_id, args.output, args.save)

    sys.exit(0 if result else 1)


def cmd_brands(args):
    """品牌管理命令"""
    from yuntu_scraper import load_brands_config, add_brand, get_brand_url

    if args.list:
        brands = load_brands_config()
        print(f"\n{'='*60}")
        print("已配置的品牌:")
        print(f"{'='*60}")
        for key, info in brands.items():
            print(f"\n  [{key}]")
            print(f"    名称: {info['name']}")
            print(f"    aadvid: {info['aadvid']}")
            print(f"    行业: {info.get('industry', '未设置')}")
            print(f"    URL: {info['yuntu_url'][:60]}...")
        print(f"\n{'='*60}")

    elif args.add:
        if len(args.add) < 3:
            print("错误: --add 需要至少3个参数: key name aadvid [industry]", file=sys.stderr)
            sys.exit(1)

        key, name, aadvid = args.add[:3]
        industry = args.add[3] if len(args.add) > 3 else ""
        add_brand(key, name, aadvid, industry)

    elif args.url:
        url = get_brand_url(args.url)
        if url:
            print(url)
        else:
            print(f"错误: 未找到品牌 '{args.url}'", file=sys.stderr)
            sys.exit(1)

    else:
        print("请使用 --list, --add 或 --url 参数")
        sys.exit(1)


def cmd_translate(args):
    """翻译内容命令"""
    config = get_config()
    is_valid, error_msg = validate_config(config, require_feishu=False)

    if not is_valid:
        print(f"错误: {error_msg}", file=sys.stderr)
        sys.exit(1)

    content = args.content
    if not content:
        print("错误: 请提供 --content 参数", file=sys.stderr)
        sys.exit(1)

    api = DouyinAPI(api_key=config["douyin_api_key"], api_url=config["douyin_api_url"])

    result = api.translate_content(content, args.lang)

    if args.output == "json":
        # 简化 JSON 输出
        if result and result.get("success"):
            translated_data = result.get("translated", {})
            translated_list = translated_data.get("translated_content_list", [])
            output = {
                "success": True,
                "source": result.get("source"),
                "target_lang": result.get("target_lang"),
                "translated": translated_list[0].get("translated_content") if translated_list else None
            }
        else:
            output = result
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if result and result.get("success"):
            translated_data = result.get("translated", {})
            translated_list = translated_data.get("translated_content_list", [])
            translated_text = translated_list[0].get("translated_content") if translated_list else "无翻译结果"

            print(f"\n{'='*50}")
            print(f"原文: {result.get('source', '')}")
            print(f"{'='*50}")
            print(f"目标语言: {result.get('target_lang')}")
            print(f"翻译结果: {translated_text}")
            print(f"{'='*50}")
        else:
            print(f"翻译失败: {result.get('error', '未知错误')}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="抖音数据同步工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 查询单个视频
  python3 sync.py query --video-id 7567352731951164082
  python3 sync.py query --url "https://www.douyin.com/video/7567352731951164082"

  # 同步飞书表格
  python3 sync.py sync --app-token Su66bLvv3aOsLps1Ebwcr0lrnMg --table-id tblDfKciZ2oHcwPt

环境变量:
  DOUYIN_API_KEY     - TikHub API 密钥 (必需)
  FEISHU_APP_ID      - 飞书应用 App ID (sync 命令必需)
  FEISHU_APP_SECRET  - 飞书应用 App Secret (sync 命令必需)
        """
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细日志")

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # query 子命令
    query_parser = subparsers.add_parser("query", help="查询单个视频数据")
    query_parser.add_argument("--video-id", help="抖音视频ID (19位数字)")
    query_parser.add_argument("--url", help="抖音视频链接")
    query_parser.add_argument("--output", choices=["text", "json"], default="text", help="输出格式")

    # sync 子命令
    sync_parser = subparsers.add_parser("sync", help="同步飞书表格数据")
    sync_parser.add_argument("--app-token", required=True, help="飞书多维表格 App Token")
    sync_parser.add_argument("--table-id", required=True, help="表格 ID")
    sync_parser.add_argument("--view-id", help="视图 ID (可选)")
    sync_parser.add_argument("--force", action="store_true", help="强制更新所有记录")
    sync_parser.add_argument("--output", choices=["text", "json"], default="text", help="输出格式")

    # translate 子命令
    translate_parser = subparsers.add_parser("translate", help="翻译内容")
    translate_parser.add_argument("--content", required=True, help="需要翻译的内容（最大5000字符）")
    translate_parser.add_argument("--lang", default="zh-Hans", help="目标语言 (zh-Hans/en/ja/ko 等，默认 zh-Hans)")
    translate_parser.add_argument("--output", choices=["text", "json"], default="text", help="输出格式")

    # script 子命令 - 视频脚本提取
    script_parser = subparsers.add_parser("script", help="提取视频脚本/字幕 (使用 Groq Whisper 免费语音识别)")
    script_parser.add_argument("--video-id", help="抖音视频ID")
    script_parser.add_argument("--url", help="抖音视频链接")
    script_parser.add_argument("--output", choices=["text", "json", "srt"], default="text",
                              help="输出格式 (text/json/srt)")
    script_parser.add_argument("--save", help="保存结果到文件")

    # brands 子命令 - 品牌管理
    brands_parser = subparsers.add_parser("brands", help="管理云图品牌配置")
    brands_parser.add_argument("--list", action="store_true", help="列出所有已配置品牌")
    brands_parser.add_argument("--add", nargs="+", metavar="ARG",
                              help="添加品牌: --add key name aadvid [industry]")
    brands_parser.add_argument("--url", metavar="BRAND_KEY", help="获取品牌云图URL")

    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.command == "query":
        cmd_query(args)
    elif args.command == "sync":
        cmd_sync(args)
    elif args.command == "translate":
        cmd_translate(args)
    elif args.command == "script":
        cmd_script(args)
    elif args.command == "brands":
        cmd_brands(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
