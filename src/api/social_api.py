import tweepy
from typing import Optional, Dict
from datetime import datetime, timedelta
from textblob import TextBlob
import praw
import os

class TwitterAPI:
    def __init__(self, credentials: Dict[str, str]):
        auth = tweepy.OAuthHandler(
            credentials['api_key'], 
            credentials['api_secret']
        )
        auth.set_access_token(
            credentials['access_token'], 
            credentials['access_secret']
        )
        self.api = tweepy.API(auth)
        
    def get_metrics(self, symbol: str, start_time: datetime = None, end_time: datetime = None) -> Dict:
        try:
            query = f"#{symbol} OR ${symbol}"
            if start_time and end_time:
                tweets = self.api.search_tweets(
                    q=query, 
                    count=100,
                    until=end_time.strftime('%Y-%m-%d'),
                    since=start_time.strftime('%Y-%m-%d')
                )
            else:
                tweets = self.api.search_tweets(q=query, count=100)
                
            return {
                'tweet_count': len(tweets),
                'interactions': sum(t.favorite_count + t.retweet_count for t in tweets),
                'followers': sum(t.user.followers_count for t in tweets),
                'tweets': tweets  # Сохраняем твиты для анализа настроений
            }
        except Exception as e:
            print(f"Twitter API error: {e}")
            return {'tweet_count': 0, 'interactions': 0, 'followers': 0, 'tweets': []}

class RedditAPI:
    def __init__(self, credentials: Dict[str, str]):
        self.reddit = praw.Reddit(
            client_id=credentials['client_id'],
            client_secret=credentials['client_secret'],
            user_agent=credentials['user_agent']
        )
        
    def get_metrics(self, symbol: str, start_time: datetime = None, end_time: datetime = None) -> Dict:
        try:
            # Поиск по нескольким криптовалютным сабреддитам
            subreddits = ['CryptoCurrency', 'CryptoMarkets', 'CryptoMoonShots']
            posts = []
            comments = []
            
            for subreddit in subreddits:
                # Собираем посты
                for post in self.reddit.subreddit(subreddit).search(
                    f"{symbol}", 
                    time_filter='day', 
                    limit=100
                ):
                    posts.append(post)
                    post.comments.replace_more(limit=0)
                    comments.extend(post.comments.list())
            
            return {
                'post_count': len(posts),
                'comment_count': len(comments),
                'total_score': sum(post.score for post in posts),
                'unique_authors': len(set(post.author.name for post in posts if post.author)),
                'posts': posts,  # Для анализа настроений
                'comments': comments  # Для анализа настроений
            }
            
        except Exception as e:
            print(f"Reddit API error: {e}")
            return {
                'post_count': 0,
                'comment_count': 0,
                'total_score': 0,
                'unique_authors': 0,
                'posts': [],
                'comments': []
            }

class EnhancedSocialAnalyzer:
    def __init__(self, twitter_api: TwitterAPI, reddit_api: RedditAPI):
        self.twitter_api = twitter_api
        self.reddit_api = reddit_api
        
    async def analyze_listing_social_data(self, symbol: str, listing_time: datetime) -> Dict:
        pre_listing_window = timedelta(hours=24)
        post_listing_window = timedelta(hours=1)
        
        # Получаем данные Twitter
        twitter_data = {
            'pre_listing': self.twitter_api.get_metrics(
                symbol, 
                start_time=listing_time - pre_listing_window,
                end_time=listing_time
            ),
            'post_listing': self.twitter_api.get_metrics(
                symbol,
                start_time=listing_time,
                end_time=listing_time + post_listing_window
            )
        }
        
        # Получаем данные Reddit
        reddit_data = self.reddit_api.get_metrics(symbol)
        
        metrics = {
            'hype_score': self.calculate_hype_score(twitter_data, reddit_data),
            'growth_rate': self.calculate_growth_rate(twitter_data),
            'sentiment': self.analyze_sentiment(twitter_data, reddit_data),
            'community_strength': self.analyze_community(twitter_data, reddit_data)
        }
        
        return metrics
        
    def calculate_hype_score(self, twitter_data: Dict, reddit_data: Dict) -> float:
        twitter_score = self.calculate_growth_rate(twitter_data)
        reddit_score = (reddit_data['post_count'] + reddit_data['comment_count']) / 100
        
        return (twitter_score * 0.6 + reddit_score * 0.4)
        
    def calculate_growth_rate(self, twitter_data: Dict) -> float:
        """Расчет скорости роста интереса"""
        pre_count = max(twitter_data['pre_listing']['tweet_count'], 1)
        post_count = twitter_data['post_listing']['tweet_count']
        return ((post_count - pre_count) / pre_count) * 100
        
    def analyze_sentiment(self, twitter_data: Dict, reddit_data: Dict) -> float:
        sentiments = []
        
        # Twitter sentiment
        for period in ['pre_listing', 'post_listing']:
            for tweet in twitter_data[period]['tweets']:
                blob = TextBlob(tweet.text)
                sentiments.append(blob.sentiment.polarity)
                
        # Reddit sentiment
        for post in reddit_data['posts']:
            blob = TextBlob(post.title + ' ' + post.selftext)
            sentiments.append(blob.sentiment.polarity)
            
        for comment in reddit_data['comments']:
            blob = TextBlob(comment.body)
            sentiments.append(blob.sentiment.polarity)
                
        return sum(sentiments) / len(sentiments) if sentiments else 0
        
    def analyze_community(self, twitter_data: Dict, reddit_data: Dict) -> float:
        """Анализ силы сообщества"""
        pre_count = max(twitter_data['pre_listing']['tweet_count'], 1)
        post_count = twitter_data['post_listing']['tweet_count']
        
        if post_count == 0:
            return 0
            
        growth_rate = ((post_count - pre_count) / pre_count) * 100
        sentiment = self.analyze_sentiment(twitter_data, reddit_data)
        
        return (growth_rate * 0.5 + sentiment * 0.5) * 100 