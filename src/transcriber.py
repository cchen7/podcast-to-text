"""Azure Speech Transcriber - 批量转录API (直接传URL，不下载到本地)"""

import os
import time
import requests
from typing import List, Dict
from dataclasses import dataclass


@dataclass
class TranscriptSegment:
    """转录片段"""
    start_time: float  # 秒
    end_time: float
    text: str
    speaker: int = 0  # 说话人编号


def format_time(seconds: float) -> str:
    """格式化时间为 HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class Transcriber:
    """Azure Speech 批量转录器 - 直接从URL转录MP3，不经过本地"""
    
    def __init__(self, speech_key: str, speech_region: str):
        self.speech_key = speech_key
        self.speech_region = speech_region
        self.language = "zh-CN"
        self.base_url = f"https://{speech_region}.api.cognitive.microsoft.com"
        
    def set_language(self, language: str):
        """设置识别语言"""
        self.language = language
    
    def transcribe(self, audio_url: str) -> List[TranscriptSegment]:
        """
        从URL转录音频 (使用批量转录API，音频不经过本地)
        
        Args:
            audio_url: 音频URL (支持mp3, wav等)
            
        Returns:
            TranscriptSegment列表
        """
        # 使用原始URL（Azure会处理重定向）
        headers = {
            "Ocp-Apim-Subscription-Key": self.speech_key,
            "Content-Type": "application/json"
        }
        
        # 1. 创建转录任务
        create_url = f"{self.base_url}/speechtotext/v3.1/transcriptions"
        payload = {
            "contentUrls": [audio_url],
            "locale": self.language,
            "displayName": f"podcast-{int(time.time())}",
            "properties": {
                "wordLevelTimestampsEnabled": True,
                "punctuationMode": "DictatedAndAutomatic",
                "profanityFilterMode": "None"
            }
        }
        
        response = requests.post(create_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        transcription = response.json()
        transcription_id = transcription["self"].split("/")[-1]
        
        print(f"  Transcription job created: {transcription_id}")
        
        # 2. 轮询等待完成
        status_url = f"{self.base_url}/speechtotext/v3.1/transcriptions/{transcription_id}"
        while True:
            response = requests.get(status_url, headers=headers, timeout=30)
            response.raise_for_status()
            status = response.json()
            
            if status["status"] == "Succeeded":
                print("  Transcription completed")
                break
            elif status["status"] == "Failed":
                error_msg = status.get("properties", {}).get("error", {}).get("message", "Unknown error")
                raise Exception(f"Transcription failed: {error_msg}")
            
            print(f"  Status: {status['status']}...")
            time.sleep(15)
        
        # 3. 获取结果
        files_url = f"{self.base_url}/speechtotext/v3.1/transcriptions/{transcription_id}/files"
        response = requests.get(files_url, headers=headers, timeout=30)
        response.raise_for_status()
        files = response.json()
        
        segments = []
        for file in files.get("values", []):
            if file["kind"] == "Transcription":
                result_url = file["links"]["contentUrl"]
                result_response = requests.get(result_url, timeout=60)
                result_response.raise_for_status()
                result = result_response.json()
                
                # 解析结果
                for item in result.get("recognizedPhrases", []):
                    offset_seconds = self._parse_duration(item.get("offset", "PT0S"))
                    duration_seconds = self._parse_duration(item.get("duration", "PT0S"))
                    speaker = item.get("speaker", 0)
                    
                    best = item.get("nBest", [{}])[0]
                    text = best.get("display", "")
                    
                    if text:
                        segments.append(TranscriptSegment(
                            start_time=offset_seconds,
                            end_time=offset_seconds + duration_seconds,
                            text=text,
                            speaker=speaker
                        ))
        
        # 4. 清理任务
        requests.delete(status_url, headers=headers, timeout=30)
        
        return segments
    
    def _resolve_url(self, url: str) -> str:
        """解析重定向获取最终URL"""
        try:
            response = requests.head(url, allow_redirects=True, timeout=30)
            return response.url
        except:
            return url
    
    def _parse_duration(self, duration_str: str) -> float:
        """解析 ISO 8601 duration (PT1H2M3.4S) 为秒数"""
        if not duration_str or not duration_str.startswith("PT"):
            return 0.0
        
        duration_str = duration_str[2:]  # 移除 "PT"
        total_seconds = 0.0
        
        # 解析小时
        if "H" in duration_str:
            hours, duration_str = duration_str.split("H")
            total_seconds += float(hours) * 3600
        
        # 解析分钟
        if "M" in duration_str:
            minutes, duration_str = duration_str.split("M")
            total_seconds += float(minutes) * 60
        
        # 解析秒
        if "S" in duration_str:
            seconds = duration_str.replace("S", "")
            total_seconds += float(seconds)
        
        return total_seconds


def segments_to_markdown(segments: List[TranscriptSegment]) -> str:
    """将转录片段转换为Markdown格式（包含说话人标识）"""
    lines = []
    for seg in segments:
        timestamp = format_time(seg.start_time)
        speaker_label = f"Speaker {seg.speaker}" if seg.speaker else ""
        if speaker_label:
            lines.append(f"[{timestamp}] **{speaker_label}**: {seg.text}")
        else:
            lines.append(f"[{timestamp}] {seg.text}")
    return "\n\n".join(lines)


def segments_to_json(segments: List[TranscriptSegment]) -> List[Dict]:
    """将转录片段转换为JSON格式"""
    return [
        {
            "time": format_time(seg.start_time),
            "start": seg.start_time,
            "end": seg.end_time,
            "speaker": seg.speaker,
            "text": seg.text
        }
        for seg in segments
    ]


if __name__ == '__main__':
    import sys
    from dotenv import load_dotenv
    
    load_dotenv()
    
    if len(sys.argv) > 1:
        key = os.getenv('AZURE_SPEECH_KEY')
        region = os.getenv('AZURE_SPEECH_REGION')
        
        if not key or not region:
            print("Missing AZURE_SPEECH_KEY or AZURE_SPEECH_REGION")
            sys.exit(1)
        
        transcriber = Transcriber(key, region)
        transcriber.set_language('en-US')
        segments = transcriber.transcribe(sys.argv[1])
        
        print(segments_to_markdown(segments))
