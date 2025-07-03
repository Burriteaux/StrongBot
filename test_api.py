from firecrawl import FirecrawlApp
from pydantic import BaseModel, Field
from typing import Any, Optional, List
import json

API_KEY = 'fc-2b484abcba804a98a794a4d4af09c790'
app = FirecrawlApp(api_key=API_KEY)

class ExtractSchema(BaseModel):
    sol_price: float = Field(alias="sol_price ($)")
    stake: float
    leader_rewards: float
    commission: float
    voting_fee: float
    current_stats_val: float
    current_identity_balance: float
    vote_balance: float
    volume_24h: float = Field(alias="StrongSOL 24hr Volume ($)")
    holders: float = Field(alias="StrongSOL Holders")

def test_data_extraction():
    print("\nTesting Data Extraction:")
    
    # V1 Extract API - Updated syntax
    response = app.extract(
        urls=[
            "https://svt.one/dashboard/Ac1beBKixfNdrTAac7GRaTsJTxLyvgGvJjvy4qQfvyfc",
            "https://birdeye.so/token/strng7mqqc1MBJJV6vMzYbEqnwVGvKKGKedeCvtktWA?chain=solana"
        ],
        prompt='''From SVT.one - Extract the Stake, Commission, Leader Rewards, Voting Fee, SOL Price, Current-stats-val (the current income value next to the income 30 epochs graph), Current Identity Balance, and Vote Balance values.

From Birdeye.so - Extract the 24h Volume, Holders''',
        schema=ExtractSchema.model_json_schema()
    )
    
    print(f"\nResponse Type: {type(response)}")
    print(f"Response Success: {response.success}")
    
    # Handle V1 ExtractResponse object
    if response.success and response.data:
        data = response.data
        print("\nExtracted Data:")
        print(json.dumps(data, indent=2))
        
        # Format in desired structure
        formatted_data = [{
            'validator': {
                'name': 'Stronghold',
                'stake': data.get('stake', 0),
                'status': 'success',
                'rewards': data.get('leader_rewards', 0),
                'sol_price': data.get('sol_price', 0),
                'commission': data.get('commission', 0),
                'voting_fee': data.get('voting_fee', 0),
                'current_stats_val': data.get('current_stats_val', 0),
                'current_identity_balance': data.get('current_identity_balance', 0),
                'vote_balance': data.get('vote_balance', 0)
            },
            'token': {
                'volume_24h': data.get('volume_24h', 0),
                'holders': data.get('holders', 0)
            }
        }]
        
        print("\nFormatted Data:")
        print(json.dumps(formatted_data, indent=2))
    else:
        print(f"Extract failed. Error: {response.error if hasattr(response, 'error') else 'Unknown error'}")
        print(f"Response attributes: {dir(response)}")

if __name__ == "__main__":
    print("Testing FireCrawl API with SDK...")
    test_data_extraction() 