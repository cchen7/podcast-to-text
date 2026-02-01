"""Utility Functions - 工具函数"""

import os
import re
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass


def load_feeds(config_path: str) -> List[str]:
    """
    加载RSS订阅列表 - 一行一个URL
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        URL列表
    """
    feeds = []
    with open(config_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # 跳过空行和注释
            if line and not line.startswith('#'):
                feeds.append(line)
    return feeds


def sanitize_filename(name: str) -> str:
    """
    清理文件名，移除非法字符
    
    Args:
        name: 原始文件名
        
    Returns:
        安全的文件名
    """
    # 移除非法字符
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # 移除控制字符
    name = re.sub(r'[\x00-\x1f]', '', name)
    # 限制长度
    if len(name) > 200:
        name = name[:200]
    # 移除首尾空格和点
    name = name.strip(' .')
    return name or 'untitled'


def ensure_dir(path: str) -> Path:
    """确保目录存在"""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_output_path(base_dir: str, channel: str, date_str: str, title: str) -> Path:
    """
    生成输出文件路径
    
    Args:
        base_dir: 输出基础目录
        channel: 频道名称
        date_str: 日期字符串 (YYYY-MM-DD)
        title: 节目标题
        
    Returns:
        输出目录路径
    """
    safe_title = sanitize_filename(title)
    output_dir = Path(base_dir) / channel / date_str
    ensure_dir(output_dir)
    return output_dir / safe_title


def format_duration(duration_str: str) -> str:
    """
    格式化时长字符串
    
    Args:
        duration_str: 原始时长 (可能是秒数或 HH:MM:SS)
        
    Returns:
        格式化后的时长
    """
    if not duration_str:
        return "Unknown"
    
    # 如果是纯数字，假设是秒数
    if duration_str.isdigit():
        seconds = int(duration_str)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"
    
    return duration_str


if __name__ == '__main__':
    # 测试
    print(sanitize_filename('Test: Episode "01" <Special>'))
    print(format_duration('3600'))
    print(format_duration('45:30'))
