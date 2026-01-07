"""
Agent状态定义
"""

from typing import TypedDict, List, Optional
from datetime import datetime


class NewsItem(TypedDict):
    """新闻条目"""
    title: str
    url: str
    content: str
    full_content: Optional[str]  # 完整网页内容
    source: str
    published_date: Optional[datetime]
    category: Optional[str]
    quality_score: Optional[float]
    embedding: Optional[List[float]]


class AgentState(TypedDict):
    """Agent工作流状态"""
    raw_items: List[NewsItem]
    checked_items: List[NewsItem]
    analyzed_items: List[NewsItem]
    unique_items: List[NewsItem]
    stage: str
    report_path: str
    timestamp: datetime
