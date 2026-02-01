#!/usr/bin/env python3
"""
Query - 查询转录任务状态并下载结果
支持查询所有任务或按频道筛选
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import requests

from db import Database
from transcriber import TranscriptSegment, segments_to_markdown, segments_to_json
from utils import get_output_path, format_duration, ensure_dir

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = ROOT_DIR / 'output'
DB_PATH = ROOT_DIR / 'data' / 'podcast.db'


def check_transcription_status(transcription_id: str, speech_key: str, speech_region: str) -> dict:
    """检查转录任务状态"""
    base_url = f"https://{speech_region}.api.cognitive.microsoft.com"
    headers = {"Ocp-Apim-Subscription-Key": speech_key}
    
    response = requests.get(
        f"{base_url}/speechtotext/v3.1/transcriptions/{transcription_id}",
        headers=headers,
        timeout=30
    )
    response.raise_for_status()
    return response.json()


def get_transcription_result(transcription_id: str, speech_key: str, speech_region: str) -> list:
    """获取转录结果"""
    base_url = f"https://{speech_region}.api.cognitive.microsoft.com"
    headers = {"Ocp-Apim-Subscription-Key": speech_key}
    
    response = requests.get(
        f"{base_url}/speechtotext/v3.1/transcriptions/{transcription_id}/files",
        headers=headers,
        timeout=30
    )
    response.raise_for_status()
    files = response.json()
    
    segments = []
    for file in files.get("values", []):
        if file["kind"] == "Transcription":
            result_url = file["links"]["contentUrl"]
            result_response = requests.get(result_url, timeout=60)
            result_response.raise_for_status()
            result = result_response.json()
            
            for item in result.get("recognizedPhrases", []):
                offset = parse_duration(item.get("offset", "PT0S"))
                duration = parse_duration(item.get("duration", "PT0S"))
                speaker = item.get("speaker", 0)
                
                best = item.get("nBest", [{}])[0]
                text = best.get("display", "")
                
                if text:
                    segments.append(TranscriptSegment(
                        start_time=offset,
                        end_time=offset + duration,
                        text=text,
                        speaker=speaker
                    ))
    
    return segments


def delete_transcription(transcription_id: str, speech_key: str, speech_region: str):
    """删除Azure上的转录任务"""
    base_url = f"https://{speech_region}.api.cognitive.microsoft.com"
    headers = {"Ocp-Apim-Subscription-Key": speech_key}
    
    requests.delete(
        f"{base_url}/speechtotext/v3.1/transcriptions/{transcription_id}",
        headers=headers,
        timeout=30
    )


def parse_duration(duration_str: str) -> float:
    """解析 ISO 8601 duration"""
    if not duration_str or not duration_str.startswith("PT"):
        return 0.0
    
    duration_str = duration_str[2:]
    total = 0.0
    
    if "H" in duration_str:
        hours, duration_str = duration_str.split("H")
        total += float(hours) * 3600
    if "M" in duration_str:
        minutes, duration_str = duration_str.split("M")
        total += float(minutes) * 60
    if "S" in duration_str:
        total += float(duration_str.replace("S", ""))
    
    return total


def save_output(pending, segments):
    """保存转录结果"""
    date_str = pending.published.strftime('%Y-%m-%d') if pending.published else datetime.now().strftime('%Y-%m-%d')
    output_base = get_output_path(str(OUTPUT_DIR), pending.channel, date_str, pending.title)
    
    # Markdown
    md_path = str(output_base) + '.md'
    md_lines = [
        f"# {pending.title}",
        "",
        f"- 发布日期: {date_str}",
        f"- 时长: {format_duration(pending.duration) if pending.duration else 'Unknown'}",
        f"- 来源: {pending.channel}",
        "",
        "## 转录内容",
        "",
        segments_to_markdown(segments)
    ]
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(md_lines))
    
    # JSON
    json_path = str(output_base) + '.json'
    json_content = {
        "title": pending.title,
        "published": pending.published.isoformat() if pending.published else None,
        "duration": format_duration(pending.duration) if pending.duration else None,
        "channel": pending.channel,
        "audio_url": pending.audio_url,
        "transcript": segments_to_json(segments),
        "processed_at": datetime.now().isoformat()
    }
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_content, f, ensure_ascii=False, indent=2)
    
    return md_path


def main():
    parser = argparse.ArgumentParser(
        description='Query transcription task status and download results',
        epilog='''
Examples:
  python query.py              # Query all pending tasks
  python query.py --channel nopriors  # Query specific channel
  python query.py --list       # List all pending tasks without processing
        '''
    )
    parser.add_argument('--channel', '-c', help='Filter by channel name')
    parser.add_argument('--list', '-l', action='store_true', help='List pending tasks only')
    
    args = parser.parse_args()
    
    load_dotenv(ROOT_DIR / '.env')
    speech_key = os.getenv('AZURE_SPEECH_KEY')
    speech_region = os.getenv('AZURE_SPEECH_REGION')
    
    if not speech_key or not speech_region:
        logger.error("Missing AZURE_SPEECH_KEY or AZURE_SPEECH_REGION")
        sys.exit(1)
    
    ensure_dir(OUTPUT_DIR)
    db = Database(str(DB_PATH))
    
    # 获取待处理列表
    pending_list = db.get_pending(args.channel)
    
    if not pending_list:
        logger.info("No pending transcriptions")
        return
    
    logger.info(f"Found {len(pending_list)} pending transcriptions")
    
    # 仅列出模式
    if args.list:
        for p in pending_list:
            logger.info(f"  [{p.channel}] {p.title[:50]}... (ID: {p.transcription_id})")
        return
    
    completed = 0
    still_running = 0
    failed = 0
    
    for pending in pending_list:
        logger.info(f"Checking [{pending.channel}]: {pending.title[:40]}...")
        
        try:
            status = check_transcription_status(
                pending.transcription_id,
                speech_key,
                speech_region
            )
            
            if status["status"] == "Succeeded":
                segments = get_transcription_result(
                    pending.transcription_id,
                    speech_key,
                    speech_region
                )
                
                if segments:
                    output_path = save_output(pending, segments)
                    
                    db.mark_processed(
                        pending.episode_id,
                        pending.channel,
                        pending.title,
                        output_path,
                        'success'
                    )
                    db.remove_pending(pending.episode_id, pending.channel)
                    delete_transcription(pending.transcription_id, speech_key, speech_region)
                    
                    logger.info(f"  ✓ Completed: {output_path}")
                    completed += 1
                else:
                    db.mark_processed(pending.episode_id, pending.channel, pending.title, '', 'failed')
                    db.remove_pending(pending.episode_id, pending.channel)
                    logger.warning(f"  ✗ No segments found")
                    failed += 1
                    
            elif status["status"] == "Failed":
                error = status.get("properties", {}).get("error", {}).get("message", "Unknown")
                logger.error(f"  ✗ Failed: {error}")
                db.mark_processed(pending.episode_id, pending.channel, pending.title, '', 'failed')
                db.remove_pending(pending.episode_id, pending.channel)
                delete_transcription(pending.transcription_id, speech_key, speech_region)
                failed += 1
                
            else:
                logger.info(f"  ⏳ Still running: {status['status']}")
                still_running += 1
                
        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
            failed += 1
    
    logger.info(f"\n=== Summary ===")
    logger.info(f"Completed: {completed}")
    logger.info(f"Still running: {still_running}")
    logger.info(f"Failed: {failed}")


if __name__ == '__main__':
    main()
