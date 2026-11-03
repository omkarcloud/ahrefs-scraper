"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. Params go through the same schemas the API uses, so defaults
are filled in and a domain or an ahrefs.com link both work.
"""
import json
import os

import config
from ahrefs import api, schemas

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


def run(schema_cls, fn, **params):
    return fn(**schema_cls().load(params))


if __name__ == "__main__":
    # a domain or any ahrefs.com/websites link — traffic since 2015, ranks, countries, keywords, competitors, DR
    save("overview_tesla.json", run(schemas.TargetSchema, api.domain_overview, target="tesla.com"))

    # Ahrefs' ranking of the most visited websites, worldwide or by country / category
    save("top_websites_us.json", run(schemas.TopWebsitesSchema, api.websites_top, country="US"))

    # Domain Rating + the top 20 backlinks (needs CAPSOLVER_API_KEY, see config.py)
    if config.CAPSOLVER_API_KEY:
        save("backlinks_tesla.json", run(schemas.TargetModeSchema, api.domain_backlinks, target="tesla.com"))
    else:
        print("skipped backlinks_tesla.json: set CAPSOLVER_API_KEY to run the free-tool endpoints")
