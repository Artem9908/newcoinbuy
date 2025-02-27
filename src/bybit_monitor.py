import os
import time
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
import json
from collections import OrderedDict
import hmac
import hashlib
import urllib.parse
import time
import threading
from enum import Enum
import numpy as np
import sys
import re
from typing import Dict, Optional, Tuple
from api.social_api import TwitterAPI, RedditAPI, EnhancedSocialAnalyzer
from database.db import Database
from api.orderbook_analyzer import OrderBookAnalyzer
from utils.api_utils import retry_on_failure, APICache
from models.token_metrics import TokenMetrics
from models.social_metrics import SocialMetrics
from models.historical_patterns import HistoricalPatterns
from pathlib import Path
from analyzers.market_data_analyzer import MarketDataAnalyzer
from analyzers.social_media_analyzer import SocialMediaAnalyzer
from analyzers.historical_data_analyzer import HistoricalDataAnalyzer
from api.dex_screener_api import DexScreenerAPI
from api.data_collector import EnhancedDataCollector
import statistics
import math

# Load environment variables
env_path = Path(__file__).parent.parent / 'config' / '.env'
load_dotenv(env_path)

# Проверяем наличие необходимых переменных
required_vars = [
    'TWITTER_API_KEY', 
    'TWITTER_API_SECRET',
    'TWITTER_ACCESS_TOKEN', 
    'TWITTER_ACCESS_SECRET',
    'REDDIT_CLIENT_ID',
    'REDDIT_SECRET',
    'CMC_API_KEY',
    'GOOGLE_API_KEY',
    'GITHUB_TOKEN',
    'COINGECKO_API_KEY'
]

missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    print(f"Warning: Missing environment variables: {', '.join(missing_vars)}")
    print("Some features may be limited. Add them to config/.env file for full functionality")

class MarketData:
    def __init__(self):
        self.volume_24h: float = 0
        self.market_cap: float = 0
        self.price_change_24h: float = 0
        self.total_supply: float = 0
        self.max_supply: Optional[float] = None
        self.circulating_supply: Optional[float] = None
        self.exchanges_listed: int = 0
        self.price: float = 0

class TradingStrategy(Enum):
    AGGRESSIVE_PUMP = {
        'name': "Aggressive Pump Strategy",
        'hold_time': '3-15 minutes',
        'take_profits': [20, 30, 50],
        'stop_loss': -8,
        'leverage': 5,
        'trailing_stop': 10
    }
    BALANCED_PUMP = {
        'name': "Balanced Pump Strategy",
        'hold_time': '15-45 minutes',
        'take_profits': [15, 25, 40],
        'stop_loss': -10,
        'leverage': 3,
        'trailing_stop': 15
    }
    MOMENTUM = {
        'name': "Momentum Strategy",
        'hold_time': '1-3 hours',
        'take_profits': [30, 45, 70],
        'stop_loss': -12,
        'leverage': 3,
        'trailing_stop': 20
    }

    def get_strategy_params(self):
        """Get strategy parameters"""
        return self.value

    @staticmethod
    def analyze_initial_listing_strategy(symbol: str, market_data: MarketData) -> 'TradingStrategy':
        """Analyze strategy specifically for initial listing conditions"""
        # Token type analysis
        meme_indicators = ['PEPE', 'MEME', 'DOGE', 'SHIB', 'BABY', 'ELON', 'MOON', 'SAFE', 'INU', 'AI']
        gaming_indicators = ['GAME', 'PLAY', 'WIN', 'GUILD', 'QUEST', 'RPG', 'META']
        defi_indicators = ['SWAP', 'YIELD', 'LEND', 'STAKE', 'FI', 'DEX']
        
        is_meme = any(indicator in symbol.upper() for indicator in meme_indicators)
        is_gaming = any(indicator in symbol.upper() for indicator in gaming_indicators)
        is_defi = any(indicator in symbol.upper() for indicator in defi_indicators)
        
        # Market cap thresholds adjusted based on performance
        MICRO_CAP = 3_000_000  # $3M
        SMALL_CAP = 15_000_000  # $15M
        
        # Volume analysis
        daily_volume = market_data.volume_24h if market_data.volume_24h else 0
        volume_per_cap = daily_volume / market_data.market_cap if market_data.market_cap else 0
        
        # Strategy selection with improved logic
        if is_meme or (market_data.market_cap < MICRO_CAP and volume_per_cap > 0.1):
            return TradingStrategy.AGGRESSIVE_PUMP
        elif (is_gaming or is_defi or MICRO_CAP <= market_data.market_cap < SMALL_CAP):
            return TradingStrategy.BALANCED_PUMP
        else:
            return TradingStrategy.MOMENTUM

class BybitMonitor:
    def __init__(self):
        self.api_key = os.getenv('BYBIT_API_KEY')
        self.api_secret = os.getenv('BYBIT_API_SECRET')
        self.testnet = os.getenv('TESTNET', 'false').lower() == 'true'
        
        # Initialize all API endpoints
        self.base_url = "https://api.bybit.com"
        self.coingecko_url = "https://api.coingecko.com/api/v3"
        self.cmc_url = "https://pro-api.coinmarketcap.com/v1"
        self.dex_screener_url = "https://api.dexscreener.com/latest"
        
        # API Keys
        self.cmc_api_key = os.getenv('CMC_API_KEY')
        self.google_api_key = os.getenv('GOOGLE_API_KEY')
        self.github_token = os.getenv('GITHUB_TOKEN')
        
        # Add CoinGecko API key
        self.coingecko_api_key = os.getenv('COINGECKO_API_KEY')
        
        # Required environment variables check
        required_vars = [
            'TWITTER_API_KEY', 
            'TWITTER_API_SECRET',
            'TWITTER_ACCESS_TOKEN', 
            'TWITTER_ACCESS_SECRET',
            'REDDIT_CLIENT_ID',
            'REDDIT_SECRET',
            'CMC_API_KEY',
            'GOOGLE_API_KEY',
            'GITHUB_TOKEN',
            'COINGECKO_API_KEY'
        ]

        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            print(f"Warning: Missing environment variables: {', '.join(missing_vars)}")
            print("Some features may be limited. Add them to config/.env file for full functionality")
        
        # Initialize data storage
        self.known_symbols = set()
        self.listing_history = OrderedDict()
        self.active_trades = {}
        self.market_data_cache: Dict[str, MarketData] = {}
        
        print("\nInitializing Bybit monitor and all components...")
        
        # Initialize API clients with proper error handling
        try:
            # Social Media APIs
            twitter_credentials = {
                'api_key': os.getenv('TWITTER_API_KEY'),
                'api_secret': os.getenv('TWITTER_API_SECRET'),
                'access_token': os.getenv('TWITTER_ACCESS_TOKEN'),
                'access_secret': os.getenv('TWITTER_ACCESS_SECRET')
            }
            
            reddit_credentials = {
                'client_id': os.getenv('REDDIT_CLIENT_ID'),
                'client_secret': os.getenv('REDDIT_SECRET'),
                'user_agent': os.getenv('REDDIT_USER_AGENT', 'Bybit_Listing_Monitor')
            }
            
            try:
                self.twitter_api = TwitterAPI(twitter_credentials)
                self.reddit_api = RedditAPI(reddit_credentials)
                self.social_analyzer = EnhancedSocialAnalyzer(self.twitter_api, self.reddit_api)
                print("✓ Social media analyzers initialized")
            except Exception as e:
                print("⚠️ Social media analyzers initialization failed, some features will be limited")
            
            try:
                # Database
                self.db = Database()
                print("✓ Database connection established")
            except Exception as e:
                print("⚠️ Database initialization failed, data persistence will be limited")
            
            try:
                # Analysis Components
                self.market_analyzer = MarketDataAnalyzer()
                self.social_analyzer = SocialMediaAnalyzer()
                self.historical_analyzer = HistoricalDataAnalyzer()
                self.orderbook_analyzer = OrderBookAnalyzer()
                self.dex_screener = DexScreenerAPI()
                print("✓ Analysis components initialized")
            except Exception as e:
                print("⚠️ Some analysis components failed to initialize, analysis capabilities will be limited")
            
            try:
                # Data collectors
                self.data_collector = EnhancedDataCollector(
                    github_token=self.github_token,
                    google_api_key=self.google_api_key
                )
                print("✓ Data collectors initialized")
            except Exception as e:
                print("⚠️ Data collectors initialization failed, some data sources will be unavailable")
            
            try:
                # Cache system
                self.api_cache = APICache()
                print("✓ Cache system initialized")
            except Exception as e:
                print("⚠️ Cache system initialization failed, performance may be affected")
            
            try:
                # Initialize known symbols
                self.initialize_known_symbols()
                print("✓ Known symbols loaded")
            except Exception as e:
                print("⚠️ Failed to load known symbols, will attempt to recover during runtime")
            
        except Exception as e:
            print(f"\n⚠️ Some components failed to initialize")
            print("The system will continue with limited functionality")
        
        print("\nMonitor initialized and ready!")

    def get_signature(self, params, timestamp):
        """Generate signature for authenticated requests"""
        param_str = str(timestamp) + self.api_key + str(params)
        hash = hmac.new(bytes(self.api_secret, "utf-8"), param_str.encode("utf-8"), hashlib.sha256)
        return hash.hexdigest()

    def get_server_time(self):
        """Get Bybit server time"""
        url = f"{self.base_url}/v5/market/time"
        response = requests.get(url)
        data = response.json()
        if data and 'result' in data and 'timeSecond' in data['result']:
            return int(data['result']['timeSecond'])
        return int(time.time())

    def get_tickers(self, silent=False):
        """Get all spot tickers from Bybit"""
        url = f"{self.base_url}/v5/market/tickers"
        params = {
            "category": "spot"
        }
        if not silent:
            print("Fetching tickers...")
        response = requests.get(url, params=params)
        return response.json()

    def get_kline_data(self, symbol):
        """Get kline data for a symbol to determine trading start time"""
        url = f"{self.base_url}/v5/market/kline"
        params = {
            "category": "spot",
            "symbol": symbol,
            "interval": "240",  # 4-hour candles
            "limit": 200  # Get maximum allowed candles
        }
        response = requests.get(url, params=params)
        return response.json()

    def get_announcements(self):
        """Get recent announcements from Bybit"""
        try:
            url = "https://api.bybit.com/v5/announcements/index"
            params = {
                "locale": "en-US",
                "type": "new_crypto",  # Changed from category and tag to type
                "page": 1,
                "limit": 50
            }
            
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            response = requests.get(url, params=params, headers=headers)
            if response.status_code != 200:
                print(f"Error fetching announcements: {response.status_code}")
                print(f"Response: {response.text}")
                return {}
                
            data = response.json()
            if data.get('retCode') != 0:
                print(f"API Error: {data.get('retMsg')}")
                return {}
                
            return data
            
        except Exception as e:
            print(f"Error fetching announcements: {str(e)}")
            return {}

    def parse_listing_time(self, title):
        """Parse listing time from announcement title"""
        try:
            # Example: "New Listing: AVLUSDT Perpetual Contract, with up to 25x leverage"
            if "listing" in title.lower():
                # Try to find a date in the title
                date_parts = [part for part in title.split() if "202" in part]  # Look for year
                if date_parts:
                    return datetime.strptime(date_parts[0], "%Y-%m-%d")
            return None
        except:
            return None

    def initialize_known_symbols(self):
        """Initialize the set of known symbols and find recent listings"""
        try:
            # Get current trading pairs
            response = self.get_tickers()
            if response and 'result' in response and 'list' in response['result']:
                for item in response['result']['list']:
                    symbol = item['symbol']
                    if symbol.endswith('USDT'):
                        self.known_symbols.add(symbol)
                print(f"Found {len(self.known_symbols)} USDT trading pairs")

            # Get recent listings from announcements
            announcements = self.get_announcements()
            if announcements and 'result' in announcements and 'list' in announcements['result']:
                print("Processing announcements...")
                for announcement in announcements['result']['list']:
                    title = announcement.get('title', '')
                    if 'listing' in title.lower() and 'usdt' in title.lower():
                        # Try to extract the symbol
                        words = title.split()
                        for word in words:
                            if word.endswith('USDT'):
                                symbol = word
                                # Get listing time from announcement
                                listing_time = datetime.fromtimestamp(int(announcement['dateTimestamp'])/1000)
                                self.listing_history[symbol] = listing_time

                print(f"Found {len(self.listing_history)} recent listings from announcements")
                if self.listing_history:
                    self.print_recent_listings()
                
        except Exception as e:
            print(f"Error initializing symbols: {str(e)}")

    def check_new_listings(self):
        """Check for new listings on Bybit"""
        try:
            announcements = self.get_announcements()
            if announcements and 'result' in announcements and 'list' in announcements['result']:
                for announcement in announcements['result']['list']:
                    title = announcement.get('title', '')
                    if 'listing' in title.lower() and 'usdt' in title.lower():
                        # Try to extract the symbol
                        words = title.split()
                        for word in words:
                            if word.endswith('USDT') and word not in self.listing_history:
                                listing_time = datetime.fromtimestamp(int(announcement['dateTimestamp'])/1000)
                                self.handle_new_listing(word, listing_time)
                
        except Exception as e:
            print(f"Error checking new listings: {str(e)}")

    def get_ticker_info(self, symbol):
        """Get current price and volume info for a symbol"""
        url = f"{self.base_url}/v5/market/tickers"
        params = {
            "category": "spot",
            "symbol": symbol
        }
        response = requests.get(url, params=params)
        return response.json()

    def get_klines(self, symbol, interval="1", limit=200):
        """Get kline/candlestick data for analysis"""
        url = f"{self.base_url}/v5/market/kline"
        params = {
            "category": "spot",
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        response = requests.get(url, params=params)
        return response.json()

    def get_coingecko_data(self, symbol: str) -> Optional[MarketData]:
        """Get detailed market data from CoinGecko using free API with rate limiting"""
        # Remove USDT suffix and handle common variations
        coin_name = symbol.replace('USDT', '').lower()
        
        # Try multiple search variations
        search_variations = [
            coin_name,
            coin_name.replace('3l', ''),
            coin_name.replace('3s', ''),
            coin_name.replace('up', ''),
            coin_name.replace('down', ''),
            coin_name.split('_')[0] if '_' in coin_name else coin_name,
            coin_name.split('-')[0] if '-' in coin_name else coin_name,
        ]
        
        # Free API rate limits: 10-30 calls/minute
        max_retries = 3
        base_delay = 6.0  # 6 seconds between calls for free API
        
        # Try each variation with retry mechanism
        for search_term in search_variations:
            for attempt in range(max_retries):
                try:
                    # Search for the coin
                    search_url = f"{self.coingecko_url}/search"
                    response = requests.get(
                        search_url,
                        params={'query': search_term}
                    )
                    
                    if response.status_code == 429:  # Rate limit
                        retry_delay = base_delay * (attempt + 1)  # Exponential backoff
                        print(f"⚠️ CoinGecko rate limit hit, waiting {retry_delay}s...")
                        time.sleep(retry_delay)
                        continue
                        
                    if response.status_code != 200:
                        print(f"❌ CoinGecko API error: {response.status_code}")
                        time.sleep(base_delay)
                        break
                        
                    search_data = response.json()
                    if not search_data.get('coins'):
                        time.sleep(base_delay)
                        continue
                        
                    # Get the first matching coin's ID
                    coin_id = search_data['coins'][0]['id']
                    
                    # Wait before next API call
                    time.sleep(base_delay)
                    
                    # Get detailed coin data
                    coin_url = f"{self.coingecko_url}/coins/{coin_id}"
                    response = requests.get(
                        coin_url,
                        params={
                            'localization': 'false',
                            'tickers': 'true',
                            'market_data': 'true',
                            'community_data': 'false',
                            'developer_data': 'false'
                        }
                    )
                    
                    if response.status_code == 429:
                        retry_delay = base_delay * (attempt + 1)
                        print(f"⚠️ CoinGecko rate limit hit, waiting {retry_delay}s...")
                        time.sleep(retry_delay)
                        continue
                        
                    if response.status_code != 200:
                        print(f"❌ CoinGecko API error: {response.status_code}")
                        time.sleep(base_delay)
                        break
                        
                    coin_data = response.json()
                    market_data = MarketData()
                    
                    # Extract relevant data
                    market_data.price = coin_data['market_data']['current_price'].get('usd', 0)
                    market_data.volume_24h = coin_data['market_data']['total_volume'].get('usd', 0)
                    market_data.market_cap = coin_data['market_data']['market_cap'].get('usd', 0)
                    market_data.price_change_24h = coin_data['market_data']['price_change_percentage_24h'] or 0
                    market_data.total_supply = coin_data['market_data']['total_supply'] or 0
                    market_data.max_supply = coin_data['market_data']['max_supply']
                    market_data.circulating_supply = coin_data['market_data']['circulating_supply']
                    market_data.exchanges_listed = len(coin_data.get('tickers', []))
                    
                    # Verify we have valid data
                    if market_data.price > 0 or market_data.market_cap > 0:
                        print(f"✓ Found CoinGecko data for {symbol}")
                        return market_data
                        
                except Exception as e:
                    print(f"⚠️ CoinGecko error for {search_term}: {str(e)}")
                    if attempt < max_retries - 1:
                        time.sleep(base_delay * (attempt + 1))
                    continue
                
                time.sleep(base_delay)  # Wait between variations
        
        print(f"❌ No valid CoinGecko data found for {symbol}")
        return None

    def get_coinmarketcap_data(self, symbol: str) -> Optional[MarketData]:
        """Get detailed market data from CoinMarketCap"""
        try:
            if not self.cmc_api_key:
                print("CoinMarketCap API key not found. Add CMC_API_KEY to your .env file")
                return None

            # Remove USDT suffix and handle variations
            coin_name = symbol.replace('USDT', '').lower()
            search_variations = [
                coin_name,
                coin_name.replace('3l', ''),
                coin_name.replace('3s', ''),
                coin_name.replace('up', ''),
                coin_name.replace('down', ''),
                coin_name.split('_')[0] if '_' in coin_name else coin_name,
                coin_name.split('-')[0] if '-' in coin_name else coin_name,
            ]

            headers = {
                'X-CMC_PRO-API-KEY': self.cmc_api_key,
                'Accept': 'application/json'
            }

            for search_term in search_variations:
                try:
                    # Search for the coin
                    search_url = f"{self.cmc_url}/cryptocurrency/quotes/latest"
                    response = requests.get(
                        search_url,
                        headers=headers,
                        params={
                            'symbol': search_term.upper(),
                            'convert': 'USD'
                        }
                    )

                    if response.status_code != 200:
                        continue

                    data = response.json()
                    if 'data' not in data or not data['data']:
                        continue

                    # Get the first matching coin's data
                    coin_data = next(iter(data['data'].values()))
                    quote = coin_data['quote']['USD']

                    market_data = MarketData()
                    market_data.price = quote.get('price', 0)
                    market_data.volume_24h = quote.get('volume_24h', 0)
                    market_data.market_cap = quote.get('market_cap', 0)
                    market_data.price_change_24h = quote.get('percent_change_24h', 0)
                    market_data.total_supply = coin_data.get('total_supply', 0)
                    market_data.max_supply = coin_data.get('max_supply')
                    market_data.circulating_supply = coin_data.get('circulating_supply')
                    market_data.exchanges_listed = coin_data.get('num_market_pairs', 1)

                    if market_data.price > 0 or market_data.market_cap > 0:
                        print(f"Found CoinMarketCap data using search term: {search_term}")
                        return market_data

                except Exception as e:
                    print(f"Error fetching CMC data for variation {search_term}: {str(e)}")
                    continue

            print(f"No valid CoinMarketCap data found for {symbol}")
            return None

        except Exception as e:
            print(f"Error in CoinMarketCap data fetch for {symbol}: {str(e)}")
            return None

    def analyze_trading_strategy(self, symbol: str) -> TradingStrategy:
        market_data = self.get_coingecko_data(symbol)
        listing_time = datetime.now()
        social_data = self.social_analyzer.analyze_listing_social_data(symbol, listing_time)
        dex_data = self.dex_screener.get_token_data(symbol)
        
        # Если нет рыночных данных (новая монета)
        if not market_data:
            # Используем комбинацию соц.метрик и DEX данных
            social_score = (
                social_data.get('hype_score', 0) * 0.4 +
                social_data.get('sentiment', 0) * 0.3 +
                social_data.get('community_strength', 0) * 0.3
            )
            
            dex_score = self.calculate_dex_score(dex_data) if dex_data else 0
            
            combined_score = social_score * 0.6 + dex_score * 0.4
            
            if combined_score > 70:
                return TradingStrategy.AGGRESSIVE_PUMP
            elif combined_score > 40:
                return TradingStrategy.BALANCED_PUMP
            else:
                return TradingStrategy.MOMENTUM

    def get_order_book(self, symbol):
        """Get order book data for a symbol"""
        url = f"{self.base_url}/v5/market/orderbook"
        params = {
            "category": "spot",
            "symbol": symbol,
            "limit": 50
        }
        response = requests.get(url, params=params)
        return response.json()

    def analyze_liquidity(self, order_book):
        """Analyze order book liquidity"""
        if not order_book or 'result' not in order_book:
            return 0
            
        bids = order_book['result'].get('b', [])
        asks = order_book['result'].get('a', [])
        
        if not bids or not asks:
            return 0
            
        # Calculate bid-ask spread
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        spread = (best_ask - best_bid) / best_bid
        
        # Calculate depth
        bid_depth = sum(float(bid[1]) for bid in bids[:10])
        ask_depth = sum(float(ask[1]) for ask in asks[:10])
        total_depth = bid_depth + ask_depth
        
        # Score from 0 to 1 based on spread and depth
        spread_score = max(0, 1 - spread * 100)  # Lower spread = better
        depth_score = min(1, total_depth / 1000000)  # Higher depth = better
        
        return (spread_score * 0.3 + depth_score * 0.7)  # Weight depth more than spread

    def monitor_trade(self, symbol, strategy):
        """Monitor an active trade and provide updates"""
        start_time = datetime.now()
        initial_price = None
        max_price = 0
        min_price = float('inf')
        monitoring = True
        
        print("\nStarting trade monitor for", symbol)
        print("Press Ctrl+C to stop monitoring\n")
        
        try:
            while monitoring:
                ticker = self.get_ticker_info(symbol)
                if ticker and 'result' in ticker and 'list' in ticker['result']:
                    current_price = float(ticker['result']['list'][0]['lastPrice'])
                    
                    if initial_price is None:
                        initial_price = current_price
                        print(f"\n💰 Initial price for {symbol}: {initial_price} USDT")
                    
                    price_change = ((current_price - initial_price) / initial_price) * 100
                    max_price = max(max_price, current_price)
                    min_price = min(min_price, current_price)
                    elapsed_time = datetime.now() - start_time
                    
                    self.analyze_trade_status(symbol, strategy, elapsed_time, initial_price, 
                                           current_price, max_price, min_price)
                
                time.sleep(10)  # Check every 10 seconds
                
        except KeyboardInterrupt:
            print("\n\nStopping trade monitor...")
            print(f"Final stats for {symbol}:")
            if initial_price:
                final_change = ((current_price - initial_price) / initial_price) * 100
                print(f"Initial Price: {initial_price:.8f} USDT")
                print(f"Final Price: {current_price:.8f} USDT")
                print(f"Total Change: {final_change:.2f}%")
                print(f"Max Price Reached: {max_price:.8f} USDT")
                print(f"Min Price Reached: {min_price:.8f} USDT")
            return
        except Exception as e:
            print(f"Error monitoring {symbol}: {str(e)}")

    def analyze_trade_status(self, symbol, strategy, elapsed_time, initial_price, 
                           current_price, max_price, min_price):
        """Analyze trade status and provide recommendations"""
        price_change = ((current_price - initial_price) / initial_price) * 100
        max_change = ((max_price - initial_price) / initial_price) * 100
        
        print(f"\n📊 {symbol} Update ({elapsed_time.total_seconds():.0f}s):")
        print(f"Current Price: {current_price:.8f} USDT (Change: {price_change:.2f}%)")
        print(f"Max Price: {max_price:.8f} USDT (Max Change: {max_change:.2f}%)")
        
        params = strategy.get_strategy_params()
        
        if strategy == TradingStrategy.AGGRESSIVE_PUMP:
            if elapsed_time.total_seconds() > 900:  # 15 minutes
                print("⚠️ ALERT: Maximum hold time reached for Aggressive Pump strategy!")
                print("🎯 Recommendation: SELL NOW")
            elif price_change >= 20:
                print("🎯 Target reached! Consider taking profits")
                print("Use trailing stop-loss at -12% from current price")
            elif price_change <= -10:
                print("⚠️ Stop loss triggered! Consider cutting losses")
                
        elif strategy == TradingStrategy.BALANCED_PUMP:
            if elapsed_time.total_seconds() > 900:  # 15 minutes
                print("⚠️ ALERT: Maximum hold time reached for Balanced Pump strategy!")
                print("🎯 Recommendation: SELL NOW")
            elif price_change >= 25:
                print("🎯 Target reached! Consider taking profits")
            elif price_change <= -15:
                print("⚠️ Stop loss triggered! Consider cutting losses")
                
        else:  # MOMENTUM
            if elapsed_time.total_seconds() > 10800:  # 3 hours
                print("⚠️ ALERT: Maximum hold time reached for Momentum strategy!")
                print("🎯 Recommendation: SELL NOW")
            elif price_change >= 30:
                print("🎯 Target reached! Consider taking profits")
            elif price_change <= -15:
                print("⚠️ Stop loss triggered! Consider cutting losses")

    @retry_on_failure(max_retries=3)
    async def handle_new_listing(self, symbol: str):
        listing_time = datetime.utcnow()
        
        # Получаем все данные
        market_data = self.get_coingecko_data(symbol)
        social_data = await self.social_analyzer.analyze_listing_social_data(symbol, listing_time)
        order_book = self.get_order_book(symbol)
        
        # Оригинальный анализ
        market_metrics = self.analyze_market_metrics(market_data)
        liquidity_metrics = self.analyze_liquidity(order_book)
        
        # Новый расширенный анализ ордербука
        orderbook_analysis = self.orderbook_analyzer.analyze_orderbook(order_book)
        
        # Комбинируем все метрики
        combined_metrics = {
            # Оригинальные метрики
            **market_metrics,
            **liquidity_metrics,
            
            # Рыночные данные
            'market_cap': market_data.market_cap,
            'volume_24h': market_data.volume_24h,
            'price': market_data.price,
            'price_change_24h': market_data.price_change_24h,
            
            # Данные поставок
            'total_supply': market_data.total_supply,
            'circulating_supply': market_data.circulating_supply,
            'max_supply': market_data.max_supply,
            
            # Социальные метрики
            'social_score': social_data['hype_score'],
            'sentiment_score': social_data['sentiment'],
            'community_strength': social_data['community_strength'],
            'growth_rate': social_data['growth_rate'],
            
            # Расширенные данные ордербука
            'depth_score': orderbook_analysis['depth_score'],
            'buy_pressure': orderbook_analysis['buy_pressure'],
            'volatility_risk': orderbook_analysis['volatility_risk'],
            
            # JSON данные для истории
            'orderbook_analysis': orderbook_analysis,
            'social_metrics': social_data
        }
        
        # Сохраняем в базу
        self.db.insert_listing_data(symbol, combined_metrics)
        
        # Определяем стратегию с учетом всех факторов
        total_score = (
            market_metrics['market_cap_score'] * 0.2 +
            market_metrics['volume_score'] * 0.2 +
            market_metrics['volatility_score'] * 0.15 +
            market_metrics['exchange_score'] * 0.1 +
            combined_metrics['social_score'] * 0.15 +
            combined_metrics['sentiment_score'] * 0.1 +
            liquidity_metrics['liquidity_score'] * 0.1
        )
        
        # Выбор стратегии с учетом всех факторов
        if (total_score < 30 or 
            market_metrics['volatility_score'] > 50 or 
            combined_metrics['social_score'] > 80):
            strategy = TradingStrategy.AGGRESSIVE_PUMP
        elif (total_score < 60 or 
              market_metrics['volatility_score'] > 30 or 
              combined_metrics['social_score'] > 50):
            strategy = TradingStrategy.BALANCED_PUMP
        else:
            strategy = TradingStrategy.MOMENTUM
            
        # Корректируем параметры стратегии
        strategy_params = strategy.value.copy()
        if combined_metrics['social_score'] > 70:
            strategy_params['take_profits'] = [x * 1.2 for x in strategy_params['take_profits']]
        if combined_metrics['sentiment_score'] < 0:
            strategy_params['stop_loss'] = strategy_params['stop_loss'] * 0.8
        if combined_metrics['buy_pressure'] > 0.7:
            strategy_params['leverage'] = min(strategy_params['leverage'] + 1, 5)
            
        return {
            'strategy': strategy,
            'parameters': strategy_params,
            'metrics': combined_metrics,
            'analysis_time': listing_time
        }

    def analyze_market_metrics(self, market_data) -> Dict[str, float]:
        """Сохраняем оригинальный анализ рыночных метрик"""
        market_cap_score = min(market_data.market_cap / 1_000_000, 100) if market_data.market_cap else 0
        volume_score = min(market_data.volume_24h / 100_000, 100) if market_data.volume_24h else 0
        volatility_score = abs(market_data.price_change_24h) if market_data.price_change_24h else 0
        exchange_score = min(market_data.exchanges_listed / 5, 20) if market_data.exchanges_listed else 0
        
        return {
            'market_cap_score': market_cap_score,
            'volume_score': volume_score,
            'volatility_score': volatility_score,
            'exchange_score': exchange_score
        }

    def analyze_liquidity(self, order_book) -> Dict[str, float]:
        """Сохраняем оригинальный анализ ликвидности"""
        if not order_book or 'result' not in order_book:
            return {'liquidity_score': 0, 'spread': 0}
            
        bids = order_book['result'].get('b', [])
        asks = order_book['result'].get('a', [])
        
        if not bids or not asks:
            return {'liquidity_score': 0, 'spread': 0}
            
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        spread = ((best_ask - best_bid) / best_bid) * 100
        
        bid_depth = sum(float(bid[1]) for bid in bids[:10])
        ask_depth = sum(float(ask[1]) for ask in asks[:10])
        total_depth = bid_depth + ask_depth
        
        spread_score = max(0, 1 - spread * 100)
        depth_score = min(1, total_depth / 1000000)
        
        return {
            'liquidity_score': (spread_score * 0.4 + depth_score * 0.6) * 100,
            'spread': spread
        }

    def get_recent_listings(self, n=10):
        """Get the n most recent listings with their timestamps"""
        # Sort by timestamp (most recent first)
        sorted_listings = sorted(self.listing_history.items(), key=lambda x: x[1], reverse=True)
        return sorted_listings[:n]

    def print_recent_listings(self):
        """Print recent listings in a formatted way"""
        print("\nLast 10 new listings:")
        print("-" * 50)
        
        # Get all listings sorted by time
        sorted_listings = sorted(self.listing_history.items(), 
                               key=lambda x: x[1], 
                               reverse=True)
        
        # Show last 10 listings
        for symbol, listing_time in sorted_listings[:10]:
            print(f"{symbol:<20} listed at {listing_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 50)

    def run(self, check_interval=1):
        """Run the monitor with specified interval in seconds"""
        print("\nMonitor is running...")
        print("Commands:")
        print("- Press 'h' to show recent listings")
        print("- Press 'q' to quit")
        print("\nWaiting for new listings...")
        
        import sys
        import select
        import tty
        import termios

        # Save terminal settings
        old_settings = termios.tcgetattr(sys.stdin)
        try:
            # Set terminal to raw mode
            tty.setraw(sys.stdin.fileno())
            
            while True:
                # Check for new listings
                self.check_new_listings()
                
                # Check for keyboard input
                if select.select([sys.stdin], [], [], 0)[0]:
                    char = sys.stdin.read(1)
                    if char == 'h':
                        # Restore terminal settings temporarily
                        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                        self.print_recent_listings()
                        print("\nWaiting for new listings...")
                        # Set back to raw mode
                        tty.setraw(sys.stdin.fileno())
                    elif char == 'q':
                        print("\nExiting...")
                        break
                
                time.sleep(check_interval)
                
        finally:
            # Restore terminal settings
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    def analyze_listing(self, symbol):
        """Analyze trading strategy for a symbol without starting monitoring"""
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n🔔 ANALYZING {symbol}")
        print("-" * 50)
        
        # Get market data
        ticker = self.get_ticker_info(symbol)
        if ticker and 'result' in ticker and 'list' in ticker['result']:
            data = ticker['result']['list'][0]
            current_price = float(data.get('lastPrice', 0))
            volume = float(data.get('volume24h', 0))
            
            print(f"Current Price: {current_price:.8f} USDT")
            print(f"24h Volume: {volume:.2f} USDT")
            
            # Analyze and select trading strategy
            strategy = self.analyze_trading_strategy(symbol)
            print(f"\n📈 Selected Strategy: {strategy.value['name']}")
            
            params = strategy.get_strategy_params()
            print(f"Target Hold Time: {params['hold_time']}")
            print(f"Take Profit Targets: {', '.join(f'{tp}%' for tp in params['take_profits'])}")
            print(f"Stop Loss: {params['stop_loss']}%")
            
            # Get order book data
            order_book = self.get_order_book(symbol)
            liquidity_score = self.analyze_liquidity(order_book)
            print(f"\nLiquidity Score: {liquidity_score:.2f}")
            
            # Additional analysis
            unusual_name_indicators = ['PEPE', 'MEME', 'DOGE', 'SHIB', 'BABY', 'ELON', 'MOON', 'SAFE', 'JAIL', 'TOOL', 'INU']
            is_meme_token = any(indicator in symbol.upper() for indicator in unusual_name_indicators)
            if is_meme_token:
                print("⚠️ Meme/Unusual Token Name Detected")
            
        print("-" * 50)

    def simulate_trade(self, symbol, strategy, klines_data):
        """Simulate a trade with the given strategy"""
        try:
            if not klines_data.get('result', {}).get('list'):
                return {'result': 0, 'max_profit': 0, 'exit_type': 'error'}
            
            kline_data = sorted(klines_data['result']['list'], key=lambda x: int(x[0]))
            entry_price = float(kline_data[0][1])
            leverage = strategy.value['leverage']
            max_profit = 0
            trailing_stop = None
            
            # For HYPE strategy, focus on first 5 minutes
            if 'HYPE' in strategy.value['name']:
                kline_data = kline_data[:5]
            
            for i, kline in enumerate(kline_data):
                high = float(kline[2])
                low = float(kline[3])
                
                # Calculate raw price changes
                high_change = ((high - entry_price) / entry_price) * 100
                low_change = ((low - entry_price) / entry_price) * 100
                
                # Apply leverage
                leveraged_high = high_change * leverage
                leveraged_low = low_change * leverage
                
                # Update max profit and trailing stop
                if leveraged_high > max_profit:
                    max_profit = leveraged_high
                    trailing_stop = max_profit * (1 - strategy.value['trailing_stop']/100)
                
                # Check take profits
                for tp in strategy.value['take_profits']:
                    if leveraged_high >= tp:
                        return {
                            'result': tp,
                            'max_profit': max_profit,
                            'exit_type': 'take_profit'
                        }
                
                # Check stop loss
                if leveraged_low <= strategy.value['stop_loss']:
                    return {
                        'result': strategy.value['stop_loss'],
                        'max_profit': max_profit,
                        'exit_type': 'stop_loss'
                    }
                
                # Check trailing stop
                if trailing_stop and leveraged_low <= trailing_stop:
                    return {
                        'result': trailing_stop,
                        'max_profit': max_profit,
                        'exit_type': 'trailing_stop'
                    }
            
            # If no exit triggered, return current position value
            return {
                'result': leveraged_low,
                'max_profit': max_profit,
                'exit_type': 'time_exit'
            }
            
        except Exception as e:
            print(f"Error in trade simulation: {str(e)}")
            return {'result': 0, 'max_profit': 0, 'exit_type': 'error'}

    def extract_symbol(self, title):
        """Extract clean symbol from announcement title"""
        try:
            # Common patterns in titles
            patterns = [
                r'([A-Z0-9]+)(?:\/)?USDT',  # Matches BTCUSDT or BTC/USDT
                r'of\s+([A-Z0-9]+)\s+on',   # Matches "Listing of BTC on"
                r':\s+([A-Z0-9]+)(?:\/)?USDT' # Matches ": BTCUSDT" or ": BTC/USDT"
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, title.upper())
                if matches:
                    return matches[0] + "USDT"
            return None
        except:
            return None

    def analyze_last_listings(self):
        """Analyze all listings from the past 30 days"""
        announcements = self.get_announcements()
        
        if not announcements.get('result', {}).get('list'):
            print("❌ No announcements found")
            return
        
        print("\n🔍 LISTINGS ANALYSIS (LAST 30 DAYS)")
        print("=" * 50)
        processed_symbols = set()
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        # Initialize analytics tracking
        analytics = {
            'total_tokens': 0,
            'strategies': {'AGGRESSIVE_PUMP': 0, 'BALANCED_PUMP': 0, 'MOMENTUM': 0},
            'market_caps': [], 'volumes': [],
            'tokens_with_data': 0, 'tokens_without_data': 0,
            'data_sources': {'coingecko': 0, 'coinmarketcap': 0, 'none': 0},
            'risk_levels': {'High': 0, 'Medium': 0, 'Low': 0},
            'component_scores': {
                'market': [], 'social': [], 'dex': [], 'historical': [],
                'github': [], 'trends': [], 'orderbook': []
            },
            'parameter_adjustments': {
                'increased_tp': 0, 'decreased_tp': 0,
                'tightened_sl': 0, 'widened_sl': 0,
                'increased_leverage': 0, 'decreased_leverage': 0,
                'recovery_mode': 0
            }
        }
        
        try:
            for announcement in announcements['result']['list']:
                title = announcement['title']
                listing_time = datetime.fromtimestamp(int(announcement['dateTimestamp'])/1000)
                
                if listing_time < thirty_days_ago:
                    continue
                    
                if ('LISTING' in title.upper() or 'WILL LIST' in title.upper()) and 'USDT' in title.upper():
                    symbol = self.extract_symbol(title)
                    if symbol and symbol not in processed_symbols:
                        processed_symbols.add(symbol)
                        analytics['total_tokens'] += 1
                        
                        print(f"\n📌 {symbol} ({listing_time.strftime('%Y-%m-%d %H:%M')})")
                        print("-" * 40)
                        
                        # Gather and analyze data
                        token_data = self.get_comprehensive_token_data(symbol, listing_time)
                        
                        # Update analytics
                        if token_data['market_data']:
                            analytics['tokens_with_data'] += 1
                            if token_data.get('market_data_source') == 'coingecko':
                                analytics['data_sources']['coingecko'] += 1
                            else:
                                analytics['data_sources']['coinmarketcap'] += 1
                        else:
                            analytics['tokens_without_data'] += 1
                            analytics['data_sources']['none'] += 1
                        
                        # Analyze strategy
                        strategy, params = self.analyze_comprehensive_strategy(symbol, token_data)
                        analytics['strategies'][strategy.name] += 1
                        
                        # Calculate scores
                        scores = {
                            'market': self.calculate_market_score(token_data.get('market_data')),
                            'social': self.calculate_social_score(token_data.get('social_metrics')),
                            'dex': self.calculate_dex_score(token_data.get('dex_data')),
                            'historical': self.calculate_historical_score(token_data.get('historical_patterns')),
                            'github': self.calculate_github_score(token_data.get('github_data')),
                            'trends': self.calculate_trends_score(token_data.get('trends_data')),
                            'orderbook': self.calculate_orderbook_score(token_data.get('orderbook_data'))
                        }
                        
                        # Update component scores
                        for component, score in scores.items():
                            if score is not None:
                                analytics['component_scores'][component].append(score)
                        
                        # Track parameter adjustments
                        base_params = strategy.value
                        if params['take_profits'] != base_params['take_profits']:
                            if params['take_profits'][0] > base_params['take_profits'][0]:
                                analytics['parameter_adjustments']['increased_tp'] += 1
                            else:
                                analytics['parameter_adjustments']['decreased_tp'] += 1
                        
                        if params['stop_loss'] != base_params['stop_loss']:
                            if abs(params['stop_loss']) < abs(base_params['stop_loss']):
                                analytics['parameter_adjustments']['tightened_sl'] += 1
                            else:
                                analytics['parameter_adjustments']['widened_sl'] += 1
                        
                        if params['leverage'] != base_params['leverage']:
                            if params['leverage'] > base_params['leverage']:
                                analytics['parameter_adjustments']['increased_leverage'] += 1
                            else:
                                analytics['parameter_adjustments']['decreased_leverage'] += 1
                        
                        if params.get('recovery_mode'):
                            analytics['parameter_adjustments']['recovery_mode'] += 1
                        
                        # Print token analysis
                        print("📊 Data Sources:", end=" ")
                        print("Market" + ("✓" if token_data['market_data'] else "✗"), end="  ")
                        print("Social" + ("✓" if token_data['social_metrics'] else "✗"), end="  ")
                        print("DEX" + ("✓" if token_data['dex_data'] else "✗"))
                        
                        if token_data['market_data']:
                            cap = token_data['market_data'].market_cap
                            vol = token_data['market_data'].volume_24h
                            if cap and vol:
                                print(f"💰 Cap: ${cap/1e6:.1f}M | Vol: ${vol/1e6:.1f}M")
                        
                        # Print scores with compact bars
                        valid_scores = {k: v for k, v in scores.items() if v is not None}
                        if valid_scores:
                            print("\n📈 Component Scores:")
                            for component, score in valid_scores.items():
                                filled = "" * int(score/10)
                                empty = "░" * (10 - int(score/10))
                                print(f"{component:8} [{filled}{empty}] {int(score)}")
                        
                        # Print strategy details
                        risk_level = "High" if strategy == TradingStrategy.AGGRESSIVE_PUMP else "Medium" if strategy == TradingStrategy.BALANCED_PUMP else "Low"
                        analytics['risk_levels'][risk_level] += 1
                        
                        print(f"\n🎯 {strategy.value['name']} ({risk_level} Risk)")
                        print(f"⚙️  Hold: {params['hold_time']} | Leverage: {params['leverage']}x")
                        print(f"   TP: {', '.join(f'{tp}%' for tp in params['take_profits'])} | SL: {params['stop_loss']}%")
                        if params.get('recovery_mode'):
                            print("   ✨ Recovery Mode Enabled")
            
            # Print summary if tokens were processed
            if processed_symbols:
                self._print_analysis_summary(analytics)
            else:
                print("\n❌ No new listings found in the past 30 days")
                
        except Exception as e:
            print(f"\n⚠️ Error during analysis: {str(e)}")
        
        print("\n" + "=" * 40)

    def _print_analysis_summary(self, analytics):
        """Print analysis summary with clean formatting"""
        print("\n📊 SUMMARY")
        print("-" * 50)
        
        total = analytics['total_tokens']
        print(f"Total Tokens: {total}")
        print(f"With Data: {analytics['tokens_with_data']} | No Data: {analytics['tokens_without_data']}")
        
        print("\n📱 Data Sources:")
        for source, count in analytics['data_sources'].items():
            if count > 0:
                pct = (count / total) * 100
                print(f"{source.capitalize():12} {count:2} ({pct:4.1f}%)")
        
        print("\n📈 Strategy Distribution:")
        for strategy, count in analytics['strategies'].items():
            if count > 0:
                pct = (count / total) * 100
                strategy_name = strategy.replace('_', ' ').title()
                print(f"{strategy_name:15} {count:2} ({pct:4.1f}%)")
        
        print("\n⚠️  Risk Levels:")
        for risk, count in analytics['risk_levels'].items():
            if count > 0:
                pct = (count / total) * 100
                print(f"{risk:8} {count:2} ({pct:4.1f}%)")
        
        if analytics.get('market_caps') and analytics.get('volumes'):
            avg_cap = sum(analytics['market_caps']) / len(analytics['market_caps'])
            avg_vol = sum(analytics['volumes']) / len(analytics['volumes'])
            print(f"\n💰 Market Averages:")
            print(f"Cap: ${avg_cap:,.0f}")
            print(f"Vol: ${avg_vol:,.0f}")
        
        print(f"\n⏰ Analysis Period:")
        if self.listing_history:
            start_date = min(self.listing_history.values()).strftime('%Y-%m-%d')
            end_date = max(self.listing_history.values()).strftime('%Y-%m-%d')
            print(f"{start_date} to {end_date}")
        print("-" * 50)

    def monitor_new_listings(self):
        """Monitor for new listings with improved analysis"""
        print("\n🔍 Monitoring for new listings...")
        print("Press Ctrl+C to stop monitoring\n")
        
        # Initialize with current announcements
        initial_announcements = self.get_announcements()
        known_announcements = set()
        if initial_announcements and 'result' in initial_announcements and 'list' in initial_announcements['result']:
            for announcement in initial_announcements['result']['list']:
                known_announcements.add(announcement.get('id', ''))
        
        print("Initialized and ready to detect new listings...")
        print("Waiting for new announcements...\n")
        
        while True:
            try:
                announcements = self.get_announcements()
                if announcements and 'result' in announcements and 'list' in announcements['result']:
                    for announcement in announcements['result']['list']:
                        announcement_id = announcement.get('id', '')
                        if announcement_id in known_announcements:
                            continue
                            
                        title = announcement.get('title', '')
                        if ('LISTING' in title.upper() or 'WILL LIST' in title.upper()) and 'USDT' in title.upper():
                            symbol = self.extract_symbol(title)
                            if symbol:
                                print(f"\n{'='*40}")
                                print(f"🚨 NEW LISTING ALERT: {symbol}")
                                print(f"{'='*40}")
                                
                                # Enhanced analysis
                                market_data = self.get_coingecko_data(symbol)
                                if market_data:
                                    initial_market_data = self.simulate_initial_conditions(market_data)
                                    strategy = TradingStrategy.analyze_initial_listing_strategy(symbol, initial_market_data)
                                    params = strategy.get_strategy_params()
                                    
                                    print(f"\n📊 Market Analysis:")
                                    print(f"Est. Initial Market Cap: ${initial_market_data.market_cap:,.0f}")
                                    print(f"Est. Initial Volume: ${initial_market_data.volume_24h:,.0f}")
                                    
                                    print(f"\n📈 Trading Strategy: {strategy.value['name']}")
                                    print(f"Timeframe: {params['hold_time']}")
                                    print(f"Leverage: {params['leverage']}x")
                                    print(f"Take Profits: {', '.join(f'{tp}%' for tp in params['take_profits'])}")
                                    print(f"Stop Loss: {params['stop_loss']}%")
                                    
                                    if params.get('recovery_mode'):
                                        print("✨ Recovery Mode Enabled")
                                    
                                    risk_level = "High" if strategy == TradingStrategy.AGGRESSIVE_PUMP else "Medium" if strategy == TradingStrategy.BALANCED_PUMP else "Low"
                                    print(f"Risk Level: {risk_level}")
                                    
                                known_announcements.add(announcement_id)
                
                time.sleep(1)
                
            except KeyboardInterrupt:
                print("\n\n🛑 Monitoring stopped")
                break
            except Exception as e:
                print(f"Error in monitoring: {e}")
                time.sleep(1)

    def simulate_initial_conditions(self, market_data: MarketData) -> MarketData:
        """Simulate initial listing conditions with improved estimates"""
        initial_data = MarketData()
        initial_data.price = market_data.price
        initial_data.market_cap = market_data.market_cap * 0.15  # More conservative estimate
        initial_data.volume_24h = market_data.volume_24h * 0.08  # More conservative volume
        initial_data.exchanges_listed = 1
        initial_data.price_change_24h = 0
        return initial_data

    def pre_listing_analysis(self, symbol: str) -> Dict:
        # Анализируем данные за 24 часа до листинга
        pre_listing_data = self.social_analyzer.analyze_listing_social_data(
            symbol,
            listing_time=datetime.now() - timedelta(hours=24)
        )
        
        strategy = TradingStrategy.MOMENTUM  # дефолтная стратегия
        
        if pre_listing_data['community_strength'] > 70:
            strategy = TradingStrategy.AGGRESSIVE_PUMP
        elif pre_listing_data['hype_score'] > 50:
            strategy = TradingStrategy.BALANCED_PUMP

    def get_comprehensive_token_data(self, symbol: str, listing_time: datetime) -> Dict:
        """Gather comprehensive token data from all available sources"""
        data = {
            'market_data': None,
            'social_metrics': None,
            'dex_data': None,
            'historical_patterns': None,
            'github_data': None,
            'trends_data': None,
            'orderbook_data': None
        }
        
        # 1. Market Data (CoinGecko/CMC)
        market_data = self.get_coingecko_data(symbol)
        if not market_data:
            market_data = self.get_coinmarketcap_data(symbol)
        data['market_data'] = market_data
        
        # 2. Social Media Metrics
        try:
            social_metrics = self.social_analyzer.analyze_listing_social_data(symbol, listing_time)
            data['social_metrics'] = social_metrics
        except Exception:
            pass
        
        # 3. DEX Data
        try:
            dex_data = self.dex_screener.get_token_data(symbol)
            data['dex_data'] = dex_data
        except Exception:
            pass
        
        # 4. Historical Patterns
        try:
            historical_patterns = self.historical_analyzer.get_patterns(symbol)
            data['historical_patterns'] = historical_patterns
        except Exception:
            pass
        
        # 5. GitHub Activity
        try:
            github_data = self.data_collector.get_github_activity(symbol)
            data['github_data'] = github_data
        except Exception:
            pass
        
        # 6. Google Trends
        try:
            trends_data = self.data_collector.get_google_trends(symbol)
            data['trends_data'] = trends_data
        except Exception:
            pass
        
        # 7. Order Book Analysis
        try:
            orderbook = self.get_order_book(symbol)
            orderbook_analysis = self.orderbook_analyzer.analyze_orderbook(orderbook)
            data['orderbook_data'] = orderbook_analysis
        except Exception:
            pass
        
        return data

    def analyze_comprehensive_strategy(self, symbol: str, token_data: Dict) -> Tuple[TradingStrategy, Dict]:
        """Analyze all available data to determine the best trading strategy"""
        try:
            self.current_symbol = symbol
            
            # Initialize scores
            scores = {
                'market': 50,  # Default moderate scores
                'social': 50,
                'dex': 50,
                'historical': 50,
                'github': 50,
                'trends': 50,
                'orderbook': 50
            }
            
            # Update scores where data is available
            if token_data.get('market_data'):
                scores['market'] = self.calculate_market_score(token_data['market_data']) or 50
                
            if token_data.get('social_metrics'):
                scores['social'] = self.calculate_social_score(token_data['social_metrics']) or 50
                
            if token_data.get('dex_data'):
                scores['dex'] = self.calculate_dex_score(token_data['dex_data']) or 50
                
            if token_data.get('historical_patterns'):
                scores['historical'] = self.calculate_historical_score(token_data['historical_patterns']) or 50
                
            if token_data.get('github_data'):
                scores['github'] = self.calculate_github_score(token_data['github_data']) or 50
                
            if token_data.get('trends_data'):
                scores['trends'] = self.calculate_trends_score(token_data['trends_data']) or 50
                
            if token_data.get('orderbook_data'):
                scores['orderbook'] = self.calculate_orderbook_score(token_data['orderbook_data']) or 50

            # Calculate total score
            total_score = sum(scores.values()) / len(scores)
            
            # Get volatility and hype with default values
            volatility = self.get_volatility_indicator(token_data) or 40
            hype = self.get_hype_indicator(token_data) or 30
            
            # Select strategy
            strategy = self.select_strategy(total_score, volatility, hype)
            
            # Adjust parameters
            params = self.adjust_strategy_parameters(strategy, token_data, scores)
            
            return strategy, params
            
        except Exception as e:
            print(f"Error in comprehensive analysis: {str(e)}")
            # Default to Balanced Pump on error with base parameters
            return TradingStrategy.BALANCED_PUMP, TradingStrategy.BALANCED_PUMP.value

    def calculate_market_score(self, market_data: Optional[MarketData]) -> Optional[float]:
        """Calculate market metrics score"""
        if not market_data:
            return None
            
        try:
            market_cap_score = min(market_data.market_cap / 1_000_000, 100)
            volume_score = min(market_data.volume_24h / 100_000, 100)
            volatility_score = min(abs(market_data.price_change_24h), 100)
            exchange_score = min(market_data.exchanges_listed / 5, 20)
            
            return (
                market_cap_score * 0.4 +
                volume_score * 0.3 +
                volatility_score * 0.2 +
                exchange_score * 0.1
            )
        except:
            return None

    def calculate_social_score(self, social_metrics: Optional[Dict]) -> Optional[float]:
        """Calculate social metrics score"""
        if not social_metrics:
            return None
            
        try:
            return (
                social_metrics.get('hype_score', 0) * 0.3 +
                social_metrics.get('sentiment', 0) * 0.3 +
                social_metrics.get('community_strength', 0) * 0.2 +
                social_metrics.get('growth_rate', 0) * 0.2
            )
        except:
            return None

    def calculate_dex_score(self, dex_data: Optional[Dict]) -> Optional[float]:
        """Calculate DEX metrics score"""
        if not dex_data:
            return None
            
        try:
            liquidity_score = min(dex_data.get('liquidity', 0) / 100_000, 100)
            holders_score = min(dex_data.get('holders', 0) / 1000, 100)
            price_impact = min(abs(dex_data.get('priceChange24h', 0)), 100)
            
            return (
                liquidity_score * 0.4 +
                holders_score * 0.3 +
                price_impact * 0.3
            )
        except:
            return None

    def calculate_historical_score(self, historical_patterns: Optional[Dict]) -> Optional[float]:
        """Calculate historical patterns score"""
        if not historical_patterns:
            return None
            
        try:
            return (
                historical_patterns.get('success_rate', 0) * 0.4 +
                historical_patterns.get('avg_roi_score', 0) * 0.3 +
                historical_patterns.get('stability_score', 0) * 0.3
            )
        except:
            return None

    def calculate_github_score(self, github_data: Optional[Dict]) -> Optional[float]:
        """Calculate GitHub activity score"""
        if not github_data:
            return None
            
        try:
            commits_score = min(github_data.get('commits_per_week', 0) / 50, 100)
            contributors_score = min(github_data.get('active_contributors', 0) / 20, 100)
            
            return (commits_score * 0.6 + contributors_score * 0.4)
        except:
            return None

    def calculate_trends_score(self, trends_data: Optional[Dict]) -> Optional[float]:
        """Calculate Google Trends score"""
        if not trends_data:
            return None
            
        try:
            return min(trends_data.get('interest_over_time', 0), 100)
        except:
            return None

    def calculate_orderbook_score(self, orderbook_data: Optional[Dict]) -> Optional[float]:
        """Calculate order book analysis score"""
        if not orderbook_data:
            return None
            
        try:
            return (
                orderbook_data.get('depth_score', 0) * 0.4 +
                orderbook_data.get('buy_pressure', 0) * 0.4 +
                (100 - orderbook_data.get('volatility_risk', 0)) * 0.2
            )
        except:
            return None

    def get_volatility_indicator(self, token_data: Dict) -> float:
        """Calculate volatility indicator from multiple sources"""
        indicators = []
        
        if token_data.get('market_data'):
            price_change = abs(token_data['market_data'].price_change_24h)
            if price_change is not None:
                indicators.append(price_change)
            
        if token_data.get('orderbook_data'):
            vol_risk = token_data['orderbook_data'].get('volatility_risk')
            if vol_risk is not None:
                indicators.append(vol_risk)
            
        if token_data.get('dex_data'):
            price_change = abs(token_data['dex_data'].get('priceChange24h', 0))
            if price_change is not None:
                indicators.append(price_change)
        
        # If no indicators available, use moderate volatility
        return statistics.mean(indicators) if indicators else 40

    def get_hype_indicator(self, token_data: Dict) -> float:
        """Calculate hype indicator from multiple sources"""
        indicators = []
        
        if token_data.get('social_metrics'):
            hype_score = token_data['social_metrics'].get('hype_score')
            if hype_score is not None:
                indicators.append(hype_score)
            
        if token_data.get('trends_data'):
            interest = token_data['trends_data'].get('interest_over_time')
            if interest is not None:
                indicators.append(interest)
        
        # Check token name for hype indicators
        meme_indicators = ['PEPE', 'MEME', 'DOGE', 'SHIB', 'BABY', 'ELON', 'MOON', 'SAFE', 'INU', 'APE']
        if any(indicator in self.current_symbol.upper() for indicator in meme_indicators):
            indicators.append(80)  # High hype score for meme tokens
        
        # If no indicators available, use moderate hype
        return statistics.mean(indicators) if indicators else 30

    def select_strategy(self, total_score: float, volatility: float, hype: float) -> TradingStrategy:
        """Select strategy based on comprehensive weighted analysis"""
        try:
            # Set default values if missing
            total_score = 50 if total_score is None else total_score
            volatility = 40 if volatility is None else volatility
            hype = 30 if hype is None else hype

            # Check for meme/hype indicators in symbol name
            meme_indicators = ['PEPE', 'MEME', 'DOGE', 'SHIB', 'BABY', 'ELON', 'MOON', 'SAFE', 'INU', 'APE']
            is_meme = any(indicator in self.current_symbol.upper() for indicator in meme_indicators)

            # Direct conditions for Aggressive Pump
            if is_meme or volatility >= 70 or hype >= 80:
                return TradingStrategy.AGGRESSIVE_PUMP

            # Calculate weighted score
            weighted_score = (
                total_score * 0.4 +
                volatility * 0.3 +
                hype * 0.3
            )

            # Strategy selection based on weighted score
            if weighted_score >= 70:
                return TradingStrategy.AGGRESSIVE_PUMP
            elif weighted_score >= 45:
                return TradingStrategy.BALANCED_PUMP
            else:
                return TradingStrategy.MOMENTUM

        except Exception as e:
            print(f"⚠️ Strategy selection error: {str(e)}")
            # Even on error, try to make an educated guess based on symbol
            if any(indicator in self.current_symbol.upper() for indicator in meme_indicators):
                return TradingStrategy.AGGRESSIVE_PUMP
            return TradingStrategy.BALANCED_PUMP  # Default to balanced instead of momentum

    def adjust_strategy_parameters(self, strategy: TradingStrategy, token_data: Dict, scores: Dict) -> Dict:
        """Adjust strategy parameters based on all available metrics"""
        params = strategy.value.copy()
        
        # Adjust take profits based on volatility and hype
        volatility = self.get_volatility_indicator(token_data)
        hype = self.get_hype_indicator(token_data)
        
        if hype > 80:
            params['take_profits'] = [x * 1.2 for x in params['take_profits']]
        elif hype < 30:
            params['take_profits'] = [x * 0.8 for x in params['take_profits']]
            
        # Adjust stop loss based on volatility - more conservative adjustments
        if volatility > 60:
            params['stop_loss'] *= 0.9  # Tighter stop loss for high volatility (was 0.8)
        elif volatility < 30:
            params['stop_loss'] *= 1.1  # Wider stop loss for low volatility (was 1.2)
            
        # Ensure stop loss doesn't exceed maximum values
        max_stop_loss = {
            TradingStrategy.AGGRESSIVE_PUMP: -10,
            TradingStrategy.BALANCED_PUMP: -12,
            TradingStrategy.MOMENTUM: -15
        }
        
        params['stop_loss'] = max(params['stop_loss'], max_stop_loss[strategy])
        
        # Adjust leverage based on risk metrics
        risk_score = (
            (scores.get('market', 50) * 0.4) +
            (scores.get('social', 50) * 0.3) +
            (scores.get('dex', 50) * 0.3)
        )
        
        if risk_score < 40:
            params['leverage'] = max(1, params['leverage'] - 1)
        elif risk_score > 70:
            params['leverage'] = min(5, params['leverage'] + 1)
            
        # Add recovery mode for certain conditions
        if scores.get('orderbook', 0) > 80 and scores.get('market', 0) > 70:
            params['recovery_mode'] = True
            
        return params

if __name__ == "__main__":
    monitor = BybitMonitor()
    
    if len(sys.argv) > 1 and sys.argv[1] == "history":
        monitor.analyze_last_listings()
    else:
        monitor.monitor_new_listings() 
        