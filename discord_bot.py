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
from expense_handler import ExpenseHandler

# Load environment variables
load_dotenv(find_dotenv(usecwd=True))

# Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))
FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY')
HELIUS_API_KEY = os.getenv('HELIUS_API_KEY')
SANCTUM_API_KEY = os.getenv('SANCTUM_API_KEY')

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

# Initialize expense handler
expense_handler = ExpenseHandler(bot)

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
    # last_epoch_apy: Removed - now fetched directly from Sanctum API

    @validator('*', pre=True)
    def empty_str_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


class ExpenseModal(discord.ui.Modal, title='Log Expense'):
    """Modal for expense entry"""
    
    def __init__(self, user_command_message=None, bot_form_message=None, original_channel=None):
        super().__init__()
        self.user_command_message = user_command_message  # The user's !add command
        self.bot_form_message = bot_form_message  # The bot's category selection form
        self.original_channel = original_channel
        
    # Category dropdown will be handled differently - we'll use a Select View first
    category = discord.ui.TextInput(
        label='Category',
        placeholder='LST Reserve, Server Payment, vSOL Transfer, Team Payout, Other',
        required=True,
        max_length=100
    )
    
    amount = discord.ui.TextInput(
        label='Amount (SOL)',
        placeholder='Enter amount in SOL (e.g., 125.50)',
        required=True,
        max_length=50
    )
    
    transaction_hash = discord.ui.TextInput(
        label='Transaction Hash',
        placeholder='Enter Solana transaction hash',
        required=False,
        max_length=200
    )
    
    notes = discord.ui.TextInput(
        label='Notes',
        placeholder='Additional notes (optional)',
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission"""
        # Defer the response to give us time to process
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get current epoch
            current_epoch_num = await get_current_epoch()
            
            # Validate amount
            try:
                amount_val = float(self.amount.value.strip())
                if amount_val <= 0:
                    raise ValueError("Amount must be greater than 0")
            except ValueError:
                await interaction.followup.send(
                    "❌ Invalid amount. Please enter a valid number greater than 0.",
                    ephemeral=True
                )
                return
            
            # Validate category
            valid_categories = ['LST Reserve', 'Server Payment', 'vSOL Transfer', 'Team Payout', 'Other']
            category_val = self.category.value.strip()
            
            # Check if it's a valid preset category or "Other" with custom text
            if category_val not in valid_categories and not category_val.startswith('Other'):
                # If it's not a preset and doesn't start with "Other", treat it as "Other: {input}"
                category_val = f"Other: {category_val}"
            
            # Prepare user data
            user_data = {
                'discord_user': f"{interaction.user.name}#{interaction.user.discriminator}",
                'epoch': current_epoch_num,
                'category': category_val,
                'amount': str(amount_val),
                'transaction_hash': self.transaction_hash.value.strip(),
                'notes': self.notes.value.strip()
            }
            
            # Log the expense
            result = await expense_handler.log_expense(user_data)
            
            if result['success']:
                await interaction.followup.send(
                    f"{result['message']}\n\n"
                    f"**Details:**\n"
                    f"• Category: {category_val}\n"
                    f"• Amount: {amount_val} SOL\n"
                    f"• Epoch: {current_epoch_num}\n"
                    f"• User: {user_data['discord_user']}",
                    ephemeral=True
                )
                
                # Clean up: Delete BOTH the user's !add command AND bot's category form
                # Delete user's !add command
                if self.user_command_message:
                    try:
                        await self.user_command_message.delete()
                    except discord.errors.NotFound:
                        pass  # Message already deleted
                    except discord.errors.Forbidden:
                        print("Warning: Bot lacks permission to delete user command")
                    except Exception as e:
                        print(f"Error deleting user command: {str(e)}")
                
                # Delete bot's category selection form
                if self.bot_form_message:
                    try:
                        await self.bot_form_message.delete()
                    except discord.errors.NotFound:
                        pass  # Message already deleted
                    except discord.errors.Forbidden:
                        print("Warning: Bot lacks permission to delete bot form")
                    except Exception as e:
                        print(f"Error deleting bot form: {str(e)}")
                
                # Create a new expense form for the next entry
                if self.original_channel:
                    try:
                        new_view = CategorySelectView(original_channel=self.original_channel)
                        new_embed = discord.Embed(
                            title="💰 Log New Expense",
                            description="Ready for next expense entry:",
                            color=discord.Color.green()
                        )
                        new_message = await self.original_channel.send(embed=new_embed, view=new_view)
                        # Update the view to reference the new form message for future deletions
                        new_view.bot_form_message = new_message
                    except Exception as e:
                        print(f"Error creating new expense form: {str(e)}")
            else:
                await interaction.followup.send(
                    f"{result['message']}\n\n"
                    f"Please try the `!add` command again.",
                    ephemeral=True
                )
                
        except Exception as e:
            print(f"Error in expense modal submission: {str(e)}")
            await interaction.followup.send(
                "❌ An unexpected error occurred while logging the expense. Please try again.",
                ephemeral=True
            )


class CategorySelectView(discord.ui.View):
    """View with category selection dropdown"""
    
    def __init__(self, user_command_message=None, bot_form_message=None, original_channel=None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.user_command_message = user_command_message  # The user's !add command
        self.bot_form_message = bot_form_message  # This category selection form
        self.original_channel = original_channel
        
    @discord.ui.select(
        placeholder="Choose an expense category...",
        options=[
            discord.SelectOption(label="LST Reserve", description="LST Reserve expenses"),
            discord.SelectOption(label="Server Payment", description="Server-related payments"),
            discord.SelectOption(label="vSOL Transfer", description="vSOL transfer expenses"),
            discord.SelectOption(label="Team Payout", description="Team member payouts"),
            discord.SelectOption(label="Other", description="Other expenses (specify in form)")
        ]
    )
    async def category_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Handle category selection"""
        selected_category = select.values[0]
        
        # Create and show the expense modal with the selected category
        modal = ExpenseModal(
            user_command_message=self.user_command_message,
            bot_form_message=self.bot_form_message,
            original_channel=self.original_channel
        )
        modal.category.default = selected_category
        
        await interaction.response.send_modal(modal)

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

async def get_sanctum_apy() -> Optional[float]:
    """Fetch StrongSOL APY data directly from Sanctum API."""
    try:
        # Using the correct API endpoint that works
        api_url = "https://sanctum-api.ironforge.network/lsts/strongSOL"
        api_key = SANCTUM_API_KEY
        
        if not api_key:
            print("Error: SANCTUM_API_KEY not found in environment variables")
            return None
        
        # Use correct authentication method discovered from testing
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{api_url}?apiKey={api_key}") as response:
                print(f"Sanctum API Status: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                elif response.status == 400:
                    error_text = await response.text()
                    if "Invalid API key" in error_text:
                        print("Error: Invalid Sanctum API key. Please check your SANCTUM_API_KEY in .env file")
                        print("The API key from the screenshot may be a demo key. You may need to:")
                        print("1. Register for a real API key at Ironforge")
                        print("2. Or contact Sanctum/Ironforge for API access")
                        return None
                    else:
                        print(f"Sanctum API error: {error_text}")
                        return None
                else:
                    response.raise_for_status()
                    data = await response.json()
                
                # Response format: {"data": [{"latestApy": 0.0820367444573813, ...}]}
                if data.get('data') and len(data['data']) > 0:
                    # Get the strongSOL data (first item in the array)
                    strongsol_data = data['data'][0]
                    apy_decimal = strongsol_data.get('latestApy')
                    
                    if apy_decimal is not None:
                        # Convert decimal to percentage (e.g., 0.082 -> 8.2%)
                        apy_percentage = apy_decimal * 100
                        print(f"Successfully fetched Sanctum APY: {apy_percentage:.2f}%")
                        return apy_percentage
                
                print("No APY data found in Sanctum API response")
                return None
                
    except aiohttp.ClientError as e:
        print(f"Error fetching Sanctum APY - HTTP error: {str(e)}")
        return None
    except Exception as e:
        print(f"Error fetching Sanctum APY - Unexpected error: {str(e)}")
        return None

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
                "https://solscan.io/token/strng7mqqc1MBJJV6vMzYbEqnwVGvKKGKedeCvtktWA"
            ],
            prompt='''From SVT.one - Extract the Stake, Commission, Leader Rewards, Voting Fee, SOL Price, and Current-stats-val (the current income value next to the income 30 epochs graph).

From Birdeye.so - Extract the 24h Volume value (e.g., $3.1K or $1.2M).

From Solscan.io - Extract the holders and current supply.''',
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
        
        # Fetch APY data directly from Sanctum API
        sanctum_apy = await get_sanctum_apy()
        
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
            print("\nSanctum APY Data:")
            print(f"APY: {sanctum_apy}%" if sanctum_apy is not None else "APY: N/A")
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
        
        # Add StrongSOL APY from Sanctum API
        if sanctum_apy is not None:
            embed.add_field(name="StrongSOL Last APY", value=f"{sanctum_apy:.2f}%", inline=False)
        else:
            embed.add_field(name="StrongSOL Last APY", value="N/A", inline=False)

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

@bot.command(name='add')
async def add_expense(ctx):
    """Trigger expense logging modal"""
    try:
        # Create and send the category selection view
        view = CategorySelectView(
            user_command_message=ctx.message,  # User's !add command
            original_channel=ctx.channel
        )
        embed = discord.Embed(
            title="💰 Log New Expense",
            description="Please select a category for your expense:",
            color=discord.Color.blue()
        )
        sent_message = await ctx.send(embed=embed, view=view)
        # Update the view to reference the bot's form message
        view.bot_form_message = sent_message
    except Exception as e:
        print(f"Error in add command: {str(e)}")
        await ctx.send("❌ Error creating expense form. Please try again.", ephemeral=True)

@bot.command(name='test_expense')
async def test_expense_connection(ctx):
    """Test expense logging connections (Google Sheets and Discord)"""
    try:
        await ctx.send("🧪 Testing expense logging connections...")
        
        # Test connections
        results = await expense_handler.test_connection()
        
        embed = discord.Embed(
            title="🧪 Expense System Test Results",
            color=discord.Color.green() if all(results.values()) else discord.Color.red()
        )
        
        embed.add_field(
            name="📊 Google Sheets", 
            value="✅ Connected" if results.get('google_sheets') else "❌ Failed", 
            inline=True
        )
        embed.add_field(
            name="💬 Discord Channel", 
            value="✅ Connected" if results.get('discord') else "❌ Failed", 
            inline=True
        )
        
        if all(results.values()):
            embed.add_field(
                name="Status", 
                value="🎉 All systems operational!", 
                inline=False
            )
        else:
            embed.add_field(
                name="Status", 
                value="⚠️ Some systems failed. Check logs for details.", 
                inline=False
            )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        print(f"Error in test_expense command: {str(e)}")
        await ctx.send("❌ Error testing expense connections. Check logs for details.")

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