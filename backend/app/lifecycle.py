"""Active work versus history, per workflow: the single classification used by every list.

History is derived only from the authoritative status. Nothing is flagged, archived or deleted, so a
status change moves an item automatically (a completed order leaves Current orders; a closed custom
request that is reopened returns to the active queue). Each scope lists its filter groups in display
order as (key, label, statuses).

Statuses that look alike differ per workflow:
- A shipped job is still active: the host has handed it over, but it completes only when the buyer
  confirms receipt. A ready job (printed, not yet shipped) is active too.
- A quoted ("accepted") custom request still needs quotation or production work, so it stays active.
"""
from sqlalchemy import func, select

ORDER_SCOPES = {
    'active': (('pending', 'Pending', ('pending',)),
               ('in-progress', 'In progress', ('accepted', 'printing', 'ready')),
               ('shipping', 'Shipping', ('shipped',))),
    'history': (('completed', 'Completed', ('completed',)),
                ('cancelled', 'Cancelled', ('cancelled',))),
}
JOB_SCOPES = {
    'active': (('available', 'Available', ('available',)),
               ('accepted', 'Accepted', ('accepted',)),
               ('in-progress', 'In progress', ('printing',)),
               ('ready', 'Ready to ship', ('ready',)),
               ('shipped', 'Awaiting buyer', ('shipped',))),
    'history': (('completed', 'Completed', ('completed',)),
                ('cancelled', 'Cancelled', ('cancelled',))),
}
REQUEST_SCOPES = {
    'active': (('submitted', 'Submitted', ('submitted',)),
               ('under_review', 'Under review', ('under_review',)),
               ('quoted', 'Accepted', ('quoted',))),
    'history': (('closed', 'Closed', ('closed',)),),
}
SCOPES = ('active', 'history')


def statuses(scopes, scope, group='all'):
    """Statuses of one scope, or of one of its groups ('all' = the whole scope)."""
    groups = scopes[scope]
    if group in (None, '', 'all'):
        return tuple(s for _, _, values in groups for s in values)
    for key, _, values in groups:
        if key == group:
            return values
    raise ValueError(f'Unknown group {group!r} for scope {scope!r}')


def group_keys(scopes, scope):
    return [key for key, _, _ in scopes[scope]]


def scope_of(scopes, status):
    return next(scope for scope in SCOPES if status in statuses(scopes, scope))


def summary(scopes, by_status):
    """Counts for the navigation: {'active': {'total', 'groups': [{key, label, count}]}, 'history': {...}}.
    by_status maps each status to its number of records."""
    result = {}
    for scope in SCOPES:
        groups = [{'key': key, 'label': label, 'count': sum(by_status.get(s, 0) for s in values)} for key, label, values in scopes[scope]]
        result[scope] = {'total': sum(g['count'] for g in groups), 'groups': groups}
    return result


def count_by_status(db, column, *where):
    """{status: count} for the rows matching where (one grouped query)."""
    return dict(db.execute(select(column, func.count()).where(*where).group_by(column)).all())


def page_bounds(total, page, per_page):
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(1, page), pages)
    return page, pages, (page - 1) * per_page
