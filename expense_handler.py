"""
Expense Handler - Google Sheets & Discord Integration for Expense Logging
Handles logging expenses to both Google Sheets and Discord outgoings channel.
"""

import os
import asyncio
import discord
from datetime import datetime
from typing import Dict, Optional, Any
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json


class ExpenseHandler:
    """Handles expense logging to Google Sheets and Discord"""
    
    def __init__(self, bot):
        self.bot = bot
        self.spreadsheet_id = os.getenv('GOOGLE_SHEETS_ID')
        self.worksheet_name = os.getenv('GOOGLE_SHEETS_WORKSHEET', 'Expenses')
        self.outgoings_channel_id = int(os.getenv('OUTGOINGS_CHANNEL_ID', '0'))
        self.service = None
        
    async def initialize(self):
        """Initialize Google Sheets service"""
        try:
            # Load credentials from environment variable
            credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
            
            if not credentials_json:
                print("Error: GOOGLE_CREDENTIALS_JSON not found in environment variables")
                return False
            
            # Load from environment variable (JSON string)
            credentials_info = json.loads(credentials_json)
            credentials = Credentials.from_service_account_info(
                credentials_info,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            # Build the service in a thread to avoid blocking
            self.service = await asyncio.to_thread(
                build, 'sheets', 'v4', credentials=credentials
            )
            print("Google Sheets service initialized successfully")
            return True
            
        except json.JSONDecodeError as e:
            print(f"Error parsing Google credentials JSON: {str(e)}")
            return False
        except Exception as e:
            print(f"Error initializing Google Sheets service: {str(e)}")
            return False
    
    async def setup_headers_if_needed(self):
        """Setup headers in the Google Sheet if they don't exist"""
        try:
            if not self.service:
                await self.initialize()
                
            if not self.service:
                return False
            
            # Check if headers exist
            range_name = f"{self.worksheet_name}!A1:H1"
            request = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            )
            result = await asyncio.to_thread(request.execute)
            
            values = result.get('values', [])
            
            # If no headers or incomplete headers, add or upgrade them
            desired_headers = [
                'Category',
                'Amount',
                'Currency',
                'Solana Epoch',
                'Transaction Hash',
                'Timestamp',
                'Discord User',
                'Notes'
            ]

            need_update = False
            if not values or len(values[0]) == 0:
                need_update = True
            else:
                current_headers = values[0]
                # If legacy (7 columns) or mismatched, update to desired headers
                if len(current_headers) < len(desired_headers) or current_headers[:len(desired_headers)] != desired_headers:
                    need_update = True

            if need_update:
                body = {'values': [desired_headers]}
                request = self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{self.worksheet_name}!A1:H1",
                    valueInputOption='RAW',
                    body=body
                )
                await asyncio.to_thread(request.execute)
                print("Headers set/updated in Google Sheet")
            
            return True
            
        except Exception as e:
            print(f"Error setting up headers: {str(e)}")
            return False
    
    async def log_to_google_sheets(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Log expense to Google Sheets"""
        try:
            if not self.service:
                if not await self.initialize():
                    return {
                        'success': False,
                        'message': 'Failed to initialize Google Sheets service'
                    }
            
            # Ensure headers exist
            await self.setup_headers_if_needed()
            
            # Prepare data for insertion
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # Column order: Category | Amount | Currency | Solana Epoch | Transaction Hash | Timestamp | Discord User | Notes
            row_data = [
                user_data.get('category', ''),
                user_data.get('amount', ''),
                user_data.get('currency', 'SOL'),
                str(user_data.get('epoch', 'N/A')),
                user_data.get('transaction_hash', ''),
                timestamp,
                user_data.get('discord_user', 'Unknown'),
                user_data.get('notes', '')
            ]
            
            # Append to sheet
            range_name = f"{self.worksheet_name}!A:H"
            body = {'values': [row_data]}
            
            request = self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body=body
            )
            result = await asyncio.to_thread(request.execute)
            
            return {
                'success': True,
                'message': f'Expense logged to Google Sheets successfully',
                'timestamp': timestamp
            }
            
        except HttpError as e:
            error_msg = f"Google Sheets API error: {str(e)}"
            print(error_msg)
            return {
                'success': False,
                'message': error_msg
            }
        except Exception as e:
            error_msg = f"Unexpected error logging to Google Sheets: {str(e)}"
            print(error_msg)
            return {
                'success': False,
                'message': error_msg
            }
    
    async def post_to_discord(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Post expense to Discord outgoings channel"""
        try:
            channel = self.bot.get_channel(self.outgoings_channel_id)
            if not channel:
                return {
                    'success': False,
                    'message': f'Outgoings channel with ID {self.outgoings_channel_id} not found'
                }
            
            # Create formatted embed
            embed = discord.Embed(
                title=f'💰 Expense Logged - Epoch {user_data.get("epoch", "N/A")}',
                color=discord.Color.orange(),
                timestamp=datetime.now()
            )
            
            # Add fields
            currency = user_data.get('currency', 'SOL')
            embed.add_field(name='📊 Category', value=user_data.get('category', 'N/A'), inline=True)
            embed.add_field(name='💵 Amount', value=f"{user_data.get('amount', 'N/A')} {currency}", inline=True)
            embed.add_field(name='👤 User', value=user_data.get('discord_user', 'Unknown'), inline=True)
            
            if user_data.get('transaction_hash'):
                # Truncate hash for display
                tx_hash = user_data['transaction_hash']
                display_hash = f"{tx_hash[:8]}...{tx_hash[-8:]}" if len(tx_hash) > 16 else tx_hash
                embed.add_field(name='🔗 Transaction', value=f"`{display_hash}`", inline=False)
            
            if user_data.get('notes'):
                embed.add_field(name='📝 Notes', value=user_data['notes'], inline=False)
            
            # Add footer
            embed.set_footer(text="StrongBot Expense Tracker")
            
            await channel.send(embed=embed)
            
            return {
                'success': True,
                'message': 'Posted to Discord outgoings channel successfully'
            }
            
        except discord.errors.HTTPException as e:
            error_msg = f"Discord error posting to outgoings channel: {str(e)}"
            print(error_msg)
            return {
                'success': False,
                'message': error_msg
            }
        except Exception as e:
            error_msg = f"Unexpected error posting to Discord: {str(e)}"
            print(error_msg)
            return {
                'success': False,
                'message': error_msg
            }
    
    async def log_expense(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Log expense to both Google Sheets and Discord
        
        Args:
            user_data: Dictionary containing:
                - discord_user: Discord username
                - epoch: Current Solana epoch
                - category: Expense category
                - amount: Expense amount
                - transaction_hash: Transaction hash
                - notes: Additional notes
        
        Returns:
            Dictionary with success status and message
        """
        sheets_result = await self.log_to_google_sheets(user_data)
        discord_result = await self.post_to_discord(user_data)
        
        # Both must succeed for overall success
        if sheets_result['success'] and discord_result['success']:
            return {
                'success': True,
                'message': '✅ Expense logged successfully to both Google Sheets and Discord!',
                'timestamp': sheets_result.get('timestamp')
            }
        elif not sheets_result['success'] and not discord_result['success']:
            return {
                'success': False,
                'message': f"❌ Failed to log expense:\n• Google Sheets: {sheets_result['message']}\n• Discord: {discord_result['message']}"
            }
        else:
            # Partial success - treat as failure and ask to retry
            failed_system = "Google Sheets" if not sheets_result['success'] else "Discord"
            successful_system = "Discord" if not sheets_result['success'] else "Google Sheets"
            return {
                'success': False,
                'message': f"❌ Partial failure - {successful_system} succeeded but {failed_system} failed. Please try again.\n• {failed_system}: {sheets_result['message'] if not sheets_result['success'] else discord_result['message']}"
            }
    
    async def test_connection(self) -> Dict[str, bool]:
        """Test connection to both Google Sheets and Discord"""
        results = {}
        
        # Test Google Sheets
        try:
            if not self.service:
                await self.initialize()
            
            if self.service:
                request = self.service.spreadsheets().get(
                    spreadsheetId=self.spreadsheet_id
                )
                result = await asyncio.to_thread(request.execute)
                results['google_sheets'] = True
                print("✅ Google Sheets connection successful")
            else:
                results['google_sheets'] = False
                print("❌ Google Sheets connection failed")
                
        except Exception as e:
            results['google_sheets'] = False
            print(f"❌ Google Sheets connection failed: {str(e)}")
        
        # Test Discord channel
        try:
            channel = self.bot.get_channel(self.outgoings_channel_id)
            results['discord'] = channel is not None
            if channel:
                print(f"✅ Discord outgoings channel found: #{channel.name}")
            else:
                print(f"❌ Discord outgoings channel not found (ID: {self.outgoings_channel_id})")
                
        except Exception as e:
            results['discord'] = False
            print(f"❌ Discord channel test failed: {str(e)}")
        
        return results