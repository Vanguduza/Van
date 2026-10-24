"""Local last-write entry bounds; never evidence about an already-sent effect."""
from vati.execution.base import VenueUnavailable

class EntryNotSent(VenueUnavailable):
    """The bounded entry was refused before the native financial write."""


def require_entry_deadline(expires_at_ms, clock):
    if type(expires_at_ms) is not int or not 0 < expires_at_ms < 2**63 or not callable(clock):
        raise EntryNotSent('explicit entry deadline or current clock unavailable; not sent')
    try:
        now_ms = clock()
    except Exception:
        raise EntryNotSent('current entry clock unavailable; not sent') from None
    if type(now_ms) is not int or not 0 <= now_ms < expires_at_ms:
        raise EntryNotSent('original entry deadline invalid or expired; not sent')
