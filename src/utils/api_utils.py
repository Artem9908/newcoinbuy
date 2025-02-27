import time
from functools import wraps
from typing import Callable, Any, Dict, Optional
from datetime import datetime, timedelta
import requests
from requests.exceptions import RequestException

def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """Декоратор для повторных попыток при ошибках API"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (2 ** attempt)  # Экспоненциальная задержка
                        print(f"Attempt {attempt + 1} failed, retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        
            print(f"All {max_retries} attempts failed: {str(last_exception)}")
            return None
            
        return wrapper
    return decorator

class APICache:
    """Простой кэш для API запросов"""
    def __init__(self, ttl: int = 60):
        self.cache = {}
        self.ttl = ttl
        
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.ttl):
                return value
            del self.cache[key]
        return None
        
    def set(self, key: str, value: Any):
        """Set value in cache with current timestamp"""
        self.cache[key] = (value, datetime.now())
        
    def clear(self):
        """Clear all cached data"""
        self.cache.clear() 