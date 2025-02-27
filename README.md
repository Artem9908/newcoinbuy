# Bybit New Listing Monitor

This project monitors Bybit exchange for new coin listings in real-time.

## Setup

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Configure your API credentials:
   - Copy `config/.env.example` to `config/.env`
   - Fill in your Bybit API credentials in the `.env` file

## Usage

Run the monitor:
```bash
python src/bybit_monitor.py
```

The script will:
- Initialize with all current Bybit spot trading pairs
- Monitor for new listings every second
- Print notifications when new listings are detected

## Configuration

In `config/.env`:
- `BYBIT_API_KEY`: Your Bybit API key
- `BYBIT_API_SECRET`: Your Bybit API secret
- `TESTNET`: Set to "true" to use testnet instead of mainnet

## Customization

To add custom actions when new listings are detected, modify the `handle_new_listing()` method in `src/bybit_monitor.py`. 