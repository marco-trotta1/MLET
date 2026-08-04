# AgriMet station registry snapshot

## What this snapshot contains

`data/outlook/agrimet_station_registry.json` records the public USBR station
registry downloaded on 2026-08-01 UTC. It contains 265 stations, including 52
stations in Idaho.

The snapshot records current coordinates, elevation when the published unit is
known, installation text, station homepage, responsibility, and source hashes.
The JSON registry is the primary source. The CSV source contains 179 station
IDs and is retained as a cross-check. The current CSV is not a complete mirror
of the JSON registry.

## Source receipt

| Source | URI | SHA-256 |
|---|---|---|
| JSON station registry | <https://www.usbr.gov/pn/agrimet/agrimetmap/usbr_map.json> | `97c5d235317821b2ebb4679e67ca3bbf29268688798eade8479c77d8667832e0` |
| CSV station registry | <https://www.usbr.gov/pn/agrimet/location.csv> | `ab4bdbdfd169a5bf7d44a7627017fe5ea8d6dcc2f5aee54b519f6d362d36b279` |
| AgriMet news archive | <https://www.usbr.gov/pn/agrimet/news.html> | `a43822118c975a44cb521ff3a93bcbe73ce6d5e4325a9859fae9a93c05598743` |

The normalized registry SHA-256 is
`ae5f85f719a057276bf9549d2b4f69fd8a570f73ab700216d435e1c7639cb10b`.

Repeat the download with:

```bash
python3 scripts/acquire_agrimet_station_registry.py \
  --destination data/outlook/agrimet_station_registry.json
```

The script refuses to overwrite an existing snapshot. It records a new
retrieval time and source hashes for each run.

## Historical-location boundary

Every station in this snapshot has `historical_location_status` set to
`current_snapshot_only`. The snapshot does not prove that the current
coordinates apply to an earlier target date.

Fourteen Idaho stations have no installation date in the public JSON registry:

`ACKI`, `EBRI`, `HAMI`, `ICHI`, `IFAI`, `IGRI`, `LOFI`, `MDKI`, `OWEI`, `ROBI`,
`RRCI`, `SUGI`, `TABI`, and `TERI`.

The ETo target path must continue to use
`mlet.agrimet.station-history-registry` for historical coordinates. Do not
convert this current snapshot into a historical registry. USBR station history
or relocation records are still required before targets for the 2013-2019
window can be treated as fully location-verified.

The news archive is retained as an evidence source for documented equipment
and relocation notices. It is not a complete station movement ledger.

## Exact follow-up request

Send this request to `AgriMet@usbr.gov`:

> Please provide the historical location record for the Idaho AgriMet stations
> used in a 2013-01-01 through 2019-12-31 ETo hindcast. For each station, please
> provide every coordinate and elevation segment, its valid start and end date,
> installation or retirement date, and any relocation notice or station-history
> revision. Please identify the source revision or file for each segment.

The requested record must support one verified coordinate for every station-day
used by the target adapter. Until USBR supplies that record, the adapter must
not treat the current snapshot as historical evidence.
