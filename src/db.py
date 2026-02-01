"""Database Operations - SQLite状态追踪"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class ProcessedEpisode:
    """已处理的节目记录"""
    id: int
    episode_id: str
    channel: str
    title: str
    processed_at: datetime
    status: str  # 'success', 'failed'
    output_path: Optional[str] = None


@dataclass
class PendingEpisode:
    """待处理的节目记录"""
    id: int
    episode_id: str
    channel: str
    title: str
    audio_url: str
    transcription_id: str
    submitted_at: datetime
    published: Optional[datetime] = None
    duration: Optional[str] = None


class Database:
    """SQLite 数据库管理"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            # 已处理表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS processed_episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    title TEXT,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'success',
                    output_path TEXT,
                    UNIQUE(episode_id, channel)
                )
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_episode_channel 
                ON processed_episodes(episode_id, channel)
            ''')
            
            # 待处理表（异步任务）
            conn.execute('''
                CREATE TABLE IF NOT EXISTS pending_episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    title TEXT,
                    audio_url TEXT,
                    transcription_id TEXT NOT NULL,
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    published TIMESTAMP,
                    duration TEXT,
                    UNIQUE(episode_id, channel)
                )
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_pending_channel 
                ON pending_episodes(episode_id, channel)
            ''')
            conn.commit()
    
    # === 已处理记录 ===
    
    def is_processed(self, episode_id: str, channel: str) -> bool:
        """检查节目是否已处理"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                'SELECT 1 FROM processed_episodes WHERE episode_id = ? AND channel = ? AND status = ?',
                (episode_id, channel, 'success')
            )
            return cursor.fetchone() is not None
    
    def mark_processed(self, episode_id: str, channel: str, title: str, 
                       output_path: str, status: str = 'success'):
        """标记节目为已处理"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO processed_episodes 
                (episode_id, channel, title, output_path, status, processed_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (episode_id, channel, title, output_path, status, datetime.now()))
            conn.commit()
    
    def get_failed_episodes(self, channel: Optional[str] = None) -> List[ProcessedEpisode]:
        """获取失败的节目列表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if channel:
                cursor = conn.execute(
                    'SELECT * FROM processed_episodes WHERE status = ? AND channel = ?',
                    ('failed', channel)
                )
            else:
                cursor = conn.execute(
                    'SELECT * FROM processed_episodes WHERE status = ?',
                    ('failed',)
                )
            return [
                ProcessedEpisode(
                    id=row['id'],
                    episode_id=row['episode_id'],
                    channel=row['channel'],
                    title=row['title'],
                    processed_at=datetime.fromisoformat(row['processed_at']),
                    status=row['status'],
                    output_path=row['output_path']
                )
                for row in cursor.fetchall()
            ]
    
    # === 待处理记录（异步任务）===
    
    def is_pending(self, episode_id: str, channel: str) -> bool:
        """检查节目是否正在处理中"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                'SELECT 1 FROM pending_episodes WHERE episode_id = ? AND channel = ?',
                (episode_id, channel)
            )
            return cursor.fetchone() is not None
    
    def mark_pending(self, episode_id: str, channel: str, title: str,
                     audio_url: str, transcription_id: str,
                     published: Optional[datetime] = None,
                     duration: Optional[str] = None):
        """标记节目为待处理"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO pending_episodes 
                (episode_id, channel, title, audio_url, transcription_id, submitted_at, published, duration)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (episode_id, channel, title, audio_url, transcription_id, 
                  datetime.now(), published, duration))
            conn.commit()
    
    def get_pending(self, channel: Optional[str] = None) -> List[PendingEpisode]:
        """获取所有待处理的节目"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if channel:
                cursor = conn.execute(
                    'SELECT * FROM pending_episodes WHERE channel = ?',
                    (channel,)
                )
            else:
                cursor = conn.execute('SELECT * FROM pending_episodes')
            
            results = []
            for row in cursor.fetchall():
                published = None
                if row['published']:
                    try:
                        published = datetime.fromisoformat(row['published'])
                    except:
                        pass
                
                results.append(PendingEpisode(
                    id=row['id'],
                    episode_id=row['episode_id'],
                    channel=row['channel'],
                    title=row['title'],
                    audio_url=row['audio_url'],
                    transcription_id=row['transcription_id'],
                    submitted_at=datetime.fromisoformat(row['submitted_at']),
                    published=published,
                    duration=row['duration']
                ))
            return results
    
    def remove_pending(self, episode_id: str, channel: str):
        """移除待处理记录"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                'DELETE FROM pending_episodes WHERE episode_id = ? AND channel = ?',
                (episode_id, channel)
            )
            conn.commit()
    
    # === 统计 ===
    
    def get_stats(self) -> dict:
        """获取处理统计"""
        with sqlite3.connect(self.db_path) as conn:
            stats = {'processed': {}, 'pending': 0}
            
            # 已处理统计
            cursor = conn.execute('''
                SELECT channel, status, COUNT(*) as count 
                FROM processed_episodes 
                GROUP BY channel, status
            ''')
            for row in cursor.fetchall():
                channel, status, count = row
                if channel not in stats['processed']:
                    stats['processed'][channel] = {'success': 0, 'failed': 0}
                stats['processed'][channel][status] = count
            
            # 待处理数量
            cursor = conn.execute('SELECT COUNT(*) FROM pending_episodes')
            stats['pending'] = cursor.fetchone()[0]
            
            return stats


if __name__ == '__main__':
    db = Database('./data/podcast.db')
    print("Database initialized")
    print("Stats:", db.get_stats())
