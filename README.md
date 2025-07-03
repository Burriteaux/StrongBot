# StrongBot - Solana Validator & StrongSOL Token Tracker

A Discord bot that tracks and reports Solana validator statistics and StrongSOL token metrics. The bot automatically posts updates at the beginning of each new Solana epoch.

## Features

- Real-time tracking of Solana epochs
- Automatic updates at epoch transitions
- Comprehensive validator statistics
- StrongSOL token metrics
- Manual update command (!test)

## Data Points Tracked

- Current Solana Epoch
- SOL Price
- Validator Stake
- Leader Rewards
- Commission Earned
- Voting Fee
- SOL Amount to LST (Leader Rewards + Commission - Voting Fee)
- StrongSOL 24h Volume
- StrongSOL Holders Count
- StrongSOL Current Supply

## Setup Instructions

1. Clone the repository:
```bash
git clone https://github.com/Burriteaux/StrongBot.git
cd StrongBot
```

2. Create and activate a virtual environment:
```bash
# On Windows
python -m venv env
env\Scripts\activate

# On macOS/Linux
python3 -m venv env
source env/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a .env file:
```bash
cp .env.example .env
```

5. Configure your environment variables in the .env file:
- Add your Discord bot token
- Add your Discord channel ID (this should be a number, e.g., 1234567890)
- Add your FireCrawl API key
- Add your Helius API key

## Recent Updates

**✅ Firecrawl V1 Migration Complete** - The bot has been updated to use Firecrawl V1 API. See `FIRECRAWL_V1_MIGRATION.md` for full migration details.

## Running the Bot

1. Ensure your virtual environment is activated
2. Run the bot:
```bash
python discord_bot.py
```

## Commands

- `!test` - Manually trigger an update (only works in the configured channel)

## Monitoring

The bot will:
- Check for new epochs every hour
- Post updates with @everyone mention when a new epoch starts
- Display comprehensive statistics in a formatted Discord embed

## Error Handling

The bot includes:
- Graceful shutdown with Ctrl+C
- Error logging for API requests
- Automatic reconnection on Discord disconnects

## Security Notes

- Never commit your .env file
- Keep your API keys secure
- Use environment variables for sensitive data

## Support

For issues or questions, please open an issue in the repository.

## License

MIT License - feel free to use and modify as needed.