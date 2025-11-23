# custom_consolidator.py

from datetime import timedelta, datetime
from AlgorithmImports import *

class CustomTradeBarConsolidator(PythonConsolidator):
    """ 
    A custom TradeBar consolidator implemented in Python.
    Emits one consolidated TradeBar each time the configured 'period' has elapsed
    since the start (Time) of the working bar.
    """

    def __init__(self, period: timedelta):
        # Validate the consolidation period (> 0)
        if period is None or period.total_seconds() <= 0:
            raise ValueError("period must be a positive timedelta")

        # IDataConsolidator-required fields
        self.input_type = TradeBar
        self.output_type = TradeBar
        self.consolidated = None
        self.working_data = None

        # Consolidator settings
        self.period = period

    def update(self, data) -> None:
        """
        Updates this consolidator with the specified data (TradeBar).
        Aggregates O/H/L/C/V in-place.
        """
        if data is None or not isinstance(data, TradeBar):
            return

        if self.working_data is None:
            # Start a new bar anchored at the first bar's Time
            self.working_data = TradeBar(
                data.time,
                data.symbol,
                float(data.open),
                float(data.high),
                float(data.low),
                float(data.close),
                int(data.volume),
                self.period,
            )
            return

        # Aggregate into the existing working bar
        wd = self.working_data
        # Open remains from the first bar
        wd.high = max(float(wd.high), float(data.high))
        wd.low = min(float(wd.low), float(data.low))
        wd.close = float(data.close)
        wd.volume = int(wd.volume) + int(data.volume)

    def scan(self, current_local_time: datetime) -> None:
        """
        Scans this consolidator to see if it should emit a bar due to time passing.
        Emits when elapsed time >= period.
        """
        if self.working_data is None:
            return

        start_time = self.working_data.time
        if current_local_time - start_time >= self.period:
            # Set a deterministic EndTime
            self.working_data.end_time = start_time + self.period

            # Publish the consolidated bar
            self.consolidated = self.working_data
            self.on_data_consolidated(self, self.consolidated)

            # Reset working state for the next bar
            self.working_data = None

    def reset(self) -> None:
        """
        Resets the consolidator state.
        """
        self.consolidated = None
        self.working_data = None
        try:
            super().reset()
        except Exception:
            pass

    # Clean up method (recommended for IDataConsolidator)
    def dispose(self):
        self.reset()