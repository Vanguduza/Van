"""Read-only rows from one captured watchlist revision and explicit source facts."""
from decimal import Decimal, localcontext

from .monitor_models import WatchlistMarketRow, WatchlistMarketResult
from .monitor_calculations import text


def project_watchlist(view, body, *, source, qualify, clock, digest):
    rows = []
    search = body.search.casefold()
    for index, entry in enumerate(view.state.entries):
        instrument = entry.instrument
        if (view.state.favourites_only and not entry.favourite
                or body.venue is not None and instrument.venue != body.venue
                or body.environment is not None and instrument.environment != body.environment
                or body.api_family is not None and instrument.api_family != body.api_family
                or search and not any(search in value.casefold() for value in
                                      (instrument.symbol, instrument.product_id, instrument.venue))):
            continue
        source_failed = False
        try:
            snapshot = source.market(instrument, body.timeframe)
        except Exception:
            snapshot = None
            source_failed = True
        # Source reads may take time: age is checked after each observation, never at request start.
        now = clock()
        snapshot, reason = qualify(snapshot, instrument, body.timeframe, body.max_age_ms, now)
        if source_failed:
            reason = 'SOURCE_READ_FAILED'
        row = WatchlistMarketRow(instrument=instrument, favourite=entry.favourite, manual_index=index,
            state='UNAVAILABLE', reason=reason, evaluated_at_ms=now, change_state='SOURCE_UNAVAILABLE')
        if snapshot is not None:
            last = snapshot.bars[-1]
            row.state = 'AVAILABLE'
            row.price, row.price_age_ms = last.close, now-last.end_ms
            row.event_time_ms, row.available_at_ms = last.end_ms, snapshot.available_at_ms
            row.source_id, row.source_revision = snapshot.source_id, snapshot.source_revision
            row.sample_id = digest(snapshot.model_dump(mode='json'))
            row.change_state = 'HISTORY_UNAVAILABLE'
            if len(snapshot.bars) >= 2:
                previous = snapshot.bars[-2]
                row.reference_price, row.reference_time_ms = previous.close, previous.end_ms
                row.change_interval_ms = last.end_ms-previous.end_ms
                reference = Decimal(previous.close)
                row.change_state = 'ZERO_REFERENCE' if reference == 0 else 'AVAILABLE'
                if reference != 0:
                    with localcontext() as context:
                        context.prec = 80
                        row.change_pct = text((Decimal(last.close)-reference)/abs(reference)*100)
        rows.append(row)

    sort_by = view.state.sort_by
    if sort_by == 'MANUAL':
        metric = lambda row: row.manual_index
    elif sort_by == 'SYMBOL':
        metric = lambda row: (row.instrument.symbol.casefold(), row.instrument.product_id.casefold(),
                              row.instrument.venue.casefold(), row.instrument.environment)
    else:
        field = {'PRICE':'price', 'CHANGE_PCT':'change_pct', 'SPREAD':'spread'}[sort_by]
        metric = lambda row: Decimal(getattr(row, field)) if getattr(row, field) is not None else None
    # Missing values stay last in either direction. Equal values preserve owner order.
    known = [(row, metric(row)) for row in rows if metric(row) is not None]
    unknown = [row for row in rows if metric(row) is None]
    ordered = [row for row, _ in sorted(known, key=lambda pair: pair[1], reverse=view.state.descending)] + unknown
    metric_state = ('NOT_APPLICABLE' if not rows else 'UNAVAILABLE' if not known
                    else 'PARTIAL' if unknown else 'AVAILABLE')
    return WatchlistMarketResult(object_id=view.object_id, revision=view.revision,
        state_sha256=view.state_sha256, request=body, sort_by=sort_by, descending=view.state.descending,
        favourites_only=view.state.favourites_only, sort_metric_state=metric_state,
        selected_count=len(view.state.entries), filtered_count=len(rows), rows=ordered, evaluated_at_ms=clock())
