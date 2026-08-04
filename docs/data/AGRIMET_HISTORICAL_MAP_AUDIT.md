# AgriMet historical map audit

## Scope

This audit compares five archived USBR AgriMet map snapshots. It supports
station identity and coordinate checks for the 2015-2019 target window.

| Archived capture | Idaho stations | SHA-256 |
| --- | ---: | --- |
| 2015-06-17 | 45 | `35e2fa31145f13bd60bdcbd117127fc0a8767f832c6798db7cd2a0c3cc2a6018` |
| 2016-09-28 | 48 | `9f9ec38bed405cb6588a4b79c25ac3c02816f4e147818a63d3dade0eba855833` |
| 2017-03-22 | 48 | `391af50e23f59c3c00a0b33381b02a4cdf10c1aaa0df2986bd3ac89ca030e0e` |
| 2018-12-28 | 48 | `016b565d70e5280158b6ca9bf161bd83d13850f9d4ba7e4d47d3565a6b074cf6` |
| 2020-11-05 | 51 | `867971f40aef8f15868f1b8fe5f8effdcf251a2fc1f2205db3f9be006894c6dd` |

The CDX response receipt has SHA-256
`b3de54d4db3b279b8087ca869532971247dfe54fa9c8eb1bf20730b39f8c2bd4`.
The raw responses are stored under the external MLET Evidence root.

## Findings

- Forty-five stations appear in the 2015 snapshot.
- Three more stations, EBRI, IGRI, and LOFI, appear in 2016.
- Forty-eight stations appear in every snapshot from 2016 through 2018.
- All 48 stations retain the same archived map coordinates in every snapshot.
- IYCI, MREI, and SLMI appear only in the 2020 snapshot.
- DRTI is in the current Idaho registry but is absent from these snapshots.

The 48 stable map identities are candidate target stations for dates after the
first dated map observation. The map data do not provide a complete relocation
ledger. Current elevation values are not historical evidence. Bulk target
import therefore remains gated until each candidate has a checksum-bound
historical station page or an equivalent USBR location record.

BOII meets the stronger feasibility requirement. Its station page records
coordinates and elevation, and five dated map snapshots bracket the target
window. The committed records are
`data/outlook/agrimet_station_history_boii.json` and
`data/outlook/agrimet_station_history_boii_evidence.json`.

## Acquired eligible records

The 19 stations with dated station pages now have published ETos records for
2015-06-17 through 2019-12-31. The archive contains 31,406 source rows and
115 explicit missing-value exclusions. The raw responses contain 807,120
bytes across 19 files. The compact checksum summary is
`data/outlook/agrimet_historical_acquisition.json`.

The nearest-grid mapping uses the verified 2019-07-03 GEFS grid. All 19
stations are within the 50 km limit. The largest distance is 25.474539 km.

The first acquisition attempt failed on the official `NO RECORD` marker. The
parser now records that marker as a published missing-value exclusion. The
failed partial response remains outside the completed receipt root.

## Target artifact generation

The target builder creates one schema-v2 target artifact per station, issue,
season, and frozen spatial fold. This keeps each target receipt bound to one
USBR request URI and source version.

The baseline is the arithmetic mean for the same station and day of year from
years before the issue year. It excludes the evaluated year and future years.
The case holdout applies to the forecast evaluation. It does not remove the
target station's own historical observations from this station baseline.

The generator is `scripts/build_eto_target_index.py`. It writes a target index,
case artifacts, and a receipt that binds the source row, exclusion, mapping,
and baseline inputs.
