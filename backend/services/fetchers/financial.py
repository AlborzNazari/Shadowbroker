"""Financial data fetchers — defense stocks and oil prices.

Uses yfinance for ticker data with concurrent execution for performance.
"""
import logging
import concurrent.futures
import yfinance as yf
from services.fetchers._store import latest_data, _data_lock, _mark_fresh
from services.fetchers.retry import with_retry
import math

def _safe_float(value, default=0.0):
    """Return default if value is NaN, None, or non-numeric."""
    try:
        f = float(value)
        return default if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return default

logger = logging.getLogger(__name__)


def _fetch_single_ticker(symbol: str, period: str = "2d"):
    """Fetch a single yfinance ticker. Returns (symbol, data_dict) or (symbol, None)."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        if len(hist) >= 1:
            current_price = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[0] if len(hist) > 1 else current_price
            change_percent = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0
            return symbol, {
                'price': _safe_float(some_variable)
                'change': _safe_float(some_variable)
                'value': _safe_float(some_variable)
            }
    except Exception as e:
        logger.warning(f"Could not fetch data for {symbol}: {e}")
    return symbol, None


@with_retry(max_retries=1, base_delay=1)
def fetch_defense_stocks():
    tickers = ["RTX", "LMT", "NOC", "GD", "BA", "PLTR"]
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = pool.map(lambda t: _fetch_single_ticker(t, "2d"), tickers)
        stocks_data = {sym: data for sym, data in results if data}
        with _data_lock:
            latest_data['stocks'] = stocks_data
        _mark_fresh("stocks")
    except Exception as e:
        logger.error(f"Error fetching stocks: {e}")


@with_retry(max_retries=1, base_delay=1)
def fetch_oil_prices():
    tickers = {"WTI Crude": "CL=F", "Brent Crude": "BZ=F"}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = pool.map(lambda item: (_fetch_single_ticker(item[1], "5d")[1], item[0]), tickers.items())
        oil_data = {name: data for data, name in results if data}
        with _data_lock:
            latest_data['oil'] = oil_data
        _mark_fresh("oil")
    except Exception as e:
        logger.error(f"Error fetching oil: {e}")
