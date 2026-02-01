"""RSS Feed Parser - 解析播客RSS订阅"""

import feedparser
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
import time


@dataclass
class Episode:
    """播客单集信息"""
    id: str
    title: str
    audio_url: str
    published: datetime
    duration: Optional[str] = None
    description: Optional[str] = None


def parse_feed(url: str, max_episodes: int = 10) -> List[Episode]:
    """
    解析RSS订阅并返回节目列表
    
    Args:
        url: RSS订阅地址
        max_episodes: 最大返回数量
        
    Returns:
        Episode列表
    """
    feed = feedparser.parse(url)
    episodes = []
    
    for entry in feed.entries[:max_episodes]:
        # 查找音频文件链接
        audio_url = None
        for link in entry.get('links', []):
            if link.get('type', '').startswith('audio/'):
                audio_url = link.get('href')
                break
        
        # 尝试从enclosures获取
        if not audio_url:
            for enclosure in entry.get('enclosures', []):
                if enclosure.get('type', '').startswith('audio/'):
                    audio_url = enclosure.get('href')
                    break
        
        if not audio_url:
            continue
            
        # 解析发布时间
        published = None
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            published = datetime(*entry.published_parsed[:6])
        else:
            published = datetime.now()
            
        # 获取时长
        duration = entry.get('itunes_duration')
        
        episode = Episode(
            id=entry.get('id', entry.get('link', audio_url)),
            title=entry.get('title', 'Untitled'),
            audio_url=audio_url,
            published=published,
            duration=duration,
            description=entry.get('summary', '')
        )
        episodes.append(episode)
    
    return episodes


if __name__ == '__main__':
    # 测试解析
    import sys
    if len(sys.argv) > 1:
        episodes = parse_feed(sys.argv[1])
        for ep in episodes:
            print(f"- {ep.title} ({ep.published.date()})")
            print(f"  Audio: {ep.audio_url}")
