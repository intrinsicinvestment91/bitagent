import time
import logging
import httpx

logger = logging.getLogger(__name__)

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
BINANCE_URL = "https://api.binance.com/api/v3/ticker/price"

BINANCE_SYMBOLS = {
    "bitcoin": "BTCUSDT",
    "ethereum": "ETHUSDT",
    "litecoin": "LTCUSDT",
}

CACHE_TTL = 60  # seconds
_cache: dict = {}  # { coin: { "price": float, "ts": float } }


async def _fetch_coingecko(coins: list[str]) -> dict[str, float]:
    params = {"ids": ",".join(coins), "vs_currencies": "usd"}
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(COINGECKO_URL, params=params)
        r.raise_for_status()
        data = r.json()
        return {coin: data[coin]["usd"] for coin in coins if coin in data}


async def _fetch_binance(coin: str) -> float | None:
    symbol = BINANCE_SYMBOLS.get(coin)
    if not symbol:
        return None
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(BINANCE_URL, params={"symbol": symbol})
        r.raise_for_status()
        return float(r.json()["price"])


async def get_prices(coins: list[str]) -> dict:
    now = time.time()
    result = {}
    stale = []
    missing = []

    for coin in coins:
        cached = _cache.get(coin)
        if cached and (now - cached["ts"]) < CACHE_TTL:
            result[coin] = {"price_usd": cached["price"], "stale": False}
        elif cached:
            stale.append(coin)
        else:
            missing.append(coin)

    to_fetch = missing + stale

    if to_fetch:
        try:
            fresh = await _fetch_coingecko(to_fetch)
        except Exception as e:
            logger.warning(f"CoinGecko failed: {e}, trying Binance fallback")
            fresh = {}
            for coin in to_fetch:
                try:
                    price = await _fetch_binance(coin)
                    if price:
                        fresh[coin] = price
                except Exception:
                    pass

        for coin, price in fresh.items():
            _cache[coin] = {"price": price, "ts": now}
            result[coin] = {"price_usd": price, "stale": False}

        # Return last cached value for any that still failed
        for coin in to_fetch:
            if coin not in result:
                cached = _cache.get(coin)
                if cached:
                    result[coin] = {"price_usd": cached["price"], "stale": True}
                else:
                    result[coin] = {"error": "Price unavailable"}

    return result


async def sats_to_usd(sats: int) -> dict:
    prices = await get_prices(["bitcoin"])
    btc_price = prices.get("bitcoin", {}).get("price_usd")
    if not btc_price:
        return {"error": "BTC price unavailable"}
    usd = round((sats / 100_000_000) * btc_price, 6)
    return {"sats": sats, "usd": usd, "btc_price_usd": btc_price}


class PriceOracleAgent:
    name = "PriceOracleAgent"
    description = "Real-time asset price feeds. BTC/USD and major crypto pairs."
    price_sats = {"single": 2, "batch": 5, "convert": 1}
    supported_coins = ["bitcoin", "ethereum", "litecoin", "dogecoin", "monero"]

    def get_info(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "pricing": self.price_sats,
            "supported_coins": self.supported_coins,
            "cache_ttl_seconds": CACHE_TTL,
        }

    async def price(self, coins: list[str]) -> dict:
        return await get_prices(coins)

    async def convert(self, sats: int) -> dict:
        return await sats_to_usd(sats)
