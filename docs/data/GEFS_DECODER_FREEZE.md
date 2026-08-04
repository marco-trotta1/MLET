# GEFS decoder freeze

The 2019-07-03 source-feasibility artifact uses the locked packages in
`requirements-gefs.lock`.

The canonical transform is
`noaa-gefs-grib-to-daily-asce-input`, version `1`.

The run uses Python 3.13.5 and repository revision
`3364b93579df45ab54f0b753fa2b7e150ce67c87`.

The decoder selects the verified GEFSv12 short names and the exact common
0.5-degree grid. It expands selected six-hour values into canonical three-hour
steps before daily aggregation.

The resulting schema-v2 artifact has SHA-256
`154e88317fe9aa6bb7b31595e5cbdd149735ffc92acdfc7ed55d7b68e49d901c`.

Regenerate the artifact only from the checksummed receipt in
`data/outlook/gefs_reforecast_20190703_transfer_receipt.json` and the external
raw evidence root recorded in the feasibility receipt.
