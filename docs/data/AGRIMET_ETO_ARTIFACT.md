# AgriMet ETos target artifact, version 2

## Purpose

Use this artifact for the ETo-only hindcast target. Do not use it for ETc,
ETa, soil-water, or irrigation claims.

USBR AgriMet publishes daily `ETos`. It defines `ETos` as ASCE-EWRI grass
reference evapotranspiration in inches per day. MLET converts this published
value to millimeters with the exact factor `25.4`.

The target is independent of the MLET GEFS forecast input. Do not calculate
the target with the forecast-weather path.

## Required source record

Give each input row these fields:

```json
{
  "station_id": "BOIS",
  "latitude": 43.6,
  "longitude": -116.2,
  "elevation_m": 824.0,
  "valid_date": "2019-07-01",
  "etos_in": 0.2,
  "available_at": "2019-07-02T12:00:00Z",
  "uri": "https://www.usbr.gov/pn/agrimet/...",
  "source_version": "recorded-source-version"
}
```

`available_at` must be later than the local Idaho end of `valid_date`. Do not
replace a missing value with zero. Do not interpolate a missing station day.

The official archive response uses `BEGIN DATA` and `END DATA` records. Its
header is `DATE, STATION ETOS`. `m`, `998877`, and `NO RECORD` are missing
markers. The parser records each such date as an exclusion. It does not make a
target row.
Use the explicit archive retrieval time as `available_at` for the archived
target receipt.

The schema-v2 target artifact may include an `exclusions` list. Each entry has
the station target identity, the excluded valid date, and the reason. An
exclusion is never scored as a target.

```json
{
  "exclusions": [
    {
      "target_id": "agrimet:BOII",
      "valid_date": "2019-07-03",
      "reason": "published_missing_etos"
    }
  ]
}
```

## Historical station location registry

The current public station snapshot is recorded in
[`AGRIMET_STATION_REGISTRY.md`](AGRIMET_STATION_REGISTRY.md). It is a source
inventory only. It is not a historical location registry.

Use `mlet.agrimet.station-history-registry` version 1 before matching a target
station to a GEFS grid. The registry must give one location segment for each
station-day that MLET uses. Do not use current station metadata as evidence for
an earlier day.

```json
{
  "schema_version": 1,
  "kind": "mlet.agrimet.station-history-registry",
  "source_snapshot": {
    "uri": "https://.../station-metadata.json",
    "sha256": "64 lowercase hex characters",
    "retrieved_at": "YYYY-MM-DDTHH:MM:SSZ"
  },
  "stations": [
    {
      "station_id": "BOII",
      "segments": [
        {
          "valid_from": "2013-01-01",
          "valid_to": null,
          "latitude": 43.6,
          "longitude": -116.2,
          "elevation_m": 824.0,
          "metadata_uri": "https://.../station-history-record",
          "metadata_sha256": "64 lowercase hex characters",
          "source_version": "station-history-revision"
        }
      ]
    }
  ]
}
```

Segments use inclusive dates. Segments for one station must not overlap. A gap
is allowed, but MLET rejects a target date in that gap. Each segment needs its
own metadata URI and checksum. The current USBR location GeoJSON is a source
snapshot. It is not enough to prove a historical segment without a dated
station-history record.

## Archived target acquisition

Use one requested interval for each verified station-location segment. The
acquisition command requires an existing empty raw directory. It writes every
raw response once. It also writes parsed source rows, missing-day exclusions,
and a retrieval receipt.

```bash
python3 scripts/acquire_agrimet_etos.py \
  --station-history archive/agrimet-station-history.json \
  --station BOII \
  --first 2013-01-01 --last 2019-12-31 \
  --raw-root archive/agrimet-raw \
  --rows archive/agrimet-raw-rows.json \
  --exclusions archive/agrimet-exclusions.json \
  --receipt archive/agrimet-retrieval-receipt.json
```

The command derives each archive request URL from the station ID and interval.
It records the raw response SHA-256 and byte count. It labels each target row
with a SHA-256 source version. It rejects a response row outside the requested
interval. It does not fill missing ETos values.

## Requirements before bulk import

1. Record the exact archive request URL and retrieval time.
2. Record the station metadata revision and station location.
3. Keep the source unit as `etos_in` in the raw record.
4. Store the raw byte checksum and the normalized artifact checksum.
5. Record an exclusion reason for each station-day that is not used.

## Source references

- [USBR AgriMet Historical Archive Weather Data Access](https://www.usbr.gov/pn/agrimet/webarcread.html)
- [USBR AgriMet parameter codes](https://www.usbr.gov/pn/agrimet/aginfo/archive_pcodes.html)
- [USBR AgriMet ASCE-EWRI explanation](https://www.usbr.gov/pn/agrimet/chartkey.html)
