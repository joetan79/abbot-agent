"""
CoinGecko API - real-time crypto prices.
Free, no API key required.
"""

import httpx
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

COINGECKO_URL = "https://api.coingecko.com/api/v3"

COIN_IDS = {
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "sol": "solana",
    "solana": "solana",
    "bnb": "binancecoin",
    "xrp": "ripple",
    "ada": "cardano",
    "doge": "dogecoin",
    "usdt": "tether",
    "usdc": "usd-coin",
}

DEFAULT_COINS = ["bitcoin", "ethereum", "solana"]


def get_prices(coins: list = None) -> dict:
    if not coins:
        coins = DEFAULT_COINS
    coin_ids = []
    for coin in coins:
        cid = COIN_IDS.get(coin.lower(), coin.lower())
        if cid not in coin_ids:
            coin_ids.append(cid)
    try:
        response = httpx.get(
            f"{COINGECKO_URL}/simple/price",
            params={
                "ids": ",".join(coin_ids),
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_7d_change": "true",
                "include_24hr_vol": "true",
                "include_market_cap": "true",
            },
            timeout=10,
            headers={"User-Agent": "ABbot/1.0"},
        )
        if response.status_code == 200:
            data = response.json()
            logger.info(f"CoinGecko: {len(data)} coins fetched")
            return data
        else:
            logger.error(f"CoinGecko: {response.status_code}")
            return {}
    except Exception as e:
        logger.error(f"CoinGecko error: {e}")
        return {}


def get_trending() -> list:
    try:
        r = httpx.get(
            f"{COINGECKO_URL}/search/trending",
            timeout=10,
            headers={"User-Agent": "ABbot/1.0"},
        )
        if r.status_code == 200:
            coins = r.json().get("coins", [])
            return [c["item"]["symbol"].upper()
                    for c in coins[:5]]
        return []
    except Exception:
        return []


def format_change(change: float) -> str:
    if change is None:
        return "N/A"
    arrow = "▲" if change >= 0 else "▼"
    return f"{arrow} {abs(change):.2f}%"


def format_price(price: float) -> str:
    if price is None:
        return "N/A"
    if price >= 1000:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:.4f}"
    else:
        return f"${price:.6f}"


def format_volume(vol: float) -> str:
    if vol is None:
        return "N/A"
    if vol >= 1_000_000_000:
        return f"${vol/1_000_000_000:.2f}B"
    elif vol >= 1_000_000:
        return f"${vol/1_000_000:.2f}M"
    return f"${vol:,.0f}"


def build_crypto_report(coins: list = None) -> str:
    prices = get_prices(coins)
    if not prices:
        return "Unable to fetch crypto prices. Please try again."
    now = datetime.now().strftime("%d %b %Y %H:%M")
    trending = get_trending()
    display_names = {
        "bitcoin": "Bitcoin (BTC)",
        "ethereum": "Ethereum (ETH)",
        "solana": "Solana (SOL)",
        "binancecoin": "BNB",
        "ripple": "XRP",
        "cardano": "Cardano (ADA)",
        "dogecoin": "Dogecoin (DOGE)",
    }
    lines = [
        f"Crypto Prices - Live",
        f"Updated: {now}\n",
    ]
    for coin_id, data in prices.items():
        name = display_names.get(coin_id, coin_id.upper())
        price = format_price(data.get("usd"))
        change_24h = format_change(data.get("usd_24h_change"))
        change_7d = format_change(data.get("usd_7d_change"))
        vol = format_volume(data.get("usd_24h_vol"))
        mcap = format_volume(data.get("usd_market_cap"))
        lines.append(
            f"{name}\n"
            f"Price: {price}\n"
            f"24h: {change_24h}  7d: {change_7d}\n"
            f"Volume: {vol}  MCap: {mcap}\n"
        )
    if trending:
        lines.append(f"Trending: {', '.join(trending)}")
    lines.append(f"\nData: CoinGecko (live)")
    return "\n".join(lines)


def extract_coins_from_text(text: str) -> list:
    text_lower = text.lower()
    found = []
    for symbol, coin_id in COIN_IDS.items():
        if symbol in text_lower and coin_id not in found:
            found.append(coin_id)
    return found if found else DEFAULT_COINS
