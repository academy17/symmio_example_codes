# XRP Trading Bot Logic

This bot automates trading for the XRP/USDT pair using a predefined entry and exit strategy. Below is a brief overview of the bot's logic and functionality:

## Logic Overview

1. **Login and Authentication**:
   - The bot uses a wallet's private key to perform a Sign-In with Ethereum (SIWE) login.
   - It fetches a nonce, signs a message, and obtains an access token for authenticated API requests.

2. **Price Monitoring**:
   - The bot continuously fetches the current price of XRP/USDT from Binance.
   - It compares the price against the configured `ENTRY_PRICE` and `EXIT_PRICE`.

3. **Opening a Trade**:
   - When the price drops below the `ENTRY_PRICE`, the bot initiates an instant trade.
   - It fetches the current price from the Muon oracle, adjusts it by 1% (for slippage), and sends a trade request.
   - The API returns a temporary quote ID, which the bot uses to track the trade's status.

4. **Polling for Quote Status**:
   - The bot polls the `/instant_open` endpoint to monitor the status of the temporary quote ID.
   - It waits until the quote ID is confirmed (a positive permanent ID is received).

5. **Closing a Trade**:
   - When the price rises above the `EXIT_PRICE`, the bot closes the position.
   - It fetches the current price from the Muon oracle, applies a 1% slippage, and sends a close request.

6. **Error Handling and Logging**:
   - The bot logs all key actions, including API responses, errors, and status updates.
   - It retries failed operations (e.g., fetching prices or polling for status) with configurable intervals.

## Key Features

- **Configurable Parameters**:
  - Entry and exit prices, trade quantity, leverage, and polling intervals are defined in the `CONFIG` dictionary.
  
- **Environment Variables**:
  - Sensitive data like the private key, API URLs, and account addresses are loaded from environment variables.

- **Robust Polling**:
  - The bot handles temporary quote IDs and waits for confirmation before proceeding.

- **Logging**:
  - Detailed logs are printed for every step, making it easy to debug and monitor the bot's behavior.

## Summary

The bot follows a simple trading strategy:
- Enter a position when the price is low.
- Exit the position when the price is high.
- Continuously monitor the status of trades and handle errors gracefully.