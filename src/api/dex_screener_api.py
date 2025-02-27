from typing import Dict, Optional
import requests

class DexScreenerAPI:
    def __init__(self):
        self.base_url = "https://api.dexscreener.com/latest"
        
    def get_token_data(self, token_address: str) -> Dict:
        url = f"{self.base_url}/dex/tokens/{token_address}"
        response = requests.get(url)
        return response.json()
        
    def get_pair_data(self, pair_address: str) -> Dict:
        url = f"{self.base_url}/dex/pairs/{pair_address}"
        response = requests.get(url)
        return response.json() 