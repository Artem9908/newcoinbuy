from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from typing import Dict, Optional

Base = declarative_base()

class ListingData(Base):
    __tablename__ = 'listing_data'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Рыночные данные
    market_cap = Column(Float)
    volume_24h = Column(Float)
    price = Column(Float)
    price_change_24h = Column(Float)
    
    # Данные поставок
    total_supply = Column(Float)
    circulating_supply = Column(Float)
    max_supply = Column(Float)
    
    # Социальные метрики
    social_score = Column(Float)
    sentiment_score = Column(Float)
    community_strength = Column(Float)
    growth_rate = Column(Float)
    
    # Данные ордербука
    spread = Column(Float)
    depth_score = Column(Float)
    buy_pressure = Column(Float)
    volatility_risk = Column(Float)
    
    # Дополнительные метрики
    exchange_count = Column(Integer)
    success_probability = Column(Float)
    
    # JSON поля для хранения детальных данных
    orderbook_analysis = Column(JSON)
    social_metrics = Column(JSON)
    trading_metrics = Column(JSON)

class Database:
    def __init__(self):
        self.engine = create_engine('sqlite:///listings.db')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        
    def insert_listing_data(self, symbol: str, metrics: Dict):
        session = self.Session()
        try:
            data = ListingData(
                symbol=symbol,
                **metrics
            )
            session.add(data)
            session.commit()
        finally:
            session.close()
            
    def get_historical_data(self, symbol: str) -> Optional[Dict]:
        """Получение исторических данных по символу"""
        session = self.Session()
        try:
            data = session.query(ListingData).filter(
                ListingData.symbol == symbol
            ).order_by(ListingData.timestamp.desc()).first()
            
            if data:
                return {
                    'market_cap': data.market_cap,
                    'volume_24h': data.volume_24h,
                    'social_score': data.social_score,
                    'sentiment_score': data.sentiment_score,
                    'success_probability': data.success_probability,
                    'orderbook_analysis': data.orderbook_analysis,
                    'social_metrics': data.social_metrics,
                    'trading_metrics': data.trading_metrics
                }
            return None
        finally:
            session.close() 