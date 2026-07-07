---
name: automated-intraday-pipeline
description: >-
  Guides an AI agent through a scheduled, event-driven intraday trading pipeline for the Indian stock market using Dhan/Upstox API, Gemini Flash, Google Search, and WhatsApp notifications.
---

# Automated Intraday Trading Pipeline

## Overview
This skill provides a systematic, instruction-only workflow for an AI agent to execute a scheduled, event-driven intraday trading pipeline. It is optimized for the Indian stock market (NSE/BSE) using Dhan/Upstox API integrations, Gemini Flash + Google Search for asset filtering, and automated WhatsApp alert updates for trade tracking and logging.

## Dependencies
* **credentials**: Used to retrieve API tokens/credentials for Dhan/Upstox, Google Search, Gemini API, and WhatsApp notification webhook.

## Quick Start
To trigger this pipeline daily, the agent must run at scheduled checkpoints corresponding to Indian Standard Time (IST):
1. **8:45 AM IST**: Fetch pre-market sentiment and news using Google Search and Gemini Flash.
2. **9:08 AM IST**: Retrieve final pre-market prices, filter candidates, and compute size.
3. **9:15 AM IST**: Send entry OCO Bracket Orders via Dhan/Upstox API.
4. **3:15 PM IST**: Verify auto-liquidation of intraday (MIS) positions.
5. **3:30 PM IST**: Compile daily PnL and dispatch WhatsApp summary.

---

## Workflow

### 1. Daily Ingestion & Scanning (8:45 AM – 9:07 AM IST)
* **Action**: Scan the market for high-relative-volume pre-market stocks.
* **Tools**: Use Google Search and Gemini Flash to search for active overnight Indian stock news (e.g., earnings releases, corporate actions, analyst upgrades).
* **Filters**:
  * Keep only stocks with Average Daily Volume (ADV) > 2,000,000 shares.
  * Price ranges between ₹15 and ₹3000.
  * Sentiment must be strongly bullish (for long setups) or bearish (for short setups) based on Gemini Flash analysis of news.

### 2. Sizing & Selection (9:08 AM – 9:14 AM IST)
* **Action**: Parse the settled pre-market quotes (which lock in at 9:08 AM IST in Indian markets).
* **Calculations**:
  1. Determine the top 3 highest-momentum setups based on Bollinger Band Squeeze or VWAP breakouts.
  2. Compute the exact position size per stock:
     $$\text{Position Size (Shares)} = \frac{\text{Account Capital} \times 0.01}{\text{Entry Price} - \text{Stop-Loss Price}}$$
  3. Validate that the Stop-Loss is no greater than 5% of the entry price. If it is wider, discard the stock.

### 3. Execution Gateway (9:15 AM IST)
* **Action**: At market open, send OCO (One-Cancels-the-Other) Bracket Orders via the chosen broker API (Dhan or Upstox).
* **Order Details**:
  * Set a marketable limit order for entry (to prevent slippage).
  * Attach a hard Stop-Loss order at the broker level.
  * Attach a Profit-Target order at the broker level (minimum 1:2 risk-to-reward ratio).
  * If the broker API times out, **immediately** start the retry loop and alert the user via WhatsApp.

### 4. Intra-Day Monitoring & Retry Loop (9:15 AM – 3:14 PM IST)
* **Action**: Periodically check order statuses via WebSockets or polling.
* **Error handling**:
  * If a connection drop occurs, the agent must retry connecting every 30 seconds.
  * **Alerting**: On every connection failure or API error, send a WhatsApp message to the user with the exact error details. Keep trying up to 10 times before shifting to a backup execution route.

### 5. Final Square-Off & Reporting (3:15 PM – 3:30 PM IST)
* **Action**: Indian intraday MIS orders auto-liquidate at 3:15 PM. Check Dhan/Upstox order books to ensure all positions are closed. If any position remains open, manually trigger a market-sell or market-buy to liquidate it.
* **Logging**: Log all trades to the local sheet/database: `Symbol`, `Type`, `Entry Price`, `Exit Price`, `Exit Time`, and `PnL`.
* **WhatsApp summary**: Send a WhatsApp message to the user in the format:
  ```text
  📊 Daily Trading Summary:
  - Stock 1: [Symbol] | [BUY/SELL] | PnL: +₹[Amount]
  - Stock 2: [Symbol] | [BUY/SELL] | PnL: -₹[Amount]
  - Net Day PnL: ₹[Total]
  ```

---

## Rate Limiting & Webhook Integrations
* **Gemini / Google Search API**: Limit requests to 1 request per second to avoid 429 errors.
* **Dhan / Upstox API**: Do not exceed 10 requests per second.
* **WhatsApp Notification Gateway**: Send messages using a simple CallMeBot API webhook URL structure:
  `https://api.callmebot.com/whatsapp.php?phone=[YOUR_PHONE]&text=[MESSAGE]&apikey=[YOUR_API_KEY]`

---

## Common Mistakes
1. **Trading Pre-Market Spikes**: Do not enter trades before 9:15 AM IST. The pre-market session (9:00 AM – 9:08 AM) is only for scanning and pricing, not trading.
2. **Missing Hard Stops**: Always submit the Stop-Loss immediately with the Entry order. Never leave a position unhedged on the broker's server.
3. **Over-Leveraging**: Do not exceed the calculated 1% risk size even if a trade setup looks "guaranteed."
