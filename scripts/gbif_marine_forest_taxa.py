#!/usr/bin/env python3
"""Build a GBIF backbone table for marine-forest taxa.

The script resolves each requested taxon, downloads its accepted species from
the GBIF Backbone Taxonomy, applies the freshwater and terrestrial exclusions,
and writes two CSV files:

- gbif_marine_forest_species.csv: one row per accepted species, with the
  hierarchy and GBIF taxon keys from class down to species
- gbif_marine_forest_taxa.csv: the taxon keys of the groups themselves,
  including names GBIF could not resolve

Run from the repository root:

    python3 scripts/gbif_marine_forest_taxa.py
    python3 scripts/gbif_marine_forest_taxa.py --resolve-only

No third-party packages are required.

Taxonomic choices encoded below:

- Seagrass genera Thalassia and Halophila are restricted to Plantae,
  Hydrocharitaceae. Both names also belong to animal genera.
- Lepilaena is retained as a query because it was merged into Althenia.
- Alcyonacea and Octocorallia are not accepted taxa in the GBIF backbone.
  Octocorallia is represented by the accepted orders Malacalcyonacea,
  Scleralcyonacea and the residual order Pennatulacea. Sea pens and
  Helioporidae are currently classified in Scleralcyonacea.
- Order Ignatiales is not in the backbone. Its genera Ignatius,
  Pseudocharacium and Symbiochlorum are excluded by name. GBIF places
  Pseudocharacium in Chlorophyceae, outside Ulvophyceae.
- Pneophyllum cetinaensis, Sphacelaria fluviatilis and Sphacelaria lacustris
  are not in the backbone. They stay in the exclusion list so a later
  backbone version drops them if they are added.
- Mangrove homonyms are fixed to the plant family: Aegialitis
  (Plumbaginaceae), Osbornia (Myrtaceae) and Sonneratia (Lythraceae).
- Extinct is not used as a filter. GBIF leaves the flag blank for most
  living algae and octocorals, so filtering on it would drop them.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import http.client
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


BACKBONE_DATASET_KEY = "d7dddbf4-2cf0-4f39-9b2a-bb099caae36c"
API_ROOT = "https://api.gbif.org/v1"
USER_AGENT = "marineForests-gbif-taxa/1.0 (taxonomy table; research)"
ROOT = Path(__file__).resolve().parent.parent

SPECIES_FIELDS = [
    "group",
    "family",
    "family_key",
    "genus",
    "genus_key",
    "species",
    "taxon_key",
    "scientific_name",
    "authorship",
    "taxonomic_status",
    "extinct",
    "class",
    "class_key",
    "order",
    "order_key",
    "kingdom",
    "kingdom_key",
    "phylum",
    "phylum_key",
    "source_taxon",
    "source_taxon_key",
]

TAXA_FIELDS = [
    "group",
    "role",
    "query_name",
    "query_rank",
    "gbif_taxon_key",
    "scientific_name",
    "canonical_name",
    "gbif_rank",
    "taxonomic_status",
    "kingdom",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "accepted_taxon_key",
    "accepted_scientific_name",
    "species_in_table",
    "species_excluded",
    "excluded_examples",
    "note",
    "retrieved_at",
]

# Editable checklist. rank is the rank of the name as requested.
# kingdom, phylum, order and family disambiguate homonyms.
GROUPS = [
    {
        "group": "Seagrasses",
        "include": [
            {"name": "Posidoniaceae", "rank": "FAMILY", "kingdom": "Plantae"},
            {"name": "Cymodoceaceae", "rank": "FAMILY", "kingdom": "Plantae"},
            {"name": "Zosteraceae", "rank": "FAMILY", "kingdom": "Plantae"},
            {
                "name": "Thalassia",
                "rank": "GENUS",
                "kingdom": "Plantae",
                "family": "Hydrocharitaceae",
                "note": "Marine genus of Hydrocharitaceae. The animal genus Thalassia is ignored.",
            },
            {
                "name": "Enhalus",
                "rank": "GENUS",
                "kingdom": "Plantae",
                "family": "Hydrocharitaceae",
            },
            {
                "name": "Halophila",
                "rank": "GENUS",
                "kingdom": "Plantae",
                "family": "Hydrocharitaceae",
                "note": "Marine genus of Hydrocharitaceae. The animal genus Halophila is ignored.",
            },
            {"name": "Ruppiaceae", "rank": "FAMILY", "kingdom": "Plantae"},
            {
                "name": "Althenia",
                "rank": "GENUS",
                "kingdom": "Plantae",
                "family": "Potamogetonaceae",
                "note": "Includes species formerly placed in Lepilaena.",
            },
            {
                "name": "Lepilaena",
                "rank": "GENUS",
                "kingdom": "Plantae",
                "family": "Potamogetonaceae",
                "note": "Former genus included with Althenia. One GBIF usage is a synonym of Althenia; a doubtful usage still contains Lepilaena australis. Both are searched.",
            },
        ],
        "exclude": [],
    },
    {
        "group": "Porifera",
        "include": [
            {"name": "Porifera", "rank": "PHYLUM", "kingdom": "Animalia"},
        ],
        "exclude": [
            {
                "name": "Spongillida",
                "rank": "ORDER",
                "kingdom": "Animalia",
                "phylum": "Porifera",
                "note": "Freshwater sponges.",
            },
        ],
    },
    {
        "group": "Rhodophyta",
        "include": [
            {"name": "Rhodophyta", "rank": "PHYLUM", "kingdom": "Plantae"},
        ],
        "exclude": [
            {"name": "Cyanidiophyceae", "rank": "CLASS", "kingdom": "Plantae", "phylum": "Rhodophyta"},
            {"name": "Porphyridiophyceae", "rank": "CLASS", "kingdom": "Plantae", "phylum": "Rhodophyta"},
            {"name": "Rhodellophyceae", "rank": "CLASS", "kingdom": "Plantae", "phylum": "Rhodophyta"},
            {
                "name": "Batrachospermales",
                "rank": "ORDER",
                "kingdom": "Plantae",
                "phylum": "Rhodophyta",
                "note": "Freshwater red algae.",
            },
            {
                "name": "Hildenbrandia rivularis",
                "rank": "SPECIES",
                "kingdom": "Plantae",
                "phylum": "Rhodophyta",
                "note": "Freshwater species. Other Hildenbrandia species are kept.",
            },
            {
                "name": "Pneophyllum cetinaensis",
                "rank": "SPECIES",
                "kingdom": "Plantae",
                "phylum": "Rhodophyta",
                "note": "Freshwater species. Other Pneophyllum species are kept.",
            },
        ],
    },
    {
        "group": "Bryozoa",
        "include": [
            {"name": "Bryozoa", "rank": "PHYLUM", "kingdom": "Animalia"},
        ],
        "exclude": [
            {
                "name": "Phylactolaemata",
                "rank": "CLASS",
                "kingdom": "Animalia",
                "phylum": "Bryozoa",
                "note": "Freshwater bryozoans.",
            },
        ],
    },
    {
        "group": "Phaeophyceae",
        "include": [
            {"name": "Phaeophyceae", "rank": "CLASS", "kingdom": "Chromista"},
        ],
        "exclude": [
            {"name": "Bodanella", "rank": "GENUS", "kingdom": "Chromista", "phylum": "Ochrophyta"},
            {"name": "Heribaudiella", "rank": "GENUS", "kingdom": "Chromista", "phylum": "Ochrophyta"},
            {
                "name": "Pleurocladia lacustris",
                "rank": "SPECIES",
                "kingdom": "Chromista",
                "note": "Freshwater species. Other Pleurocladia species are kept.",
            },
            {
                "name": "Sphacelaria fluviatilis",
                "rank": "SPECIES",
                "kingdom": "Chromista",
                "note": "Freshwater species. Other Sphacelaria species are kept.",
            },
            {
                "name": "Sphacelaria lacustris",
                "rank": "SPECIES",
                "kingdom": "Chromista",
                "note": "Freshwater species. Other Sphacelaria species are kept.",
            },
        ],
    },
    {
        "group": "Green algae",
        "include": [
            {"name": "Ulvophyceae", "rank": "CLASS", "kingdom": "Plantae"},
            {"name": "Palmophyllaceae", "rank": "FAMILY", "kingdom": "Plantae"},
        ],
        "exclude": [
            {
                "name": "Ignatiales",
                "rank": "ORDER",
                "kingdom": "Plantae",
                "note": "Order absent from the GBIF backbone. Genera of the order are excluded individually.",
            },
            {"name": "Trentepohliales", "rank": "ORDER", "kingdom": "Plantae", "phylum": "Chlorophyta"},
            {
                "name": "Ignatiaceae",
                "rank": "FAMILY",
                "kingdom": "Plantae",
                "note": "Family of Ignatiales. GBIF places it in Ulvophyceae without an order.",
            },
            {
                "name": "Ignatius",
                "rank": "GENUS",
                "kingdom": "Plantae",
                "note": "Ignatiales genus. GBIF leaves it as a doubtful genus in Ulotrichales.",
            },
            {
                "name": "Pseudocharacium",
                "rank": "GENUS",
                "kingdom": "Plantae",
                "note": "Ignatiales genus. GBIF places it in Chlorophyceae, order Sphaeropleales, already outside Ulvophyceae.",
            },
            {
                "name": "Symbiochlorum",
                "rank": "GENUS",
                "kingdom": "Plantae",
                "note": "Ignatiales genus. GBIF leaves it as a doubtful genus in Ulvophyceae.",
            },
        ],
    },
    {
        "group": "Cnidaria",
        "include": [
            {"name": "Scleractinia", "rank": "ORDER", "kingdom": "Animalia", "phylum": "Cnidaria"},
            {"name": "Antipatharia", "rank": "ORDER", "kingdom": "Animalia", "phylum": "Cnidaria"},
            {
                "name": "Malacalcyonacea",
                "rank": "ORDER",
                "kingdom": "Animalia",
                "phylum": "Cnidaria",
                "note": "GBIF has no accepted taxon named Alcyonacea or Octocorallia. Malacalcyonacea is one of the two orders that replaced traditional Alcyonacea.",
            },
            {
                "name": "Scleralcyonacea",
                "rank": "ORDER",
                "kingdom": "Animalia",
                "phylum": "Cnidaria",
                "note": "Second order replacing traditional Alcyonacea. In GBIF it also contains former sea pens and Helioporidae, so together with Malacalcyonacea it covers Octocorallia.",
            },
            {
                "name": "Pennatulacea",
                "rank": "ORDER",
                "kingdom": "Animalia",
                "phylum": "Cnidaria",
                "note": "Residual order. Most sea-pen genera are already in Scleralcyonacea; this order is included so those leftover names are not dropped.",
            },
        ],
        "exclude": [],
    },
    {
        "group": "Mangroves",
        "include": [
            {"name": "Acrostichum aureum", "rank": "SPECIES", "kingdom": "Plantae", "family": "Pteridaceae"},
            {"name": "Acrostichum speciosum", "rank": "SPECIES", "kingdom": "Plantae", "family": "Pteridaceae"},
            {
                "name": "Aegialitis",
                "rank": "GENUS",
                "kingdom": "Plantae",
                "family": "Plumbaginaceae",
                "note": "Plant genus. The bird genus and the grass homonym are ignored.",
            },
            {"name": "Aegiceras", "rank": "GENUS", "kingdom": "Plantae", "family": "Primulaceae"},
            {"name": "Avicennia", "rank": "GENUS", "kingdom": "Plantae", "family": "Acanthaceae"},
            {"name": "Bruguiera", "rank": "GENUS", "kingdom": "Plantae", "family": "Rhizophoraceae"},
            {"name": "Camptostemon", "rank": "GENUS", "kingdom": "Plantae", "family": "Malvaceae"},
            {"name": "Ceriops", "rank": "GENUS", "kingdom": "Plantae", "family": "Rhizophoraceae"},
            {
                "name": "Excoecaria agallocha",
                "rank": "SPECIES",
                "kingdom": "Plantae",
                "family": "Euphorbiaceae",
                "note": "The only mangrove in Excoecaria. Other species of the genus are not included.",
            },
            {"name": "Kandelia", "rank": "GENUS", "kingdom": "Plantae", "family": "Rhizophoraceae"},
            {"name": "Laguncularia", "rank": "GENUS", "kingdom": "Plantae", "family": "Combretaceae"},
            {"name": "Lumnitzera", "rank": "GENUS", "kingdom": "Plantae", "family": "Combretaceae"},
            {"name": "Nypa fruticans", "rank": "SPECIES", "kingdom": "Plantae", "family": "Arecaceae"},
            {
                "name": "Osbornia",
                "rank": "GENUS",
                "kingdom": "Plantae",
                "family": "Myrtaceae",
                "note": "Plant genus. The insect genus Osbornia is ignored.",
            },
            {"name": "Pelliciera", "rank": "GENUS", "kingdom": "Plantae", "family": "Tetrameristaceae"},
            {"name": "Pemphis", "rank": "GENUS", "kingdom": "Plantae", "family": "Lythraceae"},
            {"name": "Rhizophora", "rank": "GENUS", "kingdom": "Plantae", "family": "Rhizophoraceae"},
            {"name": "Scyphiphora", "rank": "GENUS", "kingdom": "Plantae", "family": "Rubiaceae"},
            {
                "name": "Sonneratia",
                "rank": "GENUS",
                "kingdom": "Plantae",
                "family": "Lythraceae",
                "note": "Plant genus. The ammonite genus Sonneratia is ignored.",
            },
            {"name": "Xylocarpus", "rank": "GENUS", "kingdom": "Plantae", "family": "Meliaceae"},
        ],
        "exclude": [],
    },
]


class ResolveError(Exception):
    """A requested name could not be tied to one GBIF taxon."""


class GbifClient:
    def __init__(self) -> None:
        self._memory: dict[str, dict] = {}
        self._disk = ROOT / "data" / "gbif_cache"
        self._disk.mkdir(parents=True, exist_ok=True)

    def get(self, path: str, params: dict | None = None) -> dict:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{API_ROOT}{path}"
        if query:
            url = f"{url}?{query}"
        cached = self._memory.get(url)
        if cached is not None:
            return cached
        digest = hashlib.sha1(url.encode()).hexdigest()
        cache_path = self._disk / f"{digest}.json"
        if cache_path.exists():
            payload = json.loads(cache_path.read_text())
        else:
            payload = slim(self._request(url))
            cache_path.write_text(json.dumps(payload))
        if "/species/search" not in url:
            self._memory[url] = payload
        return payload

    def _request(self, url: str) -> dict:
        delay = 2.0
        last_error: Exception | None = None
        for attempt in range(8):
            request = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                last_error = error
                if error.code not in {429, 500, 502, 503, 504} or attempt == 7:
                    detail = error.read().decode("utf-8", errors="replace")[:500]
                    raise RuntimeError(f"GBIF request failed ({error.code}) for {url}: {detail}") from error
            except (
                urllib.error.URLError,
                TimeoutError,
                json.JSONDecodeError,
                http.client.IncompleteRead,
                ConnectionError,
            ) as error:
                last_error = error
                if attempt == 7:
                    raise RuntimeError(f"GBIF request failed for {url}: {error}") from error
            print(f"  retry {attempt + 1} after {type(last_error).__name__}", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 60)
        raise RuntimeError(f"GBIF request failed for {url}: {last_error}")


def norm(value: str) -> str:
    return " ".join(str(value).split()).casefold()


def status_of(record: dict) -> str:
    return str(record.get("taxonomicStatus") or record.get("status") or "").upper()


def is_synonym(record: dict) -> bool:
    return record.get("synonym") is True or status_of(record) == "SYNONYM"


def accepted_key_of(record: dict) -> int | None:
    for field in ("acceptedKey", "acceptedUsageKey"):
        if record.get(field):
            return int(record[field])
    for field in ("accepted", "acceptedUsage"):
        accepted = record.get(field)
        if isinstance(accepted, dict) and accepted.get("key"):
            return int(accepted["key"])
    return None


def canonical_of(record: dict, rank: str) -> str:
    if record.get("canonicalName"):
        return str(record["canonicalName"])
    scientific = str(record.get("scientificName") or "").replace("×", " ").replace("×", " ")
    parts = scientific.split()
    if not parts:
        return ""
    if rank == "SPECIES":
        return " ".join(parts[:2])
    return parts[0]


def resolve_query(client: GbifClient, query: dict) -> dict:
    """Return the GBIF usage for one checklist entry.

    Homonyms are removed with kingdom, phylum, order and family when those
    were set on the query. A synonym is kept, and its accepted taxon is
    stored alongside it.
    """
    rank = query["rank"].upper()
    params = {"name": query["name"], "verbose": "true", "rank": rank.lower()}
    for field in ("kingdom", "phylum"):
        if query.get(field):
            params[field] = query[field]
    payload = client.get("/species/match", params)
    rough = []
    if payload.get("usageKey"):
        rough.append(payload)
    rough.extend(payload.get("alternatives") or [])

    name_hits = []
    for candidate in rough:
        if not candidate.get("usageKey"):
            continue
        if str(candidate.get("rank") or "").upper() != rank:
            continue
        if norm(canonical_of(candidate, rank)) != norm(query["name"]):
            continue
        name_hits.append(candidate)

    hydrated = []
    seen_keys = set()
    for candidate in name_hits:
        key = int(candidate["usageKey"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        full = client.get(f"/species/{key}")
        if not fits_context(full, query):
            continue
        accepted = full
        if is_synonym(full):
            target = accepted_key_of(full)
            if target is None:
                raise ResolveError(f"{query['name']}: synonym {key} has no accepted taxon")
            accepted = client.get(f"/species/{target}")
        hydrated.append((full, accepted))

    if not hydrated:
        raise ResolveError(f"{query['name']} ({rank}): no GBIF backbone match for the requested kingdom and family")

    if not query.get("family"):
        families = {
            (accepted.get("family") or usage.get("family") or "")
            for usage, accepted in hydrated
            if accepted.get("family") or usage.get("family")
        }
        if len(families) > 1:
            details = ", ".join(sorted(families))
            raise ResolveError(f"{query['name']} ({rank}) matches more than one family: {details}")

    def preference(pair: tuple[dict, dict]) -> tuple[int, int]:
        usage, accepted = pair
        status = status_of(usage)
        if status == "ACCEPTED":
            rank_score = 0
        elif status == "SYNONYM":
            rank_score = 1
        elif status == "DOUBTFUL":
            rank_score = 2
        else:
            rank_score = 3
        return (rank_score, int(usage["key"]))

    usage, accepted = sorted(hydrated, key=preference)[0]
    keys = set()
    for matched, target in hydrated:
        keys.add(int(matched["key"]))
        keys.add(int(target["key"]))
    note = query.get("note") or ""
    extra_keys = sorted(keys - {int(usage["key"]), int(accepted["key"])})
    if extra_keys:
        extra_note = "Additional GBIF usages also searched: " + ", ".join(str(key) for key in extra_keys) + "."
        note = f"{note} {extra_note}".strip()
    return {
        "query_name": query["name"],
        "query_rank": rank,
        "note": note,
        "gbif_taxon_key": int(usage["key"]),
        "scientific_name": usage.get("scientificName") or "",
        "canonical_name": usage.get("canonicalName") or canonical_of(usage, rank),
        "gbif_rank": usage.get("rank") or "",
        "taxonomic_status": status_of(usage),
        "kingdom": usage.get("kingdom") or accepted.get("kingdom") or "",
        "phylum": usage.get("phylum") or accepted.get("phylum") or "",
        "class": usage.get("class") or accepted.get("class") or "",
        "order": usage.get("order") or accepted.get("order") or "",
        "family": usage.get("family") or accepted.get("family") or "",
        "genus": usage.get("genus") or accepted.get("genus") or "",
        "accepted_taxon_key": int(accepted["key"]),
        "accepted_scientific_name": accepted.get("scientificName") or "",
        "accepted_record": accepted,
        "keys": keys,
        "fetch_keys": sorted(keys),
        "found": True,
    }


def fits_context(record: dict, query: dict) -> bool:
    for field in ("kingdom", "phylum", "order", "family"):
        expected = query.get(field)
        observed = record.get(field)
        if expected and observed and observed != expected:
            return False
        if expected and not observed:
            return False
    return True


def unresolved(query: dict, message: str) -> dict:
    rank = query["rank"].upper()
    return {
        "query_name": query["name"],
        "query_rank": rank,
        "note": " ".join(part for part in (query.get("note") or "", message) if part),
        "gbif_taxon_key": "",
        "scientific_name": "",
        "canonical_name": "",
        "gbif_rank": "",
        "taxonomic_status": "",
        "kingdom": "",
        "phylum": "",
        "class": "",
        "order": "",
        "family": "",
        "genus": "",
        "accepted_taxon_key": "",
        "accepted_scientific_name": "",
        "accepted_record": None,
        "keys": set(),
        "fetch_keys": [],
        "found": False,
    }


BULKY_FIELDS = ("descriptions", "vernacularNames", "habitats", "threatStatuses", "publishedIn")
LOWER_RANKS = {"SPECIES", "SUBSPECIES", "VARIETY", "FORM", "SUBVARIETY", "INFRASPECIES"}


def slim(payload: dict) -> dict:
    records = payload.get("results")
    if isinstance(records, list):
        for record in records:
            if isinstance(record, dict):
                for field in BULKY_FIELDS:
                    record.pop(field, None)
    for field in BULKY_FIELDS:
        payload.pop(field, None)
    return payload


def accepted_species_count(client: GbifClient, taxon_key: int) -> int:
    payload = client.get(
        "/species/search",
        {
            "datasetKey": BACKBONE_DATASET_KEY,
            "higherTaxonKey": taxon_key,
            "rank": "SPECIES",
            "status": "ACCEPTED",
            "limit": 0,
        },
    )
    return int(payload.get("count") or 0)


def child_taxa(client: GbifClient, taxon_key: int) -> list[dict]:
    offset = 0
    rows: list[dict] = []
    while offset <= 200000:
        payload = client.get(f"/species/{taxon_key}/children", {"limit": 1000, "offset": offset})
        batch = payload.get("results") or []
        rows.extend(batch)
        if payload.get("endOfRecords") or len(batch) < 1000:
            return rows
        offset += 1000
    raise RuntimeError(f"Child listing for {taxon_key} exceeded 200000 rows")


def page_species(client: GbifClient, taxon_key: int, label: str, seen: set[int]) -> list[dict]:
    limit = 200
    offset = 0
    rows: list[dict] = []
    while offset <= 200000:
        payload = client.get(
            "/species/search",
            {
                "datasetKey": BACKBONE_DATASET_KEY,
                "higherTaxonKey": taxon_key,
                "rank": "SPECIES",
                "status": "ACCEPTED",
                "limit": limit,
                "offset": offset,
            },
        )
        batch = payload.get("results") or []
        for record in batch:
            if record.get("rank") != "SPECIES" or status_of(record) != "ACCEPTED":
                continue
            key = int(record["key"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(record)
        print(f"  {label}: {len(seen)} species kept (offset {offset})", flush=True)
        if payload.get("endOfRecords") or len(batch) < limit:
            return rows
        offset += limit
    raise RuntimeError(f"{label}: species paging exceeded 200000 rows")


def fetch_accepted_species(client: GbifClient, taxon_key: int, label: str, seen: set[int] | None = None) -> list[dict]:
    """Download accepted species, splitting large taxa so each response stays small."""
    if seen is None:
        seen = set()
    count = accepted_species_count(client, taxon_key)
    if count == 0:
        print(f"  {label}: 0 species", flush=True)
        return []
    if count > 2000:
        children = child_taxa(client, taxon_key)
        branches = []
        direct_species = []
        for child in children:
            status = status_of(child)
            rank = str(child.get("rank") or "").upper()
            if status not in {"ACCEPTED", "DOUBTFUL"}:
                continue
            if rank == "SPECIES" and status == "ACCEPTED":
                direct_species.append(child)
            elif rank not in LOWER_RANKS and child.get("numDescendants"):
                branches.append(child)
        if branches:
            print(f"  {label}: {count} species across {len(branches)} child taxa", flush=True)
            rows: list[dict] = []
            before = len(seen)
            for child in direct_species:
                key = int(child["key"])
                if key in seen:
                    continue
                full = client.get(f"/species/{key}")
                if full.get("rank") == "SPECIES" and status_of(full) == "ACCEPTED":
                    seen.add(key)
                    rows.append(full)
            for child in branches:
                name = child.get("canonicalName") or child.get("scientificName") or child["key"]
                rows.extend(fetch_accepted_species(client, int(child["key"]), f"{label} / {name}", seen))
            if len(seen) - before >= count:
                return rows
            print(
                f"  warning: {label} tree walk kept {len(seen) - before} of {count}; paging the remainder",
                flush=True,
            )
            rows.extend(page_species(client, taxon_key, label, seen))
            return rows
    return page_species(client, taxon_key, label, seen)


def species_row(group: str, source: dict, record: dict, source_key) -> dict:
    extinct = record.get("extinct")
    if not isinstance(extinct, bool):
        extinct = ""
    return {
        "group": group,
        "family": record.get("family") or "",
        "family_key": record.get("familyKey") or "",
        "genus": record.get("genus") or "",
        "genus_key": record.get("genusKey") or "",
        "species": record.get("canonicalName") or record.get("species") or "",
        "taxon_key": record.get("key") or "",
        "scientific_name": record.get("scientificName") or "",
        "authorship": record.get("authorship") or "",
        "taxonomic_status": status_of(record),
        "extinct": extinct,
        "class": record.get("class") or "",
        "class_key": record.get("classKey") or "",
        "order": record.get("order") or "",
        "order_key": record.get("orderKey") or "",
        "kingdom": record.get("kingdom") or "",
        "kingdom_key": record.get("kingdomKey") or "",
        "phylum": record.get("phylum") or "",
        "phylum_key": record.get("phylumKey") or "",
        "source_taxon": source["query_name"],
        "source_taxon_key": source_key,
    }


def excluded_by(row: dict, exclusion: dict) -> bool:
    if not exclusion["found"] and exclusion["query_rank"] != "SPECIES":
        compared = {
            "CLASS": row["class"],
            "ORDER": row["order"],
            "FAMILY": row["family"],
            "GENUS": row["genus"],
        }.get(exclusion["query_rank"])
        return bool(compared) and norm(compared) == norm(exclusion["query_name"])
    keys = exclusion["keys"]
    for field in (
        "taxon_key",
        "genus_key",
        "family_key",
        "order_key",
        "class_key",
        "phylum_key",
        "kingdom_key",
    ):
        value = row.get(field)
        if value != "" and int(value) in keys:
            return True
    compared = {
        "CLASS": row["class"],
        "ORDER": row["order"],
        "FAMILY": row["family"],
        "GENUS": row["genus"],
        "SPECIES": row["species"],
        "PHYLUM": row["phylum"],
        "KINGDOM": row["kingdom"],
    }.get(exclusion["query_rank"])
    return bool(compared) and norm(compared) == norm(exclusion["query_name"])


def merge_source(existing: dict, new: dict) -> None:
    names = [part for part in existing["source_taxon"].split(" | ") if part]
    if new["source_taxon"] not in names:
        names.append(new["source_taxon"])
    keys = [part for part in str(existing["source_taxon_key"]).split(" | ") if part]
    if str(new["source_taxon_key"]) not in keys:
        keys.append(str(new["source_taxon_key"]))
    existing["source_taxon"] = " | ".join(sorted(set(names)))
    existing["source_taxon_key"] = " | ".join(sorted(set(keys), key=lambda item: int(item)))


def collect_group(client: GbifClient, group: dict, includes: list[dict], excludes: list[dict]) -> tuple[list[dict], dict[str, int], dict[str, list[str]]]:
    grouped: dict[int, dict] = {}
    excluded_keys: dict[str, set[int]] = {item["query_name"]: set() for item in excludes}
    excluded_examples: dict[str, list[str]] = {item["query_name"]: [] for item in excludes}
    for source in includes:
        if not source["found"]:
            continue
        print(
            f"{group['group']} / {source['query_name']} [{', '.join(str(key) for key in source['fetch_keys'])}]",
            flush=True,
        )
        records = []
        if source["query_rank"] == "SPECIES":
            seen_species: set[int] = set()
            for key in source["fetch_keys"]:
                record = client.get(f"/species/{key}")
                if is_synonym(record):
                    target = accepted_key_of(record)
                    if target is None:
                        continue
                    record = client.get(f"/species/{target}")
                if record.get("rank") != "SPECIES" or status_of(record) != "ACCEPTED":
                    continue
                species_key = int(record["key"])
                if species_key in seen_species:
                    continue
                seen_species.add(species_key)
                records.append((record, species_key))
            if not records:
                raise ResolveError(
                    f"{source['query_name']} did not resolve to an accepted species "
                    f"({source['accepted_scientific_name']})"
                )
        else:
            for taxon_key in source["fetch_keys"]:
                fetched = fetch_accepted_species(client, int(taxon_key), f"{source['query_name']} {taxon_key}")
                records.extend((record, taxon_key) for record in fetched)
        for record, source_key in records:
            row = species_row(group["group"], source, record, source_key)
            reasons = [item["query_name"] for item in excludes if excluded_by(row, item)]
            if reasons:
                taxon_key = int(row["taxon_key"])
                for reason in reasons:
                    if taxon_key in excluded_keys[reason]:
                        continue
                    excluded_keys[reason].add(taxon_key)
                    if len(excluded_examples[reason]) < 8:
                        excluded_examples[reason].append(row["species"])
                continue
            taxon_key = int(row["taxon_key"])
            if taxon_key in grouped:
                merge_source(grouped[taxon_key], row)
            else:
                grouped[taxon_key] = row
    rows = sorted(grouped.values(), key=lambda row: (row["family"].casefold(), row["genus"].casefold(), row["species"].casefold(), int(row["taxon_key"])))
    excluded_counts = {name: len(keys) for name, keys in excluded_keys.items()}
    return rows, excluded_counts, excluded_examples


def taxa_row(group: str, role: str, resolved: dict, species_in_table: int, species_excluded: int, examples: list[str], retrieved_at: str) -> dict:
    return {
        "group": group,
        "role": role,
        "query_name": resolved["query_name"],
        "query_rank": resolved["query_rank"],
        "gbif_taxon_key": resolved["gbif_taxon_key"],
        "scientific_name": resolved["scientific_name"],
        "canonical_name": resolved["canonical_name"],
        "gbif_rank": resolved["gbif_rank"],
        "taxonomic_status": resolved["taxonomic_status"],
        "kingdom": resolved["kingdom"],
        "phylum": resolved["phylum"],
        "class": resolved["class"],
        "order": resolved["order"],
        "family": resolved["family"],
        "genus": resolved["genus"],
        "accepted_taxon_key": resolved["accepted_taxon_key"],
        "accepted_scientific_name": resolved["accepted_scientific_name"],
        "species_in_table": species_in_table,
        "species_excluded": species_excluded,
        "excluded_examples": " | ".join(examples),
        "note": resolved["note"],
        "retrieved_at": retrieved_at,
    }


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: format_cell(row.get(field)) for field in fieldnames})


def format_cell(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def species_set(rows: list[dict], group: str) -> set[str]:
    return {row["species"] for row in rows if row["group"] == group}


def validate(rows: list[dict]) -> list[str]:
    problems = []
    by_group: dict[str, list[dict]] = {}
    for row in rows:
        by_group.setdefault(row["group"], []).append(row)
        if not row["taxon_key"] or not row["species"]:
            problems.append(f"row without taxon key or species: {row}")
        if row["taxonomic_status"] != "ACCEPTED":
            problems.append(f"{row['species']} has status {row['taxonomic_status']}")

    for group, group_rows in by_group.items():
        keys = [int(row["taxon_key"]) for row in group_rows]
        if len(keys) != len(set(keys)):
            problems.append(f"{group} contains duplicate taxon keys")

    def forbidden(group: str, predicate, message: str) -> None:
        hits = [row["species"] for row in by_group.get(group, []) if predicate(row)]
        if hits:
            problems.append(f"{message}: {', '.join(hits[:8])}")

    forbidden("Porifera", lambda row: row["order"] == "Spongillida" or str(row["order_key"]) == "8391193", "Spongillida remained in Porifera")
    forbidden(
        "Rhodophyta",
        lambda row: row["class"] in {"Cyanidiophyceae", "Porphyridiophyceae", "Rhodellophyceae"}
        or row["order"] == "Batrachospermales"
        or row["species"] == "Hildenbrandia rivularis"
        or row["species"] == "Pneophyllum cetinaensis",
        "excluded red algae remained",
    )
    forbidden("Bryozoa", lambda row: row["class"] == "Phylactolaemata", "Phylactolaemata remained in Bryozoa")
    forbidden(
        "Phaeophyceae",
        lambda row: row["genus"] in {"Bodanella", "Heribaudiella"}
        or row["species"] in {"Pleurocladia lacustris", "Sphacelaria fluviatilis", "Sphacelaria lacustris"},
        "excluded brown algae remained",
    )
    forbidden(
        "Green algae",
        lambda row: row["order"] == "Trentepohliales"
        or row["order"] == "Ignatiales"
        or row["family"] == "Ignatiaceae"
        or row["genus"] in {"Ignatius", "Pseudocharacium", "Symbiochlorum"},
        "excluded green algae remained",
    )

    seagrass_families = {"Posidoniaceae", "Cymodoceaceae", "Zosteraceae", "Hydrocharitaceae", "Ruppiaceae", "Potamogetonaceae"}
    for row in by_group.get("Seagrasses", []):
        if row["family"] not in seagrass_families:
            problems.append(f"unexpected seagrass family {row['family']} for {row['species']}")
        if row["family"] == "Hydrocharitaceae" and row["genus"] not in {"Thalassia", "Enhalus", "Halophila"}:
            problems.append(f"unexpected Hydrocharitaceae genus {row['genus']}")
        if row["family"] == "Potamogetonaceae" and row["genus"] not in {"Althenia", "Lepilaena"}:
            problems.append(f"unexpected Potamogetonaceae genus {row['genus']}")

    mangrove_species = species_set(rows, "Mangroves")
    excoecaria = {name for name in mangrove_species if name.startswith("Excoecaria ")}
    if excoecaria != {"Excoecaria agallocha"}:
        problems.append(f"Excoecaria species were {sorted(excoecaria)}")
    nypa = {name for name in mangrove_species if name.startswith("Nypa ")}
    if nypa != {"Nypa fruticans"}:
        problems.append(f"Nypa species were {sorted(nypa)}")
    acrostichum = {name for name in mangrove_species if name.startswith("Acrostichum ")}
    if not acrostichum <= {"Acrostichum aureum", "Acrostichum speciosum"} or len(acrostichum) != 2:
        problems.append(f"Acrostichum species were {sorted(acrostichum)}")

    required = {
        "Seagrasses": ["Posidonia oceanica", "Zostera marina", "Enhalus acoroides", "Halophila ovalis", "Thalassia testudinum"],
        "Mangroves": ["Avicennia marina", "Rhizophora mangle", "Excoecaria agallocha", "Nypa fruticans", "Acrostichum aureum"],
        "Green algae": [],
        "Cnidaria": [],
    }
    for group, names in required.items():
        present = species_set(rows, group)
        for name in names:
            if name not in present:
                problems.append(f"{group} is missing {name}")

    cnidaria_orders = {row["order"] for row in by_group.get("Cnidaria", []) if row["order"]}
    allowed_orders = {"Scleractinia", "Antipatharia", "Malacalcyonacea", "Scleralcyonacea", "Pennatulacea"}
    unexpected_orders = cnidaria_orders - allowed_orders
    if unexpected_orders:
        problems.append(f"unexpected cnidarian orders: {sorted(unexpected_orders)}")
    for order in ("Scleractinia", "Antipatharia", "Malacalcyonacea", "Scleralcyonacea"):
        if order not in cnidaria_orders:
            problems.append(f"Cnidaria is missing order {order}")
    if not any(row["genus"] == "Pennatula" for row in by_group.get("Cnidaria", [])):
        problems.append("Cnidaria is missing Pennatula, so sea pens were not recovered inside Scleralcyonacea")
    if not any(row["genus"] == "Ulva" for row in by_group.get("Green algae", [])):
        problems.append("Green algae is missing genus Ulva")
    if not any(row["family"] == "Palmophyllaceae" for row in by_group.get("Green algae", [])):
        problems.append("Green algae is missing Palmophyllaceae")
    if len(by_group.get("Porifera", [])) < 1000:
        problems.append("Porifera species count is unexpectedly small")
    return problems


def print_summary(rows: list[dict], taxa_rows: list[dict]) -> None:
    print("\nSpecies in the table", flush=True)
    for group in [item["group"] for item in GROUPS]:
        group_rows = [row for row in rows if row["group"] == group]
        extinct = sum(row["extinct"] is True for row in group_rows)
        living = sum(row["extinct"] is False for row in group_rows)
        blank_flag = sum(row["extinct"] == "" for row in group_rows)
        families = len({row["family"] for row in group_rows if row["family"]})
        missing_family = sum(not row["family"] for row in group_rows)
        print(
            f"  {group}: {len(group_rows)} species, {families} families, "
            f"extinct flag true {extinct}, false {living}, blank {blank_flag}, "
            f"without family {missing_family}",
            flush=True,
        )
    print("\nGreen-algal orders kept", flush=True)
    orders: dict[str, int] = {}
    for row in rows:
        if row["group"] == "Green algae":
            orders[row["order"] or "(no order)"] = orders.get(row["order"] or "(no order)", 0) + 1
    for order, count in sorted(orders.items(), key=lambda item: (-item[1], item[0])):
        print(f"  {order}: {count}", flush=True)
    missing = [row for row in taxa_rows if row["role"] == "exclude" and row["gbif_taxon_key"] == ""]
    if missing:
        print("\nExclusion names absent from the GBIF backbone", flush=True)
        for row in missing:
            print(f"  {row['group']}: {row['query_name']}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download GBIF taxon keys and species for marine-forest groups.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data",
        help="Directory for the CSV files. Defaults to data/ in the repository.",
    )
    parser.add_argument(
        "--resolve-only",
        action="store_true",
        help="Resolve taxon keys and write the taxa table without downloading species.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    retrieved_at = time.strftime("%Y-%m-%d", time.gmtime())
    client = GbifClient()
    include_errors = []
    resolved_groups = []
    for group in GROUPS:
        includes = []
        excludes = []
        for query in group["include"]:
            try:
                includes.append(resolve_query(client, query))
            except ResolveError as error:
                include_errors.append(f"{group['group']}: {error}")
        for query in group["exclude"]:
            try:
                excludes.append(resolve_query(client, query))
            except ResolveError as error:
                print(f"warning: {group['group']} exclusion not resolved: {error}", flush=True)
                excludes.append(unresolved(query, "Not found in the GBIF backbone."))
        resolved_groups.append((group, includes, excludes))

    if include_errors:
        for message in include_errors:
            print(f"error: {message}", file=sys.stderr)
        return 1

    output_dir = args.output_dir
    taxa_path = output_dir / "gbif_marine_forest_taxa.csv"
    species_path = output_dir / "gbif_marine_forest_species.csv"

    if args.resolve_only:
        taxa_rows = []
        for group, includes, excludes in resolved_groups:
            for role, items in (("include", includes), ("exclude", excludes)):
                for item in items:
                    taxa_rows.append(taxa_row(group["group"], role, item, "", "", [], retrieved_at))
        write_csv(taxa_path, TAXA_FIELDS, taxa_rows)
        print(f"Wrote {taxa_path}", flush=True)
        return 0

    species_rows = []
    taxa_rows = []
    for group, includes, excludes in resolved_groups:
        rows, excluded_counts, examples = collect_group(client, group, includes, excludes)
        species_rows.extend(rows)
        for item in includes:
            in_table = sum(item["query_name"] in row["source_taxon"].split(" | ") for row in rows)
            taxa_rows.append(taxa_row(group["group"], "include", item, in_table, "", [], retrieved_at))
        for item in excludes:
            taxa_rows.append(
                taxa_row(
                    group["group"],
                    "exclude",
                    item,
                    "",
                    excluded_counts.get(item["query_name"], 0),
                    examples.get(item["query_name"], []),
                    retrieved_at,
                )
            )

    problems = validate(species_rows)
    write_csv(species_path, SPECIES_FIELDS, species_rows)
    write_csv(taxa_path, TAXA_FIELDS, taxa_rows)
    print_summary(species_rows, taxa_rows)
    print(f"\nWrote {len(species_rows)} species to {species_path}", flush=True)
    print(f"Wrote {len(taxa_rows)} taxon rows to {taxa_path}", flush=True)
    if problems:
        print("\nValidation failed:", flush=True)
        for problem in problems:
            print(f"  {problem}", flush=True)
        return 1
    print("\nValidation passed.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
