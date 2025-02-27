from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime

@dataclass
class SocialMetrics:
    symbol: str
    timestamp: datetime
    
    # Twitter метрики
    tweet_count: int = 0
    retweet_count: int = 0
    like_count: int = 0
    engagement_rate: float = 0.0
    follower_count: int = 0
    
    # Reddit метрики
    post_count: int = 0
    comment_count: int = 0
    total_score: int = 0
    unique_authors: int = 0
    
    # Общие метрики
    sentiment_score: float = 0.0
    hype_score: float = 0.0
    active_users_ratio: float = 0.0
    verified_mentions_score: float = 0.0 