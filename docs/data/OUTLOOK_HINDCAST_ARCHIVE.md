# ETo hindcast archive

The archive assembler creates one self-contained schema-v4 ETo evidence root.

Use `mlet outlook build-eto-hindcast-archive --gefs-index ... --agrimet-index ...
--destination ...` for a source-index build. Use
`mlet assemble-eto-evidence` only for an already assembled evidence bundle.
The Python entry point is
`mlet.outlook.archive.build_eto_hindcast_archive(gefs_index, agrimet_index,
destination)`.

The GEFS index uses this shape:

```json
{
  "schema_version": 1,
  "kind": "mlet.eto.gefs-index",
  "issues": [
    {
      "case_id": "issue-2019-07-01",
      "issue_time": "2019-07-01T00:00:00Z",
      "forecast_directory": "forecasts/issue-2019-07-01",
      "source_available_at": {"gefs": "2019-07-01T00:00:00Z"},
      "held_out_fold": 0,
      "held_out_season": "JJA"
    }
  ]
}
```

The AgriMet index points to schema-v2 target artifacts:

```json
{
  "schema_version": 1,
  "kind": "mlet.eto.agrimet-index",
  "targets": [
    {"case_id": "issue-2019-07-01", "target_path": "targets/issue-2019-07-01.json"}
  ]
}
```

Each input issue must already contain:

- a checksum-bound ETo candidate and run manifest;
- an independently sourced AgriMet target artifact;
- source availability receipts; and
- a spatial and seasonal holdout receipt.

The assembler copies all referenced files below the destination root. It
rebuilds the evidence digest and evaluates the result before it returns.

The assembler does not acquire GEFS or AgriMet data. Raw data remain outside
Git. It copies both source indexes into the archive and writes
`archive-index-receipt.json` with their checksums.

The archive is not complete until the evaluator reports all 20 leads, four
seasons, five spatial folds, and at least 30 paired targets in every lead,
season, and fold cell.

Evaluate the archive with `mlet outlook hindcast --evidence ... --output ...`.
The command writes a diagnostic result and returns a nonzero status while the
archive is incomplete. It never promotes the forecast.

The result record includes archive and evaluation digests, forecast revisions,
source versions, explicit exclusions, 400 support cells, baseline and forecast
metrics, paired confidence intervals, and claim-safe prose.
