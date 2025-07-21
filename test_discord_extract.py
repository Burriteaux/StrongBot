#!/usr/bin/env python3
"""
Simple test script to verify Firecrawl V1 integration works in discord_bot.py
without needing Discord token setup.
"""
import asyncio
import os
import sys
import aiohttp
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, validator
from firecrawl import FirecrawlApp

# Set basic environment variables for testing
os.environ['FIRECRAWL_API_KEY'] = 'fc-2b484abcba804a98a794a4d4af09c790'
os.environ['HELIUS_API_KEY'] = 'dummy_key_for_testing'  # Just for testing
os.environ['CHECK_INTERVAL'] = '300'

# Schema from discord_bot.py
class ExtractSchema(BaseModel):
    """Schema for the data extraction API response"""
    sol_price: float = Field(default=None, alias="sol_price ($)")
    stake: float = Field(default=None)
    leader_rewards: float = Field(default=None)
    commission: float = Field(default=None)
    voting_fee: float = Field(default=None)
    current_stats_val: float = Field(default=None) # Previous Epoch Total
    volume_24h: float = Field(default=None, alias="StrongSOL 24hr Volume ($)")
    holders: float = Field(default=None, alias="Holders")
    current_supply: float = Field(default=None, alias="Current Supply")
    # last_epoch_apy: Removed - now fetched directly from Sanctum API

    @validator('*', pre=True)
    def empty_str_to_none(cls, v):
        if isinstance(v, str) and v.strip() == '':
            return None
        return v

async def test_firecrawl_v1():
    """Test the Firecrawl V1 extract functionality"""
    print("Testing Firecrawl V1 Extract API...")
    
    app = FirecrawlApp(api_key=os.environ['FIRECRAWL_API_KEY'])
    
    try:
        print("Making Firecrawl API request...")
        firecrawl_response = app.extract(
            urls=[
                "https://svt.one/dashboard/Ac1beBKixfNdrTAac7GRaTsJTxLyvgGvKKGKedeCvtktWA?chain=solana",
                "https://solscan.io/token/strng7mqqc1MBJJV6vMzYbEqnwVGvKKGKedeCvtktWA"
            ],
            prompt='''From SVT.one - Extract the Stake, Commission, Leader Rewards, Voting Fee, SOL Price, and Current-stats-val (the current income value next to the income 30 epochs graph).

From Birdeye.so - Extract the 24h Volume value (e.g., $3.1K or $1.2M).

From Solscan.io - Extract the holders and current supply.''',
            schema=ExtractSchema.model_json_schema()
        )
        
        print(f"Firecrawl API Response Type: {type(firecrawl_response)}")
        print(f"Response Success: {firecrawl_response.success}")
        
        data = {}
        # Updated response handling for V1 Extract API (ExtractResponse object)
        if hasattr(firecrawl_response, 'success') and firecrawl_response.success:
            if hasattr(firecrawl_response, 'data') and firecrawl_response.data:
                data = firecrawl_response.data
                print(f"Successfully extracted data: {data}")
            else:
                print("No data in successful response")
        elif hasattr(firecrawl_response, 'error'):
            print(f"Firecrawl API error: {firecrawl_response.error}")
        else:
            print(f"Unexpected response format. Type: {type(firecrawl_response)}")
        
        if data:
            print("\n--- Extracted Data Summary ---")
            print(f"SOL Price: ${data.get('sol_price ($)', 'N/A')}")
            print(f"Stake: {data.get('stake', 'N/A')} SOL")
            print(f"Leader Rewards: {data.get('leader_rewards', 'N/A')} SOL")
            print(f"Commission: {data.get('commission', 'N/A')} SOL")
            print(f"Volume 24h: {data.get('StrongSOL 24hr Volume ($)', 'N/A')}")
            print(f"Holders: {data.get('Holders', 'N/A')}")
            print("--- End Summary ---")
            
            print("\n✅ Firecrawl V1 integration test PASSED!")
            return True
        else:
            print("\n❌ Firecrawl V1 integration test FAILED - no data extracted")
            return False
            
    except Exception as e:
        print(f"\n❌ Firecrawl V1 integration test FAILED with error: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return False

async def test_sanctum_api():
    """Test the Sanctum API directly"""
    print("\nTesting Sanctum API...")
    
    try:
        api_url = "https://sanctum-api.ironforge.network/lsts/strongSOL"
        api_key = os.getenv('SANCTUM_API_KEY', '01K07MRJ5YDAQOHRGMD67QX0GH')
        
        # Try different parameter names based on error message "Missing API key"
        param_names = ['apiKey', 'api_key', 'key', 'token', 'auth', 'authorization']
        
        async with aiohttp.ClientSession() as session:
            for param_name in param_names:
                print(f"\nTrying parameter: {param_name}")
                async with session.get(f"{api_url}?{param_name}={api_key}") as response:
                    print(f"Status: {response.status}")
                    if response.status == 200:
                        data = await response.json()
                        print(f"✅ Success with parameter: {param_name}")
                        break
                    else:
                        try:
                            error_text = await response.text()
                            print(f"Error: {error_text[:100]}...")
                        except:
                            pass
            else:
                # Try with headers if query params don't work
                print("\nTrying with headers...")
                headers = {
                    'X-API-Key': api_key,
                    'Authorization': api_key,
                    'x-api-key': api_key
                }
                for header_name, header_value in headers.items():
                    print(f"Trying header: {header_name}")
                    async with session.get(api_url, headers={header_name: header_value}) as response:
                        print(f"Status: {response.status}")
                        if response.status == 200:
                            data = await response.json()
                            print(f"✅ Success with header: {header_name}")
                            break
                        else:
                            try:
                                error_text = await response.text()
                                print(f"Error: {error_text[:100]}...")
                            except:
                                pass
                else:
                    print("❌ All authentication methods failed")
                    return None
        
        print(f"Sanctum API Response: {data}")
        
        if data.get('data') and len(data['data']) > 0:
            strongsol_data = data['data'][0]
            apy_decimal = strongsol_data.get('latestApy')
            
            if apy_decimal is not None:
                apy_percentage = apy_decimal * 100
                print(f"✅ Sanctum APY: {apy_percentage:.2f}%")
                return apy_percentage
        
        print("❌ No APY data found in response")
        return None
                
    except Exception as e:
        print(f"❌ Error fetching Sanctum APY: {str(e)}")
        return None

async def main():
    """Run all tests"""
    print("=== Testing Firecrawl V1 + Sanctum API Integration ===")
    
    # Test Sanctum API first
    sanctum_apy = await test_sanctum_api()
    
    # Test Firecrawl extraction
    await test_firecrawl_v1()
    
    print(f"\n=== Test Summary ===")
    print(f"Sanctum APY: {'✅ PASSED' if sanctum_apy is not None else '❌ FAILED'}")
    print("Firecrawl V1: See results above")

if __name__ == "__main__":
    asyncio.run(main()) 