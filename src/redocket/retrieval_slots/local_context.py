from collections import Counter
from statistics import median


def _route_size(item):
    units = item.record.reported.get("pallets")
    return "大托" if units and units >= 13 else "散托"


def context(current, neighbors, old, score):
    docket = current.record.reported
    overdue = [
        item for item in neighbors if (item.record.reported.get("age") or 0) > score
    ]
    units = Counter()
    for ticket in overdue:
        document = ticket.record.reported
        if document["disputed"] == 1:
            units["disputed"] += document["pallets"] or 0
        elif document["collectors"] is not None:
            units["eligible"] += document["pallets"] or 0
    route_class = _route_size(current)
    reference_ages = [
        item.record.reported["age"]
        for item in old
        if _route_size(item) == route_class and item.record.reported["age"] is not None
    ]
    remaining = (docket["collectors"] or 0) - units["eligible"] / 22
    hold = (
        docket["distance"] is not None
        and docket["distance"] > 144
        and remaining < 0.3
        and (docket["pallets"] or 0) > 14
    )
    return {
        "decision": "远程大托集中，需复核空车回程合单" if hold else "",
        "support": len(reference_ages),
        "route_class": route_class,
        "overdue_eligible_units": units["eligible"],
        "deposit_disputed_units": units["disputed"],
        "pickup_reserve": remaining,
        "typical_dispatch_age": median(reference_ages) if reference_ages else None,
    }
