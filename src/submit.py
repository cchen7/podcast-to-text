#!/usr/bin/env python3
"""
Submit - 异步提交转录任务
支持两种模式：
1. 命令行传入RSS URL: python submit.py <rss_url> [--name channel_name] [--lang en-US]
2. 读取配置文件: python submit.py --config
"""

import os
import sys
import time
import logging
import argparse
from pathlib import Path
from dotenv import load_dotenv
import requests
import feedparser

from rss_parser import parse_feed
from db import Database
from utils import load_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent
CONFIG_PATH = ROOT_DIR / 'config' / 'channels.yaml'
DB_PATH = ROOT_DIR / 'data' / 'podcast.db'


def get_channel_name_from_rss(url: str) -> str:
    """从RSS feed中提取频道名称"""
    try:
        feed = feedparser.parse(url)
        title = feed.feed.get('title', '')
        if title:
            # 清理名称，移除特殊字符
            import re
            name = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]+', '-', title)
            name = name.strip('-').lower()
            return name[:50] if name else 'unknown'
    except:
        pass
    return 'unknown'


def submit_transcription(audio_url: str, language: str, speech_key: str, speech_region: str) -> str:
    """提交转录任务到Azure，返回transcription_id"""
    base_url = f"https://{speech_region}.api.cognitive.microsoft.com"
    headers = {
        "Ocp-Apim-Subscription-Key": speech_key,
        "Content-Type": "application/json"
    }
    
    properties = {
        "wordLevelTimestampsEnabled": True,
        "punctuationMode": "DictatedAndAutomatic",
        "profanityFilterMode": "None"
    }
    
    payload = {
        "contentUrls": [audio_url],
        "displayName": f"podcast-{int(time.time())}",
        "properties": properties
    }
    
    # Use auto language detection if language is "auto", otherwise specify locale
    if language and language.lower() != "auto":
        payload["locale"] = language
    else:
        # Enable automatic language identification
        properties["languageIdentification"] = {
            "candidateLocales": ["en-US", "zh-CN", "ja-JP", "ko-KR", "de-DE", "fr-FR", "es-ES"]
        }
    
    response = requests.post(
        f"{base_url}/speechtotext/v3.1/transcriptions",
        headers=headers,
        json=payload,
        timeout=30
    )
    response.raise_for_status()
    
    transcription = response.json()
    return transcription["self"].split("/")[-1]


def process_single_rss(url: str, channel_name: str, language: str, 
                       speech_key: str, speech_region: str, db: Database) -> int:
    """处理单个RSS，返回提交的任务数"""
    logger.info(f"Processing RSS: {url}")
    logger.info(f"Channel: {channel_name}, Language: {language}")
    
    episodes = parse_feed(url, max_episodes=1)  # 只取最新一集
    if not episodes:
        logger.warning("No episodes found")
        return 0
    
    episode = episodes[0]
    
    # 检查是否已处理
    if db.is_processed(episode.id, channel_name):
        logger.info(f"Already processed: {episode.title}")
        return 0
    
    if db.is_pending(episode.id, channel_name):
        logger.info(f"Already pending: {episode.title}")
        return 0
    
    # 提交转录
    try:
        transcription_id = submit_transcription(
            episode.audio_url, language, speech_key, speech_region
        )
        
        db.mark_pending(
            episode_id=episode.id,
            channel=channel_name,
            title=episode.title,
            audio_url=episode.audio_url,
            transcription_id=transcription_id,
            published=episode.published,
            duration=episode.duration
        )
        
        logger.info(f"Submitted: {episode.title}")
        logger.info(f"Transcription ID: {transcription_id}")
        return 1
        
    except Exception as e:
        logger.error(f"Failed to submit: {e}")
        return 0


def process_config_file(speech_key: str, speech_region: str, db: Database) -> tuple:
    """从配置文件批量处理，返回(submitted, skipped)"""
    if not CONFIG_PATH.exists():
        logger.error(f"Config file not found: {CONFIG_PATH}")
        return 0, 0
    
    channels = load_config(str(CONFIG_PATH))
    logger.info(f"Loaded {len(channels)} channels from config")
    
    submitted = 0
    skipped = 0
    
    for channel in channels:
        logger.info(f"\n=== Channel: {channel.name} ===")
        
        try:
            episodes = parse_feed(channel.url, channel.max_episodes)
            logger.info(f"Found {len(episodes)} episodes")
            
            for episode in episodes:
                if db.is_processed(episode.id, channel.name):
                    logger.info(f"Skipping (done): {episode.title[:40]}...")
                    skipped += 1
                    continue
                
                if db.is_pending(episode.id, channel.name):
                    logger.info(f"Skipping (pending): {episode.title[:40]}...")
                    skipped += 1
                    continue
                
                try:
                    transcription_id = submit_transcription(
                        episode.audio_url, channel.language, speech_key, speech_region
                    )
                    
                    db.mark_pending(
                        episode_id=episode.id,
                        channel=channel.name,
                        title=episode.title,
                        audio_url=episode.audio_url,
                        transcription_id=transcription_id,
                        published=episode.published,
                        duration=episode.duration
                    )
                    
                    logger.info(f"Submitted: {episode.title[:40]}... -> {transcription_id}")
                    submitted += 1
                    
                except Exception as e:
                    logger.error(f"Failed: {e}")
                    
        except Exception as e:
            logger.error(f"Error processing channel: {e}")
    
    return submitted, skipped


def main():
    parser = argparse.ArgumentParser(
        description='Submit podcast transcription tasks',
        epilog='''
Examples:
  python submit.py https://example.com/feed.xml
  python submit.py https://example.com/feed.xml --name my-podcast --lang zh-CN
  python submit.py https://example.com/feed.xml --lang auto
  python submit.py --config
        '''
    )
    parser.add_argument('url', nargs='?', help='RSS feed URL')
    parser.add_argument('--name', '-n', help='Channel name (auto-detected if not specified)')
    parser.add_argument('--lang', '-l', default='auto', help='Language code (default: auto). Use "auto" for automatic detection, or specify like en-US, zh-CN')
    parser.add_argument('--config', '-c', action='store_true', help='Read from config file')
    
    args = parser.parse_args()
    
    # 验证参数
    if not args.url and not args.config:
        parser.print_help()
        sys.exit(1)
    
    # 加载环境变量
    load_dotenv(ROOT_DIR / '.env')
    speech_key = os.getenv('AZURE_SPEECH_KEY')
    speech_region = os.getenv('AZURE_SPEECH_REGION')
    
    if not speech_key or not speech_region:
        logger.error("Missing AZURE_SPEECH_KEY or AZURE_SPEECH_REGION")
        sys.exit(1)
    
    db = Database(str(DB_PATH))
    
    if args.config:
        # 模式2: 配置文件
        submitted, skipped = process_config_file(speech_key, speech_region, db)
        logger.info(f"\n=== Summary ===")
        logger.info(f"Submitted: {submitted}")
        logger.info(f"Skipped: {skipped}")
    else:
        # 模式1: 单个RSS
        channel_name = args.name or get_channel_name_from_rss(args.url)
        submitted = process_single_rss(
            args.url, channel_name, args.lang,
            speech_key, speech_region, db
        )
        logger.info(f"\n=== Summary ===")
        logger.info(f"Submitted: {submitted}")


if __name__ == '__main__':
    main()
