import requests
from typing import Dict, Optional

def fetch_epoch_data(api_key: str, url: str) -> Dict:
    """Fetch epoch data from FireCrawl API"""
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    data = {
        'url': url,
        'extract': {
            'epoch_rewards': 'Extract the epoch leader rewards, commission rewards, and total rewards from this validator dashboard'
        }
    }
    
    try:
        print(f"\nMaking request to FireCrawl API for epoch data:")
        print(f"URL: {url}")
        print(f"Headers: {headers}")
        print(f"Data: {data}")
        
        response = requests.post(
            'https://api.firecrawl.dev/v1/scrape',
            headers=headers,
            json=data
        )
        
        print(f"Response status code: {response.status_code}")
        print(f"Response headers: {response.headers}")
        print(f"Response content: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            return data.get('data', {}).get('json', {})
        else:
            print(f"Error: Non-200 status code: {response.status_code}")
            return {}
            
    except Exception as e:
        print(f"Error making request: {str(e)}")
        return {}

def fetch_token_data(api_key: str, url: str) -> Dict:
    """Fetch token data from FireCrawl API"""
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    data = {
        'url': url,
        'extract': {
            'token_info': 'Extract the 24h volume, number of holders, and liquidity in USD from this token page'
        }
    }
    
    try:
        print(f"\nMaking request to FireCrawl API for token data:")
        print(f"URL: {url}")
        print(f"Headers: {headers}")
        print(f"Data: {data}")
        
        response = requests.post(
            'https://api.firecrawl.dev/v1/scrape',
            headers=headers,
            json=data
        )
        
        print(f"Response status code: {response.status_code}")
        print(f"Response headers: {response.headers}")
        print(f"Response content: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            return data.get('data', {}).get('json', {})
        else:
            print(f"Error: Non-200 status code: {response.status_code}")
            return {}
            
    except Exception as e:
        print(f"Error making request: {str(e)}")
        return {} 