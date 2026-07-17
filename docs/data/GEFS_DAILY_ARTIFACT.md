# Canonical GEFS daily artifact, version 1

## Status and boundary

MLET does **not** fetch or decode live NOAA GEFS GRIB files. The public
`fetch_gefs()` function intentionally raises before any network request. A
future operational decoder is out of scope until it is version-pinned,
independently verified against an archived GRIB file, and its daily spatial and
unit transformations are documented.

Until then, `materialize_gefs_daily_artifact()` imports this versioned
canonical artifact only. This keeps the weather/ETo core independent of a GRIB
decoder and makes an archive replay byte-auditable. Test artifacts are
explicitly non-scientific software fixtures; they are not NOAA data or forecast
skill evidence.

## Required JSON shape

The input is UTF-8 JSON with these required top-level fields:

```json
{
  "artifact_type": "mlet.gefs.daily-artifact",
  "schema_version": 1,
  "provenance": {
    "upstream_uri": "https://.../archived-gefs.grib2",
    "upstream_raw_sha256": "64 lowercase hex characters",
    "source_issue_at": "YYYY-MM-DDTHH:MM:SSZ",
    "idaho_bbox": [west, south, east, north],
    "variables": [
      "precip_mm", "solar_mj_m2_day", "tmax_c", "tmin_c",
      "vapor_pressure_kpa", "wind_m_s"
    ],
    "transform": {
      "name": "noaa-gefs-grib-to-daily-asce-input",
      "version": "1"
    }
  },
  "normalized_sha256": "64 lowercase hex characters",
  "rows": []
}
```

`upstream_raw_sha256` identifies the immutable upstream GRIB bytes. `rows`
contain the project’s canonical daily units and must include the six variables,
grid location/elevation, member ID, and valid date. The transform name and
version identify the exact external process that selected GRIB messages,
converted units, and aggregated daily Idaho weather-grid inputs. The bounding
box must be inside Idaho and every resulting row must be inside that declared
box.

`normalized_sha256` is the SHA-256 of canonical normalized JSONL: weather rows
are sorted by `(grid_id, member_id, valid_date)`, each object has sorted compact
JSON keys, and each line ends with a newline. The importer recomputes it and
rejects any mismatch.

## Receipt and transaction rule

For a successful import, the raw cache is the exact artifact bytes passed to
the JSON parser. The source receipt records the parsed-artifact `raw_sha256`,
the upstream GRIB hash, normalized JSONL hash, artifact schema/type, upstream
URI, issue time, Idaho bounding box, variable list, and transform identifier.

The cache, normalized JSONL, and receipt are staged before target changes. The
receipt is published last. If any replacement fails, targets written in that
attempt are restored or removed; a partial normalized file or new completion
receipt must never represent a failed acquisition.

## Required future decoder evidence

Before enabling any live path, add all of the following in one reviewed change:

1. a dependency-pinned GRIB decoder and deterministic selection/aggregation
   implementation;
2. an archived public GEFS GRIB test artifact with immutable URI and checksum;
3. an end-to-end test that validates the source issue, message selection,
   units, daily aggregation, and this artifact schema; and
4. a documented scientific and operational release decision.
