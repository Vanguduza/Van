"""Declared calendar times in exact milliseconds, without host-zone guesses."""
from datetime import datetime,timezone
import re


def parse_calendar_ms(value):
    if value is None or type(value) is bool:raise ValueError('calendar timestamp unavailable')
    text=str(value).strip()
    digits=text[1:] if text.startswith('-') else text
    if text.isascii() and digits.isdigit():
        result=int(text)*(1000 if len(digits)<=10 else 1)  # Preserve legacy digit units, including historical epochs.
    else:
        # datetime truncates fractional digits beyond microseconds. Check the
        # original text before parsing so an unavailable instant cannot round down.
        if any(any(digit!='0' for digit in fraction[3:])
               for fraction in re.findall(r'[.,]([0-9]+)',text)):
            raise ValueError('calendar timestamp precision finer than milliseconds requires an explicit adapter policy')
        parsed=datetime.fromisoformat(text[:-1]+'+00:00' if text.endswith('Z') else text)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError('calendar timestamp requires an explicit UTC offset')
        parsed=parsed.astimezone(timezone.utc)
        if parsed.microsecond%1000:
            raise ValueError('calendar timestamp precision finer than milliseconds requires an explicit adapter policy')
        delta=parsed-datetime(1970,1,1,tzinfo=timezone.utc)
        result=delta.days*86400000+delta.seconds*1000+delta.microseconds//1000
    if not -(2**63)<=result<=2**63-1:raise ValueError('calendar timestamp outside supported milliseconds')
    return result
