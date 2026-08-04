# Canonical GEFS daily artifact, version 2

## Status and boundary

MLET does **not** fetch operational NOAA GEFS data through the public
`fetch_gefs()` path. That function intentionally raises before any network
request. The separate reforecast acquisition runner downloads only the fixed
public GEFSv12 archive. The reforecast decoder reads local, checksum-pinned
GRIB files with eccodes. This does not enable an operational forecast path.

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
  "schema_version": 2,
  "provenance": {
    "upstream_uri": "https://.../noaa-gefs-v12-collection",
    "raw_object_receipt": {
      "uri": "file:///.../gefs-retrieval-receipt.json",
      "sha256": "64 lowercase hex characters",
      "object_count": 187
    },
    "source_issue_at": "YYYY-MM-DDTHH:MM:SSZ",
    "daily_aggregation_timezone": "America/Boise",
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

`raw_object_receipt` identifies the immutable receipt for all raw GRIB bytes
used for one issue. The receipt records the source URI, local path, byte count,
SHA-256, response version fields, and retrieval time for every planned object.
Its hash is not a substitute for a raw-file hash. `rows` contain the project’s
canonical daily units and must include the six variables, grid
location/elevation, member ID, and valid date. The transform name and version
identify the exact external process that selected GRIB messages, converted
units, and aggregated daily Idaho weather-grid inputs. The bounding box must
be inside Idaho and every resulting row must be inside that declared box.

Version 1 remains readable only for software fixtures and a single archived raw
object. A manuscript reforecast artifact must use version 2 and
`raw_object_receipt`.

`daily_aggregation_timezone` freezes the meaning of every row's
`valid_date`: it must be exactly `America/Boise`, including the IANA MST/MDT
transition rule. The importer rejects a UTC-day or unspecified aggregation
instead of shifting dates from the source issue timestamp.

## GEFSv12 reforecast source contract

The manuscript protocol uses the NOAA GEFSv12 weekly reforecast archive. The
archive stores daily five-member runs and one weekly 11-member run. The weekly
run extends to lead day 35. Public object listings show that the weekly run is
Wednesday 00Z, with `Days:1-10` and `Days:10-35` segments. The manuscript
schedule uses every Wednesday 00Z issue from 2013-01-02 through 2019-12-25,
inclusive. This gives 365 issues. The function
`weekly_wednesday_00z_issues()` derives this schedule before any data are
downloaded or scored.

The full weekly layout is source-verified. A 2019-07-03 survey found all 187
planned objects available: 11 members, 2 segments, 9 components, and
8,289,206,079 advertised bytes. The survey summary is in
`data/outlook/gefs_reforecast_20190703_availability.json`. It is an
availability result, not a downloaded or decoded hindcast.

The raw archive stores GRIB fields separately. A decoder must select the
documented 2 m maximum and minimum temperature, 2 m humidity, surface pressure,
10 m wind components, downwelling shortwave radiation, and precipitation. It
must aggregate one `America/Boise` day before calling
`normalize_gefs_reforecast_daily_rows()`. Each field value ends a three-hour
or six-hour interval. Temperature extrema and precipitation use six-hour
intervals. Humidity, pressure, wind, and shortwave radiation use three-hour
intervals in the first segment. Both segments contain complete six-hour
shortwave averages. The long-range segment also stores humidity, pressure, and
wind as six-hour point samples. The decoder expands each six-hour value into
two equal three-hour canonical steps before aggregation. Assign every interval
to the Idaho date that contains its midpoint.
This assigns an interval that ends at local midnight to the preceding day. A
complete output day contains four six-hour values or eight three-hour values,
as required by the component.

Specific humidity, surface pressure, and the two wind components are
three-hour point samples. Their GRIB messages have equal `startStep` and
`endStep`. The decoder assigns each point sample to the preceding three-hour
interval. Shortwave radiation uses the complete six-hour average messages in
both segments. Long-range humidity, pressure, and wind messages are six-hour
point samples. The decoder maps each point to the preceding six-hour interval
and expands it into two equal three-hour steps. It preserves the shortwave
energy when it expands the radiation value. Temperature extrema and
precipitation use six-hour intervals.

Select 2 m messages for maximum temperature, minimum temperature, and specific
humidity. Select 10 m messages for both wind components. The wind GRIB files
also contain 100 m messages. Do not use them.

The acquisition plan is fixed by
`gefs_reforecast_object_uri()`. For each scheduled issue, request the two
segments `Days:1-10` and `Days:10-35` for the eight time-varying components.
Request `elevation_m` only from `Days:1-10`; it is a static surface field. Use
exactly these 11 members: `c00`,
`p01` through `p10`. The function validates a UTC 00Z issue, member,
component, and segment before constructing the public URL. It must be used to
build the reforecast catalog. Do not list objects or infer alternate filenames
at acquisition time.

| Canonical component | GEFSv12 file prefix |
| --- | --- |
| `tmax_k` | `tmax_2m` |
| `tmin_k` | `tmin_2m` |
| `specific_humidity_kg_kg` | `spfh_2m` |
| `surface_pressure_pa` | `pres_sfc` |
| `u10_m_s` | `ugrd_hgt` |
| `v10_m_s` | `vgrd_hgt` |
| `shortwave_w_m2` | `dswrf_sfc` |
| `precipitation_increment_kg_m2` | `apcp_sfc` |
| `elevation_m` | `hgt_sfc` |

The decoder uses these fixed GRIB short names. MLET verified them from public
GEFSv12 GRIB objects for a 2019-07-01 00Z daily control-member diagnostic.
This diagnostic verifies message selection only. It does not define the
weekly schedule. Do not replace a short name with a filename prefix.

The first segment uses a 0.25 degree grid. The long-range segment uses a 0.5
degree grid. The decoder uses the exact common 0.5 degree cells for both
segments. It takes their elevations from matching cells in the first segment.
It does not interpolate weather or elevation values across grids.

The checked object URIs, byte counts, SHA-256 values, and interval types are in
`data/outlook/gefs_reforecast_decoder_feasibility.json`. This record proves
software source feasibility only. It is not hindcast evidence.

| Canonical component | GRIB short name |
| --- | --- |
| `tmax_k` | `tmax` |
| `tmin_k` | `tmin` |
| `specific_humidity_kg_kg` | `2sh` |
| `surface_pressure_pa` | `sp` |
| `u10_m_s` | `10u` |
| `v10_m_s` | `10v` |
| `shortwave_w_m2` | `sdswrf` |
| `precipitation_increment_kg_m2` | `tp` |
| `elevation_m` | `orog` |

Create the source plan before retrieval. The plan records the verified weekly
source layout:

```bash
python3 scripts/acquire_gefs_reforecast.py \
  --first 2013-01-01 --last 2019-12-31 \
  --plan archive/gefs-v12-acquisition-plan.json --plan-only
```

This writes 68,255 planned objects: 365 Wednesday issues × 187 objects per
issue. The plan is read-only and cannot be replaced. Survey availability before
retrieval:

```bash
python3 scripts/survey_gefs_reforecast.py \
  --first 2019-07-03 --last 2019-07-03 \
  --output archive/gefs-20190703-availability.json --workers 8
```

Do not retrieve a plan when any required object is unavailable. Preserve the
survey with the acquisition receipt. Run the acquisition command with an empty
`--data-root` and a new `--receipt`. Retrieval writes each raw file once and
creates an immutable receipt. The socket timeout defaults to 600 seconds and
is bounded from 1 through 3,600 seconds.
The default is one transfer worker. Use a bounded value such as `--workers 8`
for a storage benchmark. The worker count changes transfer concurrency only.
It does not require HPC compute.

Measure one verified weekly issue before requesting long-term storage. Record
object count, raw bytes, elapsed transfer time, average throughput, and peak
disk use. The 2019-07-03 availability survey reports 8,289,206,079 bytes
(7.720 GiB) for 187 objects. This is an availability result. It is not a
transfer or decoder runtime. If sizes were uniform, 365 issues would require
about 3.03 TB of raw bytes. Treat that value as an estimate until the complete
issue transfer runs. Keep only the survey, checksums, metadata, and derived
results unless raw files are needed for decoding.

For the complete archive, use the sequential runner. It retrieves one issue,
verifies every object, decodes the version-2 artifact, records transfer and
response metadata, and then removes raw files unless `--keep-raw` is set:

```bash
python3 scripts/acquire_decode_gefs_reforecast_stream.py \
  --plan archive/gefs-v12-acquisition-plan.json \
  --raw-root "/external/gefs-stream/raw" \
  --receipts-root "/external/gefs-stream/receipts" \
  --artifacts-root "/external/gefs-stream/artifacts" \
  --index "/external/gefs-stream/index.json" \
  --candidates-root "/external/gefs-stream/candidates" \
  --git-revision "PINNED-CODE-REVISION" \
  --idaho-bbox=-117.25,42.00,-111.00,49.00 \
  --workers 8 \
  --timeout-seconds 600 \
  --attempts 3
```

Each issue has a raw-object receipt, an issue summary receipt, and a decoded
artifact. The issue summary records byte count, elapsed time, throughput,
filesystem free space, workspace size, response metadata counts, decoder time,
and artifact checksums. The runner retries transient network failures from
byte zero up to `--attempts` times per object. The default is three attempts,
bounded from 1 through 8. HTTP client errors are not retried. When candidate
options are supplied, the runner also writes a research-candidate manifest and
ETo outlook with their checksums. Use `--resume` with the same output roots
after completed issues. The runner keeps a failed issue directory for
diagnosis.

After retrieval, decode one fully verified issue:

```bash
python3 scripts/decode_gefs_reforecast.py \
  --receipt archive/gefs-v12-retrieval-receipt.json \
  --data-root archive \
  --issue-time 2019-07-03T00:00:00Z \
  --idaho-bbox=-117.25,42.00,-111.00,49.00 \
  --artifact archive/gefs-2019070300.daily-artifact.json
```

The command re-hashes every raw file named in the receipt. It requires every
object declared by the approved source protocol for the issue. It writes one
new version-2 daily artifact. It does not contact NOAA.

The converter uses these fixed units:

- temperature: Kelvin to Celsius with `C = K - 273.15`;
- shortwave radiation: Joules per square meter to Megajoules per square meter;
- precipitation: kilograms per square meter to millimeters; and
- vapor pressure: specific humidity and surface pressure with the documented
  moist-air conversion.

Record every raw URI and SHA-256 digest in the reforecast catalog. The public
catalog loader rejects duplicate or unordered issue times.

Source: [NOAA GEFS Reforecast Registry](https://registry.opendata.aws/noaa-gefs-reforecast/).

`normalized_sha256` is the SHA-256 of canonical normalized JSONL: weather rows
are sorted by `(grid_id, member_id, valid_date)`, each object has sorted compact
JSON keys, and each line ends with a newline. The importer recomputes it and
rejects any mismatch.

Use `serialize_gefs_daily_artifact()` after decoding all members for one issue.
It validates the decoded rows, computes `normalized_sha256`, and returns the
canonical artifact bytes that `materialize_gefs_daily_artifact()` imports.
Pass the verified raw-object receipt URI, hash, and object count to write a
version-2 artifact. Do not pass a synthetic aggregate digest in the old
`upstream_raw_sha256` field.
Give every component all GRIB segment files that cover the 20-day horizon. The
decoder reads each file and validates the complete daily component coverage.

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

1. an archived public GEFS GRIB test artifact with immutable URI and checksum;
2. an end-to-end automated test that validates the source issue, message
   selection, units, daily aggregation, and this artifact schema;
3. a documented scientific and operational release decision.
