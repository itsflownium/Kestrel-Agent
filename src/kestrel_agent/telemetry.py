"""Content-free timings and cumulative usage accounting."""
import time
from contextlib import contextmanager

FIELDS = ('input_tokens', 'output_tokens', 'cached_input_tokens', 'cache_write_input_tokens', 'reasoning_output_tokens')


class Telemetry:
    def __init__(self):
        self.records = []

    @contextmanager
    def measure(self, stage, **metadata):
        record = {'stage': stage, **metadata, 'status': 'error'}
        start = time.monotonic()
        try:
            yield record
            record['status'] = 'completed'
        except BaseException as error:
            record['error_type'] = type(error).__name__
            raise
        finally:
            record['seconds'] = round(time.monotonic() - start, 6)
            self.records.append(record)


class UsageLedger:
    """Thread totals are cumulative snapshots, not additional usage on each event."""
    def __init__(self):
        self.threads = {}
        self.totals = {key: 0 for key in FIELDS}

    def observe(self, thread_id, total):
        previous = self.threads.setdefault(thread_id, {})
        delta = {}
        for key in FIELDS:
            value = getattr(total, key, None)
            if value is None:
                delta[key] = None
                continue
            if type(value) is not int or value < 0:
                raise ValueError('Invalid token usage snapshot.')
            # Repeated and out-of-order updates must never double count usage.
            high = previous.get(key, 0)
            delta[key] = max(0, value - high)
            previous[key] = max(high, value)
            self.totals[key] += delta[key]
        return delta
