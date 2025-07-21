#!/usr/bin/env python3
"""
Solana RPC Helper - Direct HTTP requests to bypass package issues
Uses working endpoint: https://mainnet.helius-rpc.com/?api-key=71a66bb2-11d1-4ed7-9434-f98eef46f5f2
"""

import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

class SolanaRPC:
    def __init__(self):
        # Use the working endpoint we found
        helius_api_key = os.getenv('HELIUS_API_KEY')
        if helius_api_key:
            self.endpoint = f"https://mainnet.helius-rpc.com/?api-key={helius_api_key}"
        else:
            self.endpoint = "https://mainnet.helius-rpc.com/?api-key=71a66bb2-11d1-4ed7-9434-f98eef46f5f2"
    
    def get_current_epoch(self):
        """Get current epoch information"""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getEpochInfo"
            }
            
            response = requests.post(
                self.endpoint,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'result' in result:
                    return result['result'].get('epoch')
            
            return None
            
        except Exception as e:
            print(f"Error getting epoch: {e}")
            return None
    
    def get_epoch_info(self):
        """Get detailed epoch information"""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getEpochInfo"
            }
            
            response = requests.post(
                self.endpoint,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'result' in result:
                    return result['result']
            
            return None
            
        except Exception as e:
            print(f"Error getting epoch info: {e}")
            return None

# Global instance
solana_rpc = SolanaRPC()

def get_current_epoch():
    """Simple function to get current epoch - replaces the old one"""
    epoch = solana_rpc.get_current_epoch()
    return epoch if epoch is not None else 654  # fallback to mock if failed

# Test the connection
if __name__ == "__main__":
    print("🧪 Testing Solana RPC Helper...")
    
    epoch = get_current_epoch()
    print(f"Current epoch: {epoch}")
    
    epoch_info = solana_rpc.get_epoch_info()
    if epoch_info:
        print(f"Detailed info: {json.dumps(epoch_info, indent=2)}")
    else:
        print("Failed to get detailed epoch info")
