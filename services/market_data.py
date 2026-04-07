"""
Market data via yfinance (free, no API key).
Used for pre/post market intel.
"""
import yfinance as yf

WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL"]


def get_market_snapshot() -> dict:
    """
    Returns a dict with today's market snapshot for Claude to summarize.
    """
    snapshot = {}
    for ticker in WATCHLIST:
        try:
            t = yf.Ticker(ticker)
            info = t.fast_info
            snapshot[ticker] = {
                "last_price": round(info.last_price, 2) if info.last_price else None,
                "day_change_pct": round(
                    (info.last_price - info.previous_close) / info.previous_close * 100, 2
                ) if info.last_price and info.previous_close else None,
            }
        except Exception:
            continue
    return snapshot


def format_snapshot_for_claude(snapshot: dict) -> str:
    lines = ["今日主要股票涨跌幅："]
    for ticker, data in snapshot.items():
        pct = data.get("day_change_pct")
        price = data.get("last_price")
        if pct is not None:
            sign = "+" if pct >= 0 else ""
            lines.append(f"  {ticker}: ${price}  {sign}{pct}%")
    return "\n".join(lines)
