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
from dotenv import load_dotenv
from firecrawl import FirecrawlApp
from pydantic import BaseModel, Field
from solana.rpc.api import Client

# Load environment variables
load_dotenv()

# Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY')
HELIUS_API_KEY = os.getenv('HELIUS_API_KEY')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '3600'))  # Default to 1 hour if not specified

# Initialize Solana client
SOLANA_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
solana_client = Client(SOLANA_RPC_URL)
current_epoch = None

def format_volume(value):
    """Format volume with K for thousands and M for millions"""
    try:
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
    sol_price: float = Field(alias="sol_price ($)")
    stake: float
    leader_rewards: float
    commission: float
    voting_fee: float
    current_stats_val: float
    current_identity_balance: float
    vote_balance: float
    volume_24h: float = Field(alias="StrongSOL 24hr Volume ($)")
    holders: float = Field(alias="Holders")
    current_supply: float = Field(alias="Current Supply")

async def get_current_epoch():
    """Get the current epoch from Solana RPC"""
    try:
        response = solana_client.get_epoch_info()
        print("Epoch Response:", response)  # Debug print
        
        # Extract epoch from Helius response format
        if hasattr(response, 'value') and hasattr(response.value, 'epoch'):
            return response.value.epoch
        
        return None
    except Exception as e:
        print(f"Error getting epoch info: {str(e)}")
        return None

@bot.event
async def on_ready():
    """Handler for bot ready event"""
    print(f'{bot.user} has connected to Discord!')
    check_epoch.start()

async def post_update():
    """Post an update to the Discord channel"""
    try:
        channel = bot.get_channel(CHANNEL_ID)
        
        print("Making API request...")
        response = app.extract([
            "https://svt.one/dashboard/Ac1beBKixfNdrTAac7GRaTsJTxLyvgGvJjvy4qQfvyfc",
            "https://birdeye.so/token/strng7mqqc1MBJJV6vMzYbEqnwVGvKKGKedeCvtktWA?chain=solana",
            "https://solscan.io/token/strng7mqqc1MBJJV6vMzYbEqnwVGvKKGKedeCvtktWA"
        ], {
            'prompt': '''From SVT.one - Extract the Stake, Commission, Leader Rewards, Voting Fee, SOL Price, Current-stats-val (the current income value next to the income 30 epochs graph), Current Identity Balance, and Vote Balance values.

From Birdeye.so - Extract the 24h Volume value (with the K or M to show thousand or million,whatever it's displaying)

From Solscan.io - extract the holders, current supply''',
            'schema': ExtractSchema.model_json_schema(),
        })
        
        print("API Response:")
        print(response)
        
        if not response or not response.get('success'):
            print("No valid response from API")
            return
            
        data = response.get('data', {})
        if not data:
            print("No data in API response")
            return

        embed = discord.Embed(title='Daily Stronghold & StrongSOL Update')
        
        # Add Epoch Number first
        current_epoch_num = await get_current_epoch()
        if current_epoch_num is not None:
            embed.add_field(name='Current Epoch', value=f"{current_epoch_num:,}", inline=False)
        
        # Validator Data - Add fields in your preferred order
        embed.add_field(name='SOL Price', value=f"${data.get('sol_price ($)', 'N/A'):,.2f}", inline=False)
        embed.add_field(name='Stake', value=f"{data.get('stake', 'N/A'):,.2f} SOL", inline=False)
        embed.add_field(name='Leader Rewards (Previous Epoch)', value=f"{data.get('leader_rewards', 'N/A'):,.2f} SOL", inline=False)
        embed.add_field(name='Commission Earned (Previous Epoch)', value=f"{data.get('commission', 'N/A')} SOL", inline=False)
        embed.add_field(name='Voting Fee', value=f"{data.get('voting_fee', 'N/A')} SOL", inline=False)
        embed.add_field(name='Previous Epoch Total', value=f"{data.get('current_stats_val', 'N/A'):,.2f} SOL", inline=False)
        embed.add_field(name='Current Identity Balance', value=f"{data.get('current_identity_balance', 'N/A'):,.2f} SOL", inline=False)
        embed.add_field(name='Current Vote Balance', value=f"{data.get('vote_balance', 'N/A'):,.2f} SOL", inline=False)
        
        # Token Data
        volume = data.get('StrongSOL 24hr Volume ($)', 0)
        if isinstance(volume, str):
            try:
                volume = float(volume.replace('$', '').replace(',', ''))
            except (ValueError, TypeError):
                volume = 0
        embed.add_field(name='StrongSOL 24h Volume (K/M)', value=format_volume(volume), inline=False)
        embed.add_field(name='StrongSOL Holders', value=f"{data.get('Holders', 'N/A'):,.0f}", inline=False)
        embed.add_field(name='StrongSOL Current Supply', value=f"{data.get('Current Supply', 'N/A'):,.0f}", inline=False)
        
        await channel.send("@everyone", embed=embed)
    except Exception as e:
        print(f'Error posting update: {str(e)}')

@tasks.loop(seconds=CHECK_INTERVAL)
async def check_epoch():
    """Check for epoch changes and post updates"""
    global current_epoch
    
    new_epoch = await get_current_epoch()
    if new_epoch is None:
        return
        
    if current_epoch is None:
        current_epoch = new_epoch
        print(f"Initial epoch: {current_epoch}")
        return
        
    if new_epoch > current_epoch:
        print(f"New epoch detected: {new_epoch} (previous: {current_epoch})")
        current_epoch = new_epoch
        await post_update()
    else:
        print(f"Current epoch: {new_epoch}")

@bot.command(name='test')
async def test_update(ctx):
    """Trigger an immediate update for testing"""
    if ctx.channel.id == CHANNEL_ID:
        await post_update()

if __name__ == "__main__":
    # Verify environment variables
    required_vars = ['DISCORD_TOKEN', 'DISCORD_CHANNEL_ID', 'FIRECRAWL_API_KEY', 'HELIUS_API_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("Error: Missing required environment variables:", missing_vars)
        print("Please check your .env file and ensure all required variables are set.")
        sys.exit(1)
    
    # Run the bot
    bot.run(DISCORD_TOKEN) 