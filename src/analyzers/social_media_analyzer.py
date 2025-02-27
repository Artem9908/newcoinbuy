from typing import Dict, Optional
from datetime import datetime
from models.social_metrics import SocialMetrics
from textblob import TextBlob

class SocialMediaAnalyzer:
    def __init__(self):
        self.engagement_threshold = 100  # Минимальный порог вовлеченности
        
    def analyze_social_data(self, twitter_data: Dict, reddit_data: Dict) -> SocialMetrics:
        metrics = SocialMetrics(
            symbol=twitter_data.get('symbol', ''),
            timestamp=datetime.now(),
            tweet_count=twitter_data.get('tweet_count', 0),
            retweet_count=twitter_data.get('retweet_count', 0),
            like_count=twitter_data.get('like_count', 0),
            post_count=reddit_data.get('post_count', 0),
            comment_count=reddit_data.get('comment_count', 0)
        )
        
        metrics.engagement_rate = self._calculate_engagement(twitter_data, reddit_data)
        metrics.sentiment_score = self._analyze_sentiment(twitter_data, reddit_data)
        metrics.active_users_ratio = self._calculate_active_users(twitter_data, reddit_data)
        metrics.verified_mentions_score = self._analyze_verified_mentions(twitter_data)
        
        return metrics
        
    def _calculate_engagement(self, twitter_data: Dict, reddit_data: Dict) -> float:
        total_interactions = (
            twitter_data.get('interactions', 0) + 
            reddit_data.get('total_score', 0)
        )
        return min(total_interactions / self.engagement_threshold * 100, 100)
        
    def _analyze_sentiment(self, twitter_data: Dict, reddit_data: Dict) -> float:
        sentiments = []
        
        # Анализ твитов
        for tweet in twitter_data.get('tweets', []):
            blob = TextBlob(tweet.text)
            sentiments.append(blob.sentiment.polarity)
            
        # Анализ постов Reddit
        for post in reddit_data.get('posts', []):
            blob = TextBlob(post.title + ' ' + post.selftext)
            sentiments.append(blob.sentiment.polarity)
            
        return sum(sentiments) / len(sentiments) if sentiments else 0

    def _calculate_active_users(self, twitter_data: Dict, reddit_data: Dict) -> float:
        # Implementation of _calculate_active_users method
        pass

    def _analyze_verified_mentions(self, twitter_data: Dict) -> float:
        # Implementation of _analyze_verified_mentions method
        pass 