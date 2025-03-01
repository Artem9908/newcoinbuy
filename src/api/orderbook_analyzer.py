from typing import Dict, Optional
import numpy as np

class OrderBookAnalyzer:
    def __init__(self):
        self.depth_levels = 20  # Глубина анализа стакана
        
    def analyze_orderbook(self, order_book: Dict) -> Dict[str, float]:
        """Полный анализ ордербука"""
        if not order_book or 'result' not in order_book:
            return self._empty_analysis()
            
        bids = order_book['result'].get('b', [])
        asks = order_book['result'].get('a', [])
        
        if not bids or not asks:
            return self._empty_analysis()
            
        analysis = {
            'spread': self._calculate_spread(bids[0], asks[0]),
            'bid_wall': self._find_walls(bids),
            'ask_wall': self._find_walls(asks),
            'depth_score': self._calculate_depth(bids, asks),
            'buy_pressure': self._calculate_pressure(bids, asks),
            'volatility_risk': self._estimate_volatility(bids, asks),
            'dump_probability': self._calculate_dump_probability(bids, asks),
            'sell_wall_pressure': self._calculate_sell_wall_pressure(asks),
            'bid_support_strength': self._calculate_bid_support_strength(bids)
        }
        
        return analysis
        
    def _calculate_spread(self, best_bid: list, best_ask: list) -> float:
        """Расчет спреда между лучшими ценами"""
        bid_price = float(best_bid[0])
        ask_price = float(best_ask[0])
        return ((ask_price - bid_price) / bid_price) * 100
        
    def _find_walls(self, orders: list) -> float:
        """Поиск крупных ордеров (стен)"""
        volumes = [float(order[1]) for order in orders[:self.depth_levels]]
        mean_volume = np.mean(volumes)
        walls = sum(1 for vol in volumes if vol > mean_volume * 3)
        return walls
        
    def _calculate_depth(self, bids: list, asks: list) -> float:
        """Оценка глубины стакана"""
        bid_depth = sum(float(bid[1]) for bid in bids[:self.depth_levels])
        ask_depth = sum(float(ask[1]) for ask in asks[:self.depth_levels])
        return (bid_depth + ask_depth) / 2
        
    def _calculate_pressure(self, bids: list, asks: list) -> float:
        """Оценка давления покупателей/продавцов"""
        bid_pressure = sum(float(bid[1]) for bid in bids[:5])
        ask_pressure = sum(float(ask[1]) for ask in asks[:5])
        return (bid_pressure - ask_pressure) / (bid_pressure + ask_pressure)
        
    def _estimate_volatility(self, bids: list, asks: list) -> float:
        """Оценка потенциальной волатильности"""
        bid_prices = [float(bid[0]) for bid in bids[:self.depth_levels]]
        ask_prices = [float(ask[0]) for ask in asks[:self.depth_levels]]
        price_range = (max(ask_prices) - min(bid_prices)) / float(bids[0][0])
        return price_range * 100
        
    def _calculate_dump_probability(self, bids: list, asks: list) -> float:
        """Расчет вероятности дампа на основе анализа ордербука
        
        Факторы:
        1. Соотношение объемов продаж к покупкам (sell/buy ratio)
        2. Наличие крупных стен на продажу
        3. Слабая поддержка покупателей
        4. Высокий спред
        """
        # Анализ объемов верхних 10 ордеров
        bid_volume = sum(float(bid[1]) for bid in bids[:10])
        ask_volume = sum(float(ask[1]) for ask in asks[:10])
        volume_ratio = ask_volume / (bid_volume + 0.0001)  # Избегаем деления на 0
        
        # Анализ стен
        ask_walls = self._find_walls(asks[:10])
        bid_walls = self._find_walls(bids[:10])
        wall_factor = ask_walls / (bid_walls + 1)  # Больше стен на продажу - выше вероятность дампа
        
        # Спред
        spread = self._calculate_spread(bids[0], asks[0])
        spread_factor = min(spread / 2, 1)  # Нормализуем до 1
        
        # Расчет итоговой вероятности
        dump_probability = (
            0.4 * min(volume_ratio, 2) +  # 40% вес для объемов
            0.3 * min(wall_factor, 2) +   # 30% вес для стен
            0.3 * spread_factor            # 30% вес для спреда
        ) * 100
        
        return min(dump_probability, 100)  # Нормализуем до 100%
        
    def _calculate_sell_wall_pressure(self, asks: list) -> float:
        """Расчет давления продаж от крупных стен"""
        volumes = [float(ask[1]) for ask in asks[:10]]
        mean_volume = np.mean(volumes)
        pressure = sum(vol / mean_volume for vol in volumes if vol > mean_volume * 2)
        return min(pressure * 10, 100)  # Нормализуем до 100
        
    def _calculate_bid_support_strength(self, bids: list) -> float:
        """Оценка силы поддержки от покупателей"""
        volumes = [float(bid[1]) for bid in bids[:10]]
        mean_volume = np.mean(volumes)
        support = sum(vol / mean_volume for vol in volumes if vol > mean_volume)
        return min(support * 10, 100)  # Нормализуем до 100
        
    def _empty_analysis(self) -> Dict[str, float]:
        """Пустой анализ при отсутствии данных"""
        return {
            'spread': 0,
            'bid_wall': 0,
            'ask_wall': 0,
            'depth_score': 0,
            'buy_pressure': 0,
            'volatility_risk': 0,
            'dump_probability': 100,  # Максимальный риск при отсутствии данных
            'sell_wall_pressure': 0,
            'bid_support_strength': 0
        } 