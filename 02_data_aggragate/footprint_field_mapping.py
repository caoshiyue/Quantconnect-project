# footprint_field_mapping.py

# --- QuantConnect History DataFrame Columns ---
# These are the column names returned by qb.History() when requesting multiple data types.
DF_COL_TIME = 'time'
DF_COL_SYMBOL = 'symbol'

# Trade Data Columns
DF_COL_TRADE_OPEN = 'open'
DF_COL_TRADE_HIGH = 'high'
DF_COL_TRADE_LOW = 'low'
DF_COL_TRADE_CLOSE = 'close'
DF_COL_TRADE_VOLUME = 'volume'

# Quote Data Columns
DF_COL_BID_OPEN = 'bidopen'
DF_COL_BID_HIGH = 'bidhigh'
DF_COL_BID_LOW = 'bidlow'
DF_COL_BID_CLOSE = 'bidclose'
DF_COL_ASK_OPEN = 'askopen'
DF_COL_ASK_HIGH = 'askhigh'
DF_COL_ASK_LOW = 'asklow'
DF_COL_ASK_CLOSE = 'askclose'
DF_COL_BID_SIZE = 'bidsize'
DF_COL_ASK_SIZE = 'asksize'


# --- Internal Standardized Field Names ---
# These are the names we will use internally within our functions after mapping.
STD_FIELD_TRADE_OPEN = 'trade_open'
STD_FIELD_TRADE_HIGH = 'trade_high'
STD_FIELD_TRADE_LOW = 'trade_low'
STD_FIELD_TRADE_CLOSE = 'trade_price' # Using 'price' to align with 'value' concept
STD_FIELD_TRADE_VOLUME = 'trade_volume'

STD_FIELD_BID_PRICE = 'bid_price'
STD_FIELD_ASK_PRICE = 'ask_price'

# This dictionary maps the DataFrame columns to our internal standard names
HISTORY_DF_FIELD_MAP = {
    DF_COL_TRADE_OPEN: STD_FIELD_TRADE_OPEN,
    # DF_COL_TRADE_HIGH: STD_FIELD_TRADE_HIGH, # Not strictly needed for footprint logic
    # DF_COL_TRADE_LOW: STD_FIELD_TRADE_LOW,   # Not strictly needed for footprint logic
    DF_COL_TRADE_CLOSE: STD_FIELD_TRADE_CLOSE,
    DF_COL_TRADE_VOLUME: STD_FIELD_TRADE_VOLUME,
    DF_COL_BID_CLOSE: STD_FIELD_BID_PRICE,
    DF_COL_ASK_CLOSE: STD_FIELD_ASK_PRICE,
}

# --- QuantConnect Data Object Attributes ---
# These are the attribute names on TradeBar and QuoteBar objects
OBJ_ATTR_OPEN = 'open'
OBJ_ATTR_HIGH = 'high'
OBJ_ATTR_LOW = 'low'
OBJ_ATTR_CLOSE = 'close'
OBJ_ATTR_VOLUME = 'volume'
OBJ_ATTR_END_TIME = 'end_time'
OBJ_ATTR_PERIOD = 'period'
OBJ_ATTR_SYMBOL = 'symbol'
OBJ_ATTR_TIME = 'time'

OBJ_ATTR_BID = 'bid'
OBJ_ATTR_ASK = 'ask'
from AlgorithmImports import *
# endregion

# Your New Python File
