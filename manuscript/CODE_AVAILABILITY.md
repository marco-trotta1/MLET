# Code availability

The MLET source repository contains the target adapters, ETo candidate builder,
hindcast evaluator, and deterministic manuscript artifact generator.

Run the software verification gate with:

```bash
./scripts/verify.sh
```

Run the non-gated draft gate with:

```bash
./scripts/verify_build_ready.sh
```

Bundle completed issue evidence with:

```bash
mlet outlook build-eto-hindcast-archive \
  --gefs-index GEFS_INDEX.json \
  --agrimet-index AGRIMET_INDEX.json \
  --destination ARCHIVE_ROOT
```

Rebuild the current AgriMet station snapshot with:

```bash
python3 scripts/acquire_agrimet_station_registry.py \
  --destination data/outlook/agrimet_station_registry.json
```

Run `./scripts/verify_manuscript_ready.sh` only after the complete ETo result
record is present. It intentionally fails when the outcome archive is absent.

The repository does not require a storage allocation, an HPC account, an OpenET
API key, or Irrigant access to run the software tests or build the draft.
