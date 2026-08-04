#!/usr/bin/env bash
# Canonical MLET verification gate. Exits non-zero on any failure.
# Usage: ./scripts/verify.sh
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

echo "== python version =="
python3 --version

echo "== test suite =="
python3 -m pytest -q

echo "== serving-path isolation =="
# The hybrid package and PyTorch must never be reachable from the audited
# outlook path. Task 10 adds the pytest enforcement; this is the fast check.
if grep -rn --include=*.py -E "^\s*(import|from)\s+(torch|mlet\.hybrid)" \
     src/mlet/outlook src/mlet/sources src/mlet/experiments src/mlet/cli.py; then
  echo "FAIL: serving path imports torch or mlet.hybrid" >&2
  exit 1
fi
echo "ok"

echo "== VERIFY PASSED =="

echo "== real ETo candidate site =="
python3 scripts/verify_real_candidate_site.py
