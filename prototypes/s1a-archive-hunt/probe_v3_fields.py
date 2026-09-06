#!/usr/bin/env python3
"""Census which unhappy-path fields the MBTA V3 /predictions endpoint actually
populates, broken out by route type.

Used by S1a to check whether the signals named in docs/mbta-api.md exist at all
for the commuter-rail tracer bullet, independently of the archive question.
No API key needed (unauthenticated V3 is 20 req/min; this makes 3 calls).
"""

import collections
import json
import time
import urllib.parse
import urllib.request

GROUPS = {
    "commuter_rail": [
        "CR-Worcester", "CR-Providence", "CR-Franklin", "CR-Fitchburg",
        "CR-Newburyport", "CR-Haverhill", "CR-Lowell", "CR-Needham",
        "CR-Greenbush", "CR-Kingston", "CR-Middleborough", "CR-Fairmount",
    ],
    "heavy_rail": ["Red", "Orange", "Blue"],
    "light_rail": ["Green-B", "Green-C", "Green-D", "Green-E", "Mattapan"],
}


def fetch(routes):
    qs = urllib.parse.urlencode({
        "filter[route]": ",".join(routes),
        "page[limit]": 500,
    })
    url = "https://api-v3.mbta.com/predictions?" + qs
    with urllib.request.urlopen(url) as r:
        return json.load(r)["data"]


def main():
    for name, routes in GROUPS.items():
        try:
            recs = fetch(routes)
        except Exception as exc:  # noqa: BLE001 - probe script
            print(name, "ERR", exc)
            continue

        update_type = collections.Counter()
        uncertainty = collections.Counter()
        status = collections.Counter()
        sched_rel = collections.Counter()
        vehicle = collections.Counter()

        for rec in recs:
            a = rec["attributes"]
            update_type[a.get("update_type")] += 1
            uncertainty[a.get("arrival_uncertainty")] += 1
            status[str(a.get("status"))[:26]] += 1
            sched_rel[a.get("schedule_relationship")] += 1
            has_veh = bool((rec["relationships"].get("vehicle") or {}).get("data"))
            vehicle["vehicle" if has_veh else "no_vehicle"] += 1

        print(f"== {name}  n={len(recs)}")
        print("   update_type          ", dict(update_type))
        print("   arrival_uncertainty  ", dict(uncertainty))
        print("   schedule_relationship", dict(sched_rel))
        print("   vehicle relationship ", dict(vehicle))
        print("   status               ", status.most_common(8))
        time.sleep(1)


if __name__ == "__main__":
    main()
