# MLET feature freeze

**Date:** 2026-07-31

## Frozen manuscript scope

The manuscript reports two separate evidence paths:

1. the Phase 2 historical daily actual-ET comparison; and
2. the ETo-only, 20-day regional outlook protocol.

The current AgriMet station registry snapshot is complete for public current
metadata. Historical station movement records and the full GEFS outcome archive
remain data gates. They are not replaced with assumptions.

## Outside the manuscript gate

The following work is deferred:

- OpenET API keys and a new OpenET acquisition path;
- CDL download and intersection work;
- soil-moisture assimilation;
- hybrid or LSTM training;
- ETc or ETa forecast validation;
- UI redesign;
- operational promotion;
- direct Irrigant integration; and
- a definite institutional storage or compute allocation.

Future experiments must not alter the frozen target, baseline, split, or claim
language after outcome inspection. A new scientific question requires a dated
protocol amendment.

## Storage and compute rule

Use local or lab storage for one-off analysis. Keep only URLs, checksums,
metadata, and derived results when raw bytes are not needed. Request temporary
project storage from the PI before keeping the full raw archive. Do not request
a general HPC allocation for this transfer. Add batch compute only if repeated
large runs later require it.

The next feasibility action is one weekly GEFS issue. Measure its object count,
raw size, transfer time, decode time, throughput, and peak disk use. Decide the
storage request from those measurements.

The source layout is now resolved. The weekly GEFS issues are Wednesdays from
2013-01-02 through 2019-12-25. Each issue has 11 members and the two segments
`Days:1-10` and `Days:10-35`. A full 2019-07-03 availability survey found
187 of 187 required objects and 8,289,206,079 advertised bytes. The summary is
`data/outlook/gefs_reforecast_20190703_availability.json`.

The earlier 2019-07-01, 85-object transfer was a daily five-member diagnostic.
It is superseded for weekly archive sizing. A complete weekly transfer and
decoder run remain required before requesting long-term storage.
