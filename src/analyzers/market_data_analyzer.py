from typing import Dict, Optional
from datetime import datetime
from models.token_metrics import TokenMetrics

class MarketDataAnalyzer:
    def __init__(self):
        self.min_market_cap = 1_000_000  # Минимальная капитализация в USD
        self.min_volume = 100_000        # Минимальный объем в USD
        
    def analyze_market_data(self, market_data: Dict) -> TokenMetrics:
        metrics = TokenMetrics(
            symbol=market_data['symbol'],
            timestamp=datetime.now(),
            market_cap=market_data.get('market_cap', 0),
            volume_24h=market_data.get('volume_24h', 0),
            price=market_data.get('price', 0),
            price_change_24h=market_data.get('price_change_24h', 0)
        )
        
        metrics.volatility_score = self._calculate_volatility_score(market_data)
        metrics.liquidity_score = self._calculate_liquidity_score(market_data)
        metrics.market_strength = self._calculate_market_strength(market_data)
        
        return metrics
        
    def _calculate_volatility_score(self, data: Dict) -> float:
        price_change = abs(data.get('price_change_24h', 0))
        return min(price_change / 10, 100)  # Нормализуем до 100
        
    def _calculate_liquidity_score(self, data: Dict) -> float:
        volume = data.get('volume_24h', 0)
        return min(volume / self.min_volume * 100, 100)
        
    def _calculate_market_strength(self, data: Dict) -> float:
        market_cap = data.get('market_cap', 0)
        volume = data.get('volume_24h', 0)
        
        if market_cap == 0:
            return 0
            
        volume_to_cap_ratio = (volume / market_cap) * 100
        return min(volume_to_cap_ratio * 10, 100) 