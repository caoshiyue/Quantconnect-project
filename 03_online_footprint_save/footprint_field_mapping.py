# region imports
from AlgorithmImports import *
# endregion
# footprint_field_mapping.py

# These are the column names returned by qb.History() when requesting multiple data types.
DF_COL_TRADE_OPEN = 'open'
DF_COL_TRADE_HIGH = 'high'
DF_COL_TRADE_LOW = 'low'
DF_COL_TRADE_CLOSE = 'close'
DF_COL_TRADE_VOLUME = 'volume'

DF_COL_BID_OPEN = 'bidopen'
DF_COL_BID_HIGH = 'bidhigh'
DF_COL_BID_LOW = 'bidlow'
DF_COL_BID_CLOSE = 'bidclose'
DF_COL_ASK_OPEN = 'askopen'
DF_COL_ASK_HIGH = 'askhigh'
DF_COL_ASK_LOW = 'asklow'
DF_COL_ASK_CLOSE = 'askclose'


# This dictionary maps the DataFrame columns to our internal standard names
HISTORY_DF_FIELD_MAP = {
    DF_COL_TRADE_OPEN: 'trade_open',
    DF_COL_TRADE_HIGH: 'trade_high',
    DF_COL_TRADE_LOW: 'trade_low',
    DF_COL_TRADE_CLOSE: 'trade_close',
    DF_COL_TRADE_VOLUME: 'trade_volume',

    DF_COL_BID_OPEN: 'bid_open',
    DF_COL_BID_HIGH: 'bid_high',
    DF_COL_BID_LOW: 'bid_low',
    DF_COL_BID_CLOSE: 'bid_close',

    DF_COL_ASK_OPEN: 'ask_open',
    DF_COL_ASK_HIGH: 'ask_high',
    DF_COL_ASK_LOW: 'ask_low',
    DF_COL_ASK_CLOSE: 'ask_close',
}
