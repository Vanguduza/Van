"""Market-data sources for research and demo (Rev 5 Part E). Every source
writes into the bar lake with a manifest hash so a backtest can name exactly
which bytes it ran on."""

from vati.market_data.feeds.csv_source import bars_from_csv, bars_to_csv
from vati.market_data.feeds.dukascopy import DukascopyDownloader, decode_bi5, dukascopy_url
from vati.market_data.feeds.lake import BarLake

__all__ = ["BarLake", "DukascopyDownloader", "bars_from_csv", "bars_to_csv", "decode_bi5", "dukascopy_url"]
