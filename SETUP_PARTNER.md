# StrongBot Partner Setup Guide

This is a private setup guide for running StrongBot on your Windows PC.

## One-Time Setup

1. Install Python if not already installed:
   - Download from: https://www.python.org/downloads/
   - Make sure to check "Add Python to PATH" during installation

2. Clone the repository:
```bash
git clone https://github.com/Burriteaux/StrongBot.git
cd StrongBot
```

3. Create and activate virtual environment:
```bash
python -m venv env
env\Scripts\activate
```

4. Install dependencies:
```bash
pip install -r requirements.txt
```

5. Create `.env` file with these contents (replace with your actual values):
```
# Discord Configuration
DISCORD_TOKEN=your_discord_bot_token_here
DISCORD_CHANNEL_ID=your_discord_channel_id_here

# API Keys
FIRECRAWL_API_KEY=your_firecrawl_api_key_here
HELIUS_API_KEY=your_helius_api_key_here
SANCTUM_API_KEY=your_sanctum_api_key_here

# Bot Configuration
CHECK_INTERVAL=3600
```

## Running the Bot

1. Open Command Prompt
2. Navigate to bot directory:
```bash
cd path\to\StrongBot
```

3. Activate virtual environment:
```bash
env\Scripts\activate
```

4. Run the bot:
```bash
python discord_bot.py
```

## Updating the Bot

When I make updates, pull the latest changes:
```bash
git pull origin main
```

## Troubleshooting

If you see any errors:
1. Make sure virtual environment is activated
2. Try running `pip install -r requirements.txt` again
3. Check that `.env` file exists and has correct values
4. Contact me for help

## Security Note

Keep this setup guide and the `.env` file private. Don't share them with anyone else. 