"""
StrongBot - Solana Validator & StrongSOL Token Tracker
A Discord bot that tracks and reports validator statistics and token metrics.
"""

import discord
from discord.ext import commands, tasks
import time
import signal
import sys
import os
from dotenv import load_dotenv, find_dotenv
from firecrawl import FirecrawlApp
from pydantic import BaseModel, Field, validator
from solana.rpc.api import Client
import asyncio # Added for sleep
import aiohttp # Added for async HTTP requests
import csv # Added for CSV parsing
from typing import Optional, List, Dict, Any # Added for typing

# Load environment variables
load_dotenv(find_dotenv(usecwd=True))

# Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))
FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY')
HELIUS_API_KEY = os.getenv('HELIUS_API_KEY')

# Remove this line for debugging
# print(f"DEBUG: Raw CHECK_INTERVAL from .env: '{os.getenv('CHECK_INTERVAL', '3600')}'")

CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '3600'))
WALLET_BALANCES_URL = "https://strongpricebotvercel-erpqwps50-burriteauxs-projects.vercel.app/api/balances"

# Initialize Solana client
SOLANA_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
solana_client = Client(SOLANA_RPC_URL)
current_epoch = None

def format_volume(value):
    """Format volume with K for thousands and M for millions"""
    try:
        if value is None:
            return "N/A"
        if value >= 1_000_000:
            return f"${value/1_000_000:,.1f}M"
        elif value >= 1_000:
            return f"${value/1_000:,.1f}K"
        else:
            return f"${value:,.2f}"
    except (TypeError, ValueError):
        return "N/A"

# Initialize bot and FireCrawl
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
bot = commands.Bot(command_prefix='!', intents=intents)
app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)

def signal_handler(sig, frame):
    """Handle shutdown gracefully"""
    print('\nShutting down bot...')
    bot.loop.run_until_complete(bot.close())
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

class ExtractSchema(BaseModel):
    """Schema for the data extraction API response"""
    sol_price: Optional[float] = Field(default=None, alias="sol_price ($)")
    stake: Optional[float] = Field(default=None)
    leader_rewards: Optional[float] = Field(default=None)
    commission: Optional[float] = Field(default=None)
    voting_fee: Optional[float] = Field(default=None)
    current_stats_val: Optional[float] = Field(default=None) # Previous Epoch Total
    # current_identity_balance: Optional[float] = Field(default=None) # Removed
    # vote_balance: Optional[float] = Field(default=None) # Removed
    volume_24h: Optional[float] = Field(default=None, alias="StrongSOL 24hr Volume ($)")
    holders: Optional[float] = Field(default=None, alias="Holders")
    current_supply: Optional[float] = Field(default=None, alias="Current Supply")
    last_epoch_apy: Optional[float] = Field(default=None, alias="Last Epoch's APY")

    @validator('*', pre=True)
    def empty_str_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

async def get_current_epoch():
    """Get the current epoch from Solana RPC"""
    try:
        response = await asyncio.to_thread(solana_client.get_epoch_info) # Run blocking call in thread
        print("Epoch Response:", response) 
        
        if hasattr(response, 'value') and hasattr(response.value, 'epoch'):
            return response.value.epoch
        
        return None
    except Exception as e:
        print(f"Error getting epoch info: {str(e)}")
        return None

async def get_wallet_balances() -> Dict[str, Any]:
    """Fetch and parse wallet balances from the CSV URL."""
    balances = []
    total_sol = 0.0
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(WALLET_BALANCES_URL) as response:
                response.raise_for_status() # Raise an exception for HTTP errors
                content = await response.text()
                reader = csv.reader(content.splitlines())
                next(reader) # Skip header row
                for row in reader:
                    if len(row) >= 2:
                        wallet_address = row[0]
                        try:
                            balance = float(row[1])
                            balances.append({"address": wallet_address, "balance": balance})
                            total_sol += balance
                        except ValueError:
                            print(f"Could not parse balance for wallet {wallet_address}: {row[1]}")
        return {"individual_balances": balances, "total_balance": total_sol}
    except aiohttp.ClientError as e:
        print(f"Error fetching wallet balances: {str(e)}")
        return {"individual_balances": [], "total_balance": 0.0, "error": str(e)}
    except csv.Error as e:
        print(f"Error parsing CSV data: {str(e)}")
        return {"individual_balances": [], "total_balance": 0.0, "error": str(e)}
    except Exception as e:
        print(f"Unexpected error in get_wallet_balances: {str(e)}")
        return {"individual_balances": [], "total_balance": 0.0, "error": str(e)}

@bot.event
async def on_ready():
    """Handler for bot ready event"""
    print(f'{bot.user} has connected to Discord!')
    check_epoch.start()

async def post_update():
    """Post an update to the Discord channel or print data if channel is None."""
    channel = None
    try:
        # Try to get channel only if bot object has it (i.e., running as full bot)
        if bot and hasattr(bot, 'get_channel'):
            channel = bot.get_channel(CHANNEL_ID)

        # If channel is None (e.g., running in test mode from __main__), 
        # we won't send to Discord but will print fetched data.
        if channel is None:
            print("Running in terminal test mode: Channel not available. Will print data instead of sending to Discord.")

        print("Making Firecrawl API request...")
        firecrawl_response = await asyncio.to_thread(
            app.extract,
            urls=[
                "https://svt.one/dashboard/Ac1beBKixfNdrTAac7GRaTsJTxLyvgGvJjvy4qQfvyfc",
                "https://birdeye.so/token/strng7mqqc1MBJJV6vMzYbEqnwVGvKKGKedeCvtktWA?chain=solana",
                "https://solscan.io/token/strng7mqqc1MBJJV6vMzYbEqnwVGvKKGKedeCvtktWA",
                "https://app.sanctum.so/strongSOL"
            ],
            prompt='''From SVT.one - Extract the Stake, Commission, Leader Rewards, Voting Fee, SOL Price, and Current-stats-val (the current income value next to the income 30 epochs graph).

From Birdeye.so - Extract the 24h Volume value (e.g., $3.1K or $1.2M).

From Solscan.io - Extract the holders and current supply.

From app.sanctum.so/strongSOL - Extract the APY value that is labeled as "Last Epoch's APY" from the strongSOL staking page.''',
            schema=ExtractSchema.model_json_schema()
        )
        print("Firecrawl API Response:")
        print(firecrawl_response)
        
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

        wallet_data = await get_wallet_balances()
        
        # If in terminal test mode (no channel), print collected data and return
        if channel is None:
            print("\n--- Terminal Test Mode: Fetched Data ---")
            print("Firecrawl Extracted Data (first item if multiple URLs were successful):")
            # Attempt to pretty print if data is a dict, otherwise regular print
            if isinstance(data, dict):
                import json
                print(json.dumps(data, indent=2))
            else:
                print(data)
            print("\nWallet Balances Data:")
            print(json.dumps(wallet_data, indent=2))
            print("--- End of Terminal Test ---")
            return # Exit before trying to use Discord objects

        # --- Original code continues below if channel is available ---
        if not channel: # This check is now redundant if the above 'if channel is None' handles it, but keep for safety
            print(f"Error: Channel with ID {CHANNEL_ID} not found after initial check.")
            return

        individual_balances = wallet_data.get("individual_balances", [])
        total_wallet_balance = wallet_data.get("total_balance", 0.0)
        if wallet_data.get("error"):
            print(f"Could not display wallet balances due to error: {wallet_data.get('error')}")

        embed = discord.Embed(title='Stronghold & StrongSOL Update', color=discord.Color.blue())
        
        current_epoch_num = await get_current_epoch()
        if current_epoch_num is not None:
            embed.add_field(name='Current Epoch', value=f"{current_epoch_num:,}", inline=False)
        
        embed.add_field(name='SOL Price', value=f"${data.get('sol_price ($)', 'N/A'):,.2f}" if data.get('sol_price ($)') is not None else "N/A", inline=False)
        embed.add_field(name='Stake', value=f"{data.get('stake', 'N/A'):,.2f} SOL" if data.get('stake') is not None else "N/A", inline=False)
        embed.add_field(name='StrongSOL Current Supply', value=f"{data.get('Current Supply', 'N/A'):,.0f}" if data.get('Current Supply') is not None else "N/A", inline=False)
        embed.add_field(name='Leader Rewards (Previous Epoch)', value=f"{data.get('leader_rewards', 'N/A'):,.2f} SOL" if data.get('leader_rewards') is not None else "N/A", inline=False)
        embed.add_field(name='Commission Earned (Previous Epoch)', value=f"{data.get('commission', 'N/A')} SOL" if data.get('commission') is not None else "N/A", inline=False)
        embed.add_field(name='Voting Fee', value=f"{data.get('voting_fee', 'N/A')} SOL" if data.get('voting_fee') is not None else "N/A", inline=False)
        embed.add_field(name='Previous Epoch Total', value=f"{data.get('current_stats_val', 'N/A'):,.2f} SOL" if data.get('current_stats_val') is not None else "N/A", inline=False)

        # Define wallet labels
        wallet_labels = {
            "Cx46fVnmtGBpGJtsdQMWhHTfGkKnswJHx1QhSCp16DWF": "Multisig",
            "91oPXTs2oq8VvJpQ5TnvXakFGnnJSpEB6HFWDtSctwMt": "Identity",
            "Ac1beBKixfNdrTAac7GRaTsJTxLyvgGvJjvy4qQfvyfc": "Vote"
        }

        if individual_balances:
            for bal_info in individual_balances:
                wallet_address = bal_info["address"]
                display_label = wallet_labels.get(wallet_address, "Wallet") # Get custom label or default to "Wallet"
                embed.add_field(name=f'{display_label}: {wallet_address[:4]}...{wallet_address[-4:]}', value=f"{bal_info['balance']:,.2f} SOL", inline=True)
            embed.add_field(name='Total Wallet Balance', value=f"{total_wallet_balance:,.2f} SOL", inline=False)
        elif wallet_data.get("error"):
             embed.add_field(name='Wallet Balances', value=f"Error fetching: {wallet_data.get('error')}", inline=False)
        else:
            embed.add_field(name='Wallet Balances', value="N/A", inline=False)
        
        # Add Last Epoch's APY (Moved Here)
        apy_value = data.get("Last Epoch's APY") # Fetching data using the original alias
        if apy_value is not None:
            try:
                if isinstance(apy_value, str):
                    apy_value_cleaned = apy_value.replace('%', '').strip()
                    apy_float = float(apy_value_cleaned)
                elif isinstance(apy_value, (int, float)):
                    apy_float = float(apy_value)
                else:
                    apy_float = None
                
                if apy_float is not None:
                    embed.add_field(name="StrongSOL Last APY", value=f"{apy_float:.2f}%", inline=False) # Display name changed
                else:
                    embed.add_field(name="StrongSOL Last APY", value="N/A", inline=False) # Display name changed
            except ValueError:
                 embed.add_field(name="StrongSOL Last APY", value="N/A (parse error)", inline=False) # Display name changed
        else:
            embed.add_field(name="StrongSOL Last APY", value="N/A", inline=False) # Display name changed

        # Token Data
        volume_str = data.get('StrongSOL 24hr Volume ($)')
        volume_val = None
        if isinstance(volume_str, (int, float)):
            volume_val = volume_str
        elif isinstance(volume_str, str):
            try:
                volume_str_cleaned = volume_str.replace('$', '').replace(',', '')
                if 'K' in volume_str_cleaned.upper():
                    volume_val = float(volume_str_cleaned.upper().replace('K', '')) * 1_000
                elif 'M' in volume_str_cleaned.upper():
                    volume_val = float(volume_str_cleaned.upper().replace('M', '')) * 1_000_000
                else:
                    volume_val = float(volume_str_cleaned)
            except (ValueError, TypeError):
                volume_val = None
        
        embed.add_field(name='StrongSOL 24h Volume (K/M)', value=format_volume(volume_val), inline=False)
        embed.add_field(name='StrongSOL Holders', value=f"{data.get('Holders', 'N/A'):,.0f}" if data.get('Holders') is not None else "N/A", inline=False)
        
        await channel.send("@everyone", embed=embed)
    except discord.errors.HTTPException as e:
        # If in terminal test mode and this somehow gets hit (e.g. channel was found but send failed)
        if channel is None: 
            print(f"Discord HTTP Error occurred, but was in terminal test mode: {str(e)}")
            return
        print(f"Discord HTTP Error posting update: {str(e)}. Status: {e.status}. Code: {e.code}. Message: {e.text}")
    except Exception as e:
        import traceback
        # If in terminal test mode
        if channel is None:
            print(f"An error occurred during terminal test mode in post_update: {str(e)}")
            print(traceback.format_exc())
            return # Important to return here if channel is None
        print(f'Error posting update: {str(e)}')
        print(traceback.format_exc())

@tasks.loop(seconds=CHECK_INTERVAL)
async def check_epoch():
    """Check for epoch changes and post updates"""
    global current_epoch
    
    new_epoch = await get_current_epoch()
    if new_epoch is None:
        print("Failed to get new epoch, skipping this check.")
        return
        
    if current_epoch is None:
        current_epoch = new_epoch
        print(f"Initial epoch: {current_epoch}. Bot will post on next epoch change.")
        # Optionally, post an update on first run after setting initial epoch
        # await post_update() 
        return
        
    if new_epoch > current_epoch:
        print(f"New epoch detected: {new_epoch} (previous: {current_epoch})")
        await post_update() # Post update before updating current_epoch
        current_epoch = new_epoch # Update current_epoch only after successful post or attempt
    else:
        print(f"Current epoch: {new_epoch} (no change or older epoch detected, which is unusual)")

@bot.command(name='test')
async def test_update(ctx):
    """Trigger an immediate update for testing"""
    if ctx.channel.id == CHANNEL_ID:
        await ctx.send("Test update triggered, fetching data...")
        await post_update()
        await ctx.send("Test update complete.")
    else:
        await ctx.send(f"This command can only be used in the designated channel ID: {CHANNEL_ID}")

if __name__ == "__main__":
    required_vars = ['DISCORD_TOKEN', 'DISCORD_CHANNEL_ID', 'FIRECRAWL_API_KEY', 'HELIUS_API_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("Error: Missing required environment variables:", missing_vars)
        print("Please check your .env file and ensure all required variables are set.")
        sys.exit(1)
    
    print("Starting StrongBot...") # Message for normal operation
    # To run the full bot:
    # 1. Comment out the asyncio.run(post_update()) line below.
    # 2. Uncomment the bot.run(DISCORD_TOKEN) line.
    
    # For terminal testing (now commented out):
    # asyncio.run(post_update())
    
    # For normal bot operation:
    bot.run(DISCORD_TOKEN) 