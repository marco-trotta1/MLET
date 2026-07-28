# External reference data

Sources MLET has reviewed but does not ingest. Recorded because a reviewer will
ask, because one of them carries a defect warning that matters, and because one
of them supplies a packaging convention MLET should follow. The machine-readable
form is `data/reference/external_sources.json`.

## Caravan

Global large-sample hydrology, standardised across subdatasets, version 1.5
reviewed. It is the external benchmark in this literature.

**Not an MLET input.** Caravan is keyed by gauged basin and its target is
streamflow. MLET is keyed by native weather-grid cell and flux-tower station and
its target is evapotranspiration. No MLET evaluation target maps onto a Caravan
entity, so using it would mean changing the research question rather than adding
evidence.

**Defect warning that does transfer.** Caravan v1.5 added
`potential_evaporation_sum_FAO_PENMAN_MONTEITH` because ERA5-Land's native
`potential_evaporation` band is unreliable. If MLET ever falls back to ERA5-Land
meteorology, the native PET band must not be used. This is recorded in the
registry with `do_not_use: true`.

## Caravan MultiMet

Extends Caravan with multiple weather nowcasts and forecasts aligned to a fixed
issue time. This is the packaging problem MLET currently solves ad hoc for GEFS:
an observed forcing record plus N forecast products, each with its own issue
time, addressable together without ambiguity about what was knowable when.

Adopted as a **convention**, not as data. MLET's hindcast/forecast namespace
separation (`src/mlet/outlook/namespaces.py`) is the same distinction expressed
in the feature contract rather than in the file layout.

## What would change this

If MLET's scope ever extended to streamflow or to basin-keyed targets, Caravan
becomes a direct external validation set and this document should be revisited.
As long as the target is grid-cell and station evapotranspiration, it does not.
