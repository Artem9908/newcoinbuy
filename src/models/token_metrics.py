from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime

@dataclass
class TokenMetrics:
    symbol: str
    timestamp: datetime
    
    # Рыночные данные
    market_cap: float = 0.0
    volume_24h: float = 0.0
    price: float = 0.0
    price_change_24h: float = 0.0
    
    # Данные поставок
    total_supply: float = 0.0
    circulating_supply: float = 0.0
    max_supply: Optional[float] = None
    
    # Социальные метрики
    social_score: float = 0.0
    sentiment_score: float = 0.0
    community_strength: float = 0.0
    growth_rate: float = 0.0
    
    # Данные ордербука
    spread: float = 0.0
    depth_score: float = 0.0
    buy_pressure: float = 0.0
    volatility_risk: float = 0.0
    
    # Дополнительные метрики
    exchange_count: int = 0
    success_probability: float = 0.0
    
    # JSON поля для хранения детальных данных
    orderbook_analysis: Dict = None
    social_metrics: Dict = None 