from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

@dataclass
class HistoricalPatterns:
    symbol: str
    timestamp: datetime
    
    # Показатели успешности
    success_rate: float = 0.0
    avg_roi_score: float = 0.0
    stability_score: float = 0.0
    
    # Исторические данные
    price_history: List[float] = None
    volume_history: List[float] = None
    volatility_history: List[float] = None
    
    # Паттерны
    support_levels: List[float] = None
    resistance_levels: List[float] = None
    trend_strength: float = 0.0
    
    # Дополнительные метрики
    mean_reversion_score: float = 0.0
    momentum_score: float = 0.0 