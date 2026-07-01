"""Confirm the OpenAlex 500 is IP-level throttling (not the query). Run this in a SECOND terminal
WHILE run_experiment.py is going (so this IP is under the same load), or right after a failure:

    PYTHONPATH=. uv run python scripts/diagnose_openalex_500.py

It fires the exact failing q03 Arm B query raw (no pyalex retry to swallow the body) 6× and prints
HTTP status + the response BODY. If you see 500/429 + a rate/throttle message here while the same
query returns 200 from an idle network, the cause is OpenAlex throttling this IP under run load.
"""

import time

import requests

import config  # noqa: F401 -- bootstrap backend/.env
from app.core.config import settings

BASE = "https://api.openalex.org/works"

_G1 = [
    "behavioural intervention",
    "behavioral intervention",
    "communication intervention",
    "health communication",
    "consumer education",
    "social marketing",
    "nudging",
    "choice architecture",
    "public information campaign",
    "information provision",
    "consumer information",
    "health messaging",
    "digital intervention",
    "online intervention",
    "digital communication",
    "online messaging",
    "online education",
    "web-based intervention",
    "mobile intervention",
    "app-based intervention",
    "consumer guidance",
    "public awareness campaign",
]
_G2 = [
    "supermarket",
    "supermarkets",
    "grocery store",
    "grocery stores",
    "food retailer",
    "food retailers",
    "retail food environment",
    "online grocery",
    "online store",
    "e-grocery",
    "e-commerce",
    "digital platform",
    "online platform",
    "online shopping",
    "online retail",
]
_G3 = [
    "purchasing behaviour",
    "purchasing behavior",
    "consumer purchasing",
    "purchase patterns",
    "buying behaviour",
    "buying behavior",
    "shopping behaviour",
    "shopping behavior",
    "recommended purchasing guidelines",
    "consumer guidelines",
    "food purchasing",
    "adherent purchases",
    "adherence to guidelines",
    "stockpiling",
    "panic buying",
    "food shortage",
    "supply shortage",
    "food supplies",
    "adaptive purchasing",
    "hoarding",
    "supply chain disruption",
    "consumer response",
    "purchase intention",
    "purchase decision",
]


def _grp(t):
    return "(" + " OR ".join(f'"{x}"' for x in t) + ")"


FLT = f"title_and_abstract.search:({_grp(_G1)} AND {_grp(_G2)} AND {_grp(_G3)}),cited_by_count:>5"

params = {"filter": FLT, "per-page": 200, "cursor": "*"}
if getattr(settings, "OPENALEX_EMAIL", None):
    params["mailto"] = settings.OPENALEX_EMAIL
if getattr(settings, "OPENALEX_API_KEY", None):
    params["api_key"] = settings.OPENALEX_API_KEY  # exact pyalex authed-pool params

print(f"mailto set: {'mailto' in params} | api_key set: {'api_key' in params}\n")
for i in range(6):
    try:
        r = requests.get(BASE, params=params, timeout=60)
        print(f"[{i+1}] HTTP {r.status_code}  body: {r.text[:300]!r}")
    except Exception as e:
        print(f"[{i+1}] EXCEPTION {type(e).__name__}: {e}")
    time.sleep(0.3)
