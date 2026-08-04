#!/usr/bin/env bash
# Verify the frozen manuscript inputs and generated artifacts.
# Usage: ./scripts/verify_manuscript_ready.sh
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

./scripts/verify.sh

if [[ ! -f docs/results/idaho_eto_hindcast.json ]]; then
  echo "FAIL: the archived ETo hindcast result is not present" >&2
  exit 1
fi

temporary_directory="$(mktemp -d /private/tmp/mlet-manuscript-verify.XXXXXX)"
cleanup() {
  rm -f "$temporary_directory/phase2_openet_value.md"
  rm -f "$temporary_directory/idaho_eto_hindcast.md"
  rm -f "$temporary_directory/tables/phase2_model_comparison.csv"
  rm -f "$temporary_directory/tables/eto_skill_by_lead.csv"
  rm -f "$temporary_directory/tables/eto_skill_by_season.csv"
  rm -f "$temporary_directory/tables/eto_skill_by_spatial_fold.csv"
  rm -f "$temporary_directory/figures/phase2_model_comparison.svg"
  rm -f "$temporary_directory/figures/eto_error_by_lead.svg"
  rm -f "$temporary_directory/figures/eto_coverage_by_lead.svg"
  rm -f "$temporary_directory/figures/eto_bias_by_season.svg"
  rmdir "$temporary_directory/tables" "$temporary_directory/figures"
  rmdir "$temporary_directory"
}
trap cleanup EXIT

echo "== Phase 2 artifact regeneration =="
python3 scripts/build_manuscript_artifacts.py \
  --phase2 docs/results/phase2_openet_value.json \
  --eto-hindcast docs/results/idaho_eto_hindcast.json \
  --out "$temporary_directory"
cmp -s "$temporary_directory/phase2_openet_value.md" docs/results/phase2_openet_value.md
cmp -s "$temporary_directory/tables/phase2_model_comparison.csv" \
  docs/results/tables/phase2_model_comparison.csv
cmp -s "$temporary_directory/figures/phase2_model_comparison.svg" \
  docs/results/figures/phase2_model_comparison.svg
cmp -s "$temporary_directory/idaho_eto_hindcast.md" \
  docs/results/idaho_eto_hindcast.md
cmp -s "$temporary_directory/tables/eto_skill_by_lead.csv" \
  docs/results/tables/eto_skill_by_lead.csv
cmp -s "$temporary_directory/tables/eto_skill_by_season.csv" \
  docs/results/tables/eto_skill_by_season.csv
cmp -s "$temporary_directory/tables/eto_skill_by_spatial_fold.csv" \
  docs/results/tables/eto_skill_by_spatial_fold.csv
cmp -s "$temporary_directory/figures/eto_error_by_lead.svg" \
  docs/results/figures/eto_error_by_lead.svg
cmp -s "$temporary_directory/figures/eto_coverage_by_lead.svg" \
  docs/results/figures/eto_coverage_by_lead.svg
cmp -s "$temporary_directory/figures/eto_bias_by_season.svg" \
  docs/results/figures/eto_bias_by_season.svg

echo "== Required manuscript sources =="
for path in \
  manuscript/manuscript.md \
  manuscript/SUPPLEMENT.md \
  manuscript/DATA_AVAILABILITY.md \
  manuscript/CODE_AVAILABILITY.md \
  manuscript/LIMITATIONS.md \
  manuscript/references.bib; do
  test -s "$path"
done

echo "== VERIFY MANUSCRIPT READY PASSED =="
