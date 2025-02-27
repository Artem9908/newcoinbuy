import requests
from typing import Dict, Optional
from datetime import datetime, timedelta
from pytrends.request import TrendReq

class EnhancedDataCollector:
    def __init__(self, github_token: str, google_api_key: str):
        self.github_token = github_token
        self.google_api_key = google_api_key
        self.github_headers = {
            'Authorization': f'token {self.github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        self.pytrends = TrendReq(hl='en-US', tz=360)

    def get_github_activity(self, symbol: str) -> Optional[Dict]:
        """Get GitHub activity metrics for a token project"""
        try:
            # Remove USDT suffix and convert to lowercase for searching
            project_name = symbol.replace('USDT', '').lower()
            
            # Search for repositories
            search_url = f'https://api.github.com/search/repositories?q={project_name}+in:name'
            response = requests.get(search_url, headers=self.github_headers)
            
            if response.status_code != 200:
                print(f"GitHub API error: {response.status_code}")
                return None
                
            repos = response.json().get('items', [])
            if not repos:
                return None
                
            # Get the most relevant repository (usually the first one)
            repo = repos[0]
            repo_full_name = repo['full_name']
            
            # Get commit activity
            commits_url = f'https://api.github.com/repos/{repo_full_name}/stats/commit_activity'
            commits_response = requests.get(commits_url, headers=self.github_headers)
            
            if commits_response.status_code != 200:
                return None
                
            commit_data = commits_response.json()
            
            # Calculate weekly commit average
            total_commits = sum(week.get('total', 0) for week in commit_data[-4:])  # Last 4 weeks
            commits_per_week = total_commits / 4
            
            # Get contributors
            contributors_url = f'https://api.github.com/repos/{repo_full_name}/contributors'
            contributors_response = requests.get(contributors_url, headers=self.github_headers)
            
            if contributors_response.status_code != 200:
                return None
                
            active_contributors = len(contributors_response.json())
            
            return {
                'commits_per_week': commits_per_week,
                'active_contributors': active_contributors,
                'repo_url': repo['html_url'],
                'stars': repo['stargazers_count'],
                'forks': repo['forks_count']
            }
            
        except Exception as e:
            print(f"Error fetching GitHub data: {str(e)}")
            return None

    def get_google_trends(self, symbol: str) -> Optional[Dict]:
        """Get Google Trends data for a token"""
        try:
            # Remove USDT suffix for searching
            search_term = symbol.replace('USDT', '')
            
            # Build payload
            self.pytrends.build_payload([search_term], timeframe='today 3-m')
            
            # Get interest over time
            interest_data = self.pytrends.interest_over_time()
            
            if interest_data.empty:
                return None
                
            # Calculate average interest for last 7 days
            recent_interest = interest_data[search_term].tail(7).mean()
            
            # Get related queries
            related_queries = self.pytrends.related_queries()
            rising_queries = related_queries.get(search_term, {}).get('rising', [])
            
            return {
                'interest_over_time': recent_interest,
                'rising_queries': rising_queries[:5] if isinstance(rising_queries, list) else [],
                'data_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Error fetching Google Trends data: {str(e)}")
            return None 