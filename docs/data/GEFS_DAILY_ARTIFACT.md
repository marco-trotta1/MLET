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

## Immutable generation and atomic pointer rule

For a successful import, `materialize_gefs_daily_artifact(artifact, pointer)`
creates a content-addressed, generation-specific directory below
`pointer.parent/data/cache/gefs-daily-artifacts/`. That directory contains
only these immutable members:

- `canonical-artifact.json`: the exact UTF-8 bytes passed to the JSON parser;
- `weather_members.jsonl`: the validated canonical normalized rows; and
- `receipt.json`: provenance and the raw/normalized hashes.

The source receipt records the parsed-artifact `raw_sha256`, the upstream GRIB
hash, normalized JSONL hash, artifact schema/type, upstream URI, issue time,
Idaho bounding box, variable list, transform identifier, and generation ID.

The `pointer` argument is a stable symlink to one complete generation directory;
it is **not** a normalized JSONL file. Consumers must call
`resolve_gefs_daily_artifact(pointer)` and read the returned raw, normalized,
and receipt paths together. There are no mutable normalized-file and receipt
sidecars at the pointer location.

When the cache hierarchy is new, the importer creates `data/`, `cache/`, and
`gefs-daily-artifacts/` one level at a time.  For each new level it fsyncs the
new directory and then its parent before moving to the next level.  It writes
and fsyncs all three staged members, changes each member to mode `0444`, and
fsyncs that member again after the final mode change.  It then changes the
staged generation directory to mode `0555`, fsyncs that directory, and
atomically renames the directory into the cache.  Only then does it atomically
replace the single pointer and fsync its parent.
Thus, an interruption before pointer replacement leaves the previous complete
generation visible; an interruption after replacement selects the new complete
generation. A newly completed but unpointed generation may remain in the cache
after an interrupted publish, but it is never a visible mixed artifact set.

This relies on the POSIX/filesystem guarantee that `rename`/`replace` is atomic
when source and destination are on the same filesystem and directory fsync is
honored by the deployment filesystem. MLET stages each replacement beside its
destination to meet the same-filesystem condition. The importer rejects
symlinked pointer parents, cache roots, generation directories, and artifact
members before writing or resolving them; the pointer target is restricted to
this cache layout.

## Required future decoder evidence

Before enabling any live path, add all of the following in one reviewed change:

1. a dependency-pinned GRIB decoder and deterministic selection/aggregation
   implementation;
2. an archived public GEFS GRIB test artifact with immutable URI and checksum;
3. an end-to-end test that validates the source issue, message selection,
   units, daily aggregation, and this artifact schema; and
4. a documented scientific and operational release decision.
