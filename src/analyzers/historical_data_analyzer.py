from typing import Dict, Optional, List
from datetime import datetime, timedelta
from models.historical_patterns import HistoricalPatterns
import numpy as np

class HistoricalDataAnalyzer:
    def __init__(self):
        self.min_data_points = 10
        self.volatility_window = 24  # часов
        
    def analyze_historical_data(self, price_data: List[Dict], volume_data: List[Dict]) -> HistoricalPatterns:
        if not price_data or len(price_data) < self.min_data_points:
            return self._empty_patterns()
            
        patterns = HistoricalPatterns(
            symbol=price_data[0].get('symbol', ''),
            timestamp=datetime.now(),
            price_history=[p['price'] for p in price_data],
            volume_history=[v['volume'] for v in volume_data]
        )
        
        patterns.success_rate = self._calculate_success_rate(price_data)
        patterns.avg_roi_score = self._calculate_avg_roi(price_data)
        patterns.stability_score = self._calculate_stability(price_data)
        patterns.support_levels = self._find_support_levels(price_data)
        patterns.resistance_levels = self._find_resistance_levels(price_data)
        patterns.trend_strength = self._calculate_trend_strength(price_data)
        
        return patterns
        
    def _calculate_success_rate(self, price_data: List[Dict]) -> float:
        """Расчет процента успешных листингов"""
        if len(price_data) < 2:
            return 0
            
        success_count = sum(1 for i in range(len(price_data)-1) 
                          if price_data[i+1]['price'] > price_data[i]['price'])
        return (success_count / (len(price_data)-1)) * 100
        
    def _calculate_avg_roi(self, price_data: List[Dict]) -> float:
        """Расчет среднего ROI"""
        if len(price_data) < 2:
            return 0
            
        rois = [(price_data[i+1]['price'] - price_data[i]['price']) / price_data[i]['price'] 
                for i in range(len(price_data)-1)]
        return np.mean(rois) * 100
        
    def _empty_patterns(self) -> HistoricalPatterns:
        return HistoricalPatterns(
            symbol='',
            timestamp=datetime.now()
        ) 