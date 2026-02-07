#!/usr/bin/env python3
"""
视频字幕提取器 - OpenAI Whisper
"""

import os
import sys
import json
import tempfile
import subprocess
from typing import Optional, Dict
from pathlib import Path
from datetime import datetime

import requests

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


def download_video(video_id: str, output_path: str) -> bool:
    """通过 TikHub 下载视频"""
    try:
        from config import get_config
        api_key = get_config().get("douyin_api_key", "")
    except:
        api_key = os.environ.get("DOUYIN_API_KEY", "")

    if not api_key:
        print("❌ 未设置 DOUYIN_API_KEY")
        return False

    try:
        print(f"📥 下载视频...")
        resp = requests.get(
            "https://api.tikhub.io/api/v1/douyin/web/fetch_one_video",
            params={"aweme_id": video_id},
            headers={"Authorization": f"Bearer {api_key}"}
        )
        data = resp.json()
        video_urls = data.get("data", {}).get("aweme_detail", {}).get("video", {}).get("play_addr", {}).get("url_list", [])

        if not video_urls:
            print("❌ 未找到视频")
            return False

        video_resp = requests.get(video_urls[0], stream=True, timeout=60)
        with open(output_path, 'wb') as f:
            for chunk in video_resp.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"   ✅ 下载成功: {os.path.getsize(output_path) / 1024 / 1024:.1f} MB")
        return True
    except Exception as e:
        print(f"❌ 下载失败: {e}")
        return False


def extract_audio(video_path: str, audio_path: str) -> bool:
    """提取音频"""
    try:
        cmd = ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1", audio_path]
        subprocess.run(cmd, capture_output=True, check=True)
        print(f"🎵 音频提取成功")
        return True
    except Exception as e:
        print(f"❌ 音频提取失败: {e}")
        return False


def transcribe_whisper(audio_path: str) -> Optional[str]:
    """Whisper 语音识别 (Groq 免费接口)"""
    # 优先用 Groq (免费)
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if groq_key:
        try:
            print(f"🎤 Groq Whisper 识别中...")
            client = OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
            with open(audio_path, "rb") as f:
                result = client.audio.transcriptions.create(model="whisper-large-v3", file=f, language="zh")
            print(f"   ✅ 识别完成")
            return result.text
        except Exception as e:
            print(f"⚠️ Groq 失败: {e}")

    # 备选 OpenAI
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("❌ 需要 GROQ_API_KEY 或 OPENAI_API_KEY")
        return None

    if not HAS_OPENAI:
        print("❌ 未安装 openai: pip install openai")
        return None

    try:
        print(f"🎤 OpenAI Whisper 识别中...")
        client = OpenAI(api_key=api_key)
        with open(audio_path, "rb") as f:
            result = client.audio.transcriptions.create(model="whisper-1", file=f, language="zh")
        print(f"   ✅ 识别完成")
        return result.text
    except Exception as e:
        print(f"❌ 识别失败: {e}")
        return None


def extract_subtitle(video_input: str, output_format: str = "text", save_path: str = None) -> Optional[Dict]:
    """提取字幕"""
    print(f"\n{'='*50}")
    print(f"视频字幕提取 (Whisper)")
    print(f"{'='*50}")

    video_id = video_input.split("/")[-1] if "/" in video_input else video_input

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "video.mp4")
        audio_path = os.path.join(tmpdir, "audio.mp3")

        if not download_video(video_id, video_path):
            return None
        if not extract_audio(video_path, audio_path):
            return None

        text = transcribe_whisper(audio_path)
        if not text:
            return None

        result = {
            "video_id": video_id,
            "text": text,
            "method": "whisper",
            "extracted_at": datetime.now().isoformat(),
            "char_count": len(text)
        }

        print(f"\n{'='*50}")
        print(f"结果 ({len(text)} 字)")
        print(f"{'='*50}")

        if output_format == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(text)

        if save_path:
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n✅ 已保存: {save_path}")

        return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--output", default="text", choices=["text", "json"])
    parser.add_argument("--save")
    args = parser.parse_args()

    result = extract_subtitle(args.video_id, args.output, args.save)
    sys.exit(0 if result else 1)
