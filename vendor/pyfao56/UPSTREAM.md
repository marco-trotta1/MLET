# pyfao56 upstream snapshot

This folder contains the source code for `pyfao56`, vendored for the early
MLET soil-moisture forecasting scaffold.

## Source

- Repository: https://github.com/kthorp/pyfao56
- Upstream commit: `1d242ee985be0edbc4946f06e7e94a487d4bc0c9`
- Upstream commit date: 2026-02-12 11:49:05 -0600
- Upstream version: `1.4.3`
- License: CC0 1.0 Universal / public domain dedication, preserved in
  `LICENSE.md`

## Local scope

Only the package source and upstream project metadata were copied here. The
large upstream test fixture tree was intentionally left out because this
scaffold needs the FAO-56 implementation code, not 179 MB of example outputs
and test data.

The rough project plan identifies pyfao56 as the FAO-56 dual-coefficient water
balance scaffold that MLET can later adapt into a differentiable forecasting
component.
