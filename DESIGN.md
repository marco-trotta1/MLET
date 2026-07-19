# Design System — MLET (Idaho Regional ET Outlook)

## Product Context
- **What this is:** An open-source, reproducible 20-day Idaho evapotranspiration
  outlook on the native weather grid, with p10/p50/p90 uncertainty and a frozen
  product contract. First public surface: a GitHub Pages site (landing +
  outlook map viewer + results charts) rendered from `mlet publish-outlook`
  artifacts.
- **Who it's for:** Researchers auditing the artifact contract, and public
  users who need a regional (not field-scale) ET outlook.
- **Space/industry:** Scientific weather/ET forecasting. Peers: GraphCast,
  ECMWF Charts, OpenET, Open-Meteo.
- **Project type:** Scientific data product — static landing page + map/chart
  dashboard.
- **The memorable thing:** *"The forecast that shows its work."* Honest
  uncertainty and auditable provenance are the identity. Every design decision
  serves that.

## Aesthetic Direction
- **Direction:** Frontier lab. Utilitarian scientific tool — the register of a
  research-lab release page, not a product marketing site. One sans family
  everywhere; the visualization is the hero; chrome stays quiet, monochrome,
  and typographic. No serif, anywhere.
- **Decoration level:** None. No gradients, no illustration, no stock imagery,
  no italic flourishes, no marketing copy. The map, the uncertainty bands, and
  the provenance chips are the only visual interest.
- **Mood:** Precise, terse, confident. Copy states facts ("20 daily lead
  dates. p10/p50/p90. Native weather grid."), never sells.
- **Reference:** deepmind.google GraphCast post (prose measure + full-bleed
  figures, monochrome chrome); frontier-lab release pages generally.
  Anti-reference: open-meteo.com landing (default-blue interchangeable SaaS).
- **Ecosystem survey (2026-07-19):** GenCast/GraphCast, FourCastNet,
  Pangu-Weather, ClimaX, Aurora, NeuralGCM, Makani, ECMWF Anemoi, NVIDIA
  Earth2Studio, Modulus/PhysicsNeMo, DeepXDE, OpenFold, AlphaFold 3
  implementations, Open Catalyst, SchNetPack, PyTorch Geometric, DeepChem,
  TorchMD-Net, JAX-CFD, PhiFlow, Dedalus, Oceananigans, ClimateLearn. Shared
  presentation grammar MLET follows:
  1. code above the fold — install + minimal run command on page one;
  2. BibTeX citation block as a first-class landing component;
  3. explicit limitations sections in the nav (Aurora's "Beware!"), not
     footnotes — MLET's research-candidate banners follow this convention;
  4. benchmark/evidence tables with CIs as centerpiece content, no adjectives;
  5. utilitarian docs chrome: one sans, one accent, dark mode, version
     awareness (run_id + changelog), left nav + on-page TOC for methods pages;
  6. artifact tables with licenses, versions, checksums, download links;
  7. the only imagery is real model output.

## Typography
- **Everything (display, headings, body, UI):** Söhne (Klim Type Foundry).
  Headings 600 weight with −0.02em tracking; body 400. One family carries the
  whole interface — hierarchy comes from size, weight, and case, not from
  mixing families.
- **Data/Provenance/Code:** Söhne Mono with `tabular-nums` — all numbers, run
  IDs, timestamps, checksums, chips, table cells, axis labels.
- **Licensing/fallback:** Söhne is a commercial license — buy from Klim and
  self-host woff2 on Pages; it must never be hotlinked or committed to a
  public repo unlicensed. Stack: `"Söhne", "Inter", -apple-system, sans-serif`
  and `"Söhne Mono", "IBM Plex Mono", ui-monospace`. Until the license is in
  place, the site renders Inter/IBM Plex Mono (both Google Fonts).
- **Scale:** hero clamp(30px, 4.4vw, 44px)/600 · section heads 18px/600 ·
  labels 11.5–12px uppercase +0.08em tracking · body 15px/1.6 · data
  12.5–13.5px mono · caption 11.5px mono. Kept deliberately smaller than
  consumer-product scale — instrument, not billboard.

## Color
- **Approach:** Restrained. Chrome is near-monochrome; **viridis is reserved
  exclusively for data** (map cells, ramps, chart series). UI never imitates
  the colormap.
- **Ground ("Paper"):** `#FAFAF8` — just off pure white. Surfaces `#FFFFFF`,
  recessed `#F2F2EF`.
- **Ink:** text `#191D1B`, secondary `#505652`, tertiary `#7C827E`; lines
  `#E0E0DB` / `#BFBFB8`.
- **Accent:** teal `#17706B` (hover `#0E5551`, tint `#E3F0EE`) — sampled from
  the cool half of viridis so controls feel related to the data.
- **Semantic:** caution amber `#C77E1B` on `#FDF3E3` (reserved for
  `validation_pending` / research-candidate / fixture banners — this is a
  first-class brand color, not an error style), error `#B3261E`, success
  `#2E7D32`, info `#1D4E89`.
- **Data ramp:** viridis 11-stop (`#440154` → `#FDE725`), colorblind-safe.
  Missing data: neutral gray `#79837C`, never a ramp color.
- **Dark mode:** class toggle on `<html>`. Ground `#111413`, surface
  `#191D1B`, ink `#E9EAE7`, accent lightened `#4CB8AE`, amber kept, viridis
  unchanged (it reads better on dark).

## Spacing
- **Base unit:** 8px
- **Density:** comfortable; compact inside data tables (8px cell padding)
- **Scale:** 2xs(2) xs(4) sm(8) md(16) lg(24) xl(32) 2xl(48) 3xl(64) 4xl(96)

## Layout
- **Approach:** grid-disciplined. Prose in a 58–68ch measure; maps, charts,
  and tables may break out to the full 1100px shell (GraphCast pattern).
- **Max content width:** 1100px shell, 24px gutters.
- **Dashboard:** 280px control sidebar + fluid map/chart main; stacks under
  860px.
- **Border radius:** sm 3px (chips) · md 6px (buttons, inputs, cards) ·
  lg 10px (mockup frames). Nothing pill-shaped.

## Motion
- **Approach:** minimal-functional. A scientific instrument doesn't perform.
- **Easing:** enter ease-out, exit ease-in, move ease-in-out.
- **Duration:** micro 100ms (hover) · short 150–250ms (state changes). No
  entrance choreography, no scroll animation.

## Signature Patterns (what makes MLET look like MLET)
1. **Provenance chips:** run ID, issue time, cutoff, checksum status as
   monospace bordered chips at the top of every view — first-class UI, not
   footer fine print.
2. **Status banners:** amber `RESEARCH CANDIDATE` / `validation_pending`
   blocks styled as part of the brand; never hidden, never red-alarm.
3. **Uncertainty fans:** every forecast line chart shows the p10–p90 band
   (accent teal at 16% opacity) behind the p50 line; a lone deterministic
   line is a contract violation.
4. **Honest labels verbatim:** layer names from the product contract
   (`eto_mm`, `eta_analysis_mm`, scenario names) appear in mono beside their
   human labels; scenario assumptions render next to scenario values.
5. **Quickstart code block on the landing:** `pip install` / `python3 -m mlet`
   commands in a mono block (Söhne Mono, recessed surface, 1px border, no
   syntax-highlight rainbow — accent teal for commands only). The tool is the
   hero; reproduce-it-yourself is the pitch.
6. **Citation block:** BibTeX in a mono block with a copy button, on the
   landing and in the footer of every methods page.
7. **Artifact table:** every downloadable (outlook.geojson, summary.json, run
   receipt) listed with size, sha256, and generation timestamp — the
   Aurora/OCP checkpoint-table convention applied to forecast artifacts.

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-07-19 | Initial design system created | /design-consultation; research on GraphCast + Open-Meteo; user directive: clean scientific UI for GitHub Pages, GraphCast-inspired |
| 2026-07-19 | Viridis reserved for data only | Colorblind-safe, scientifically credible; keeps chrome from competing with the map |
| 2026-07-19 | Provenance/caution styled as brand | The project's honesty (frozen contracts, promotion:false) becomes the visual signature |
| 2026-07-19 | Rev 2: serif removed; Söhne everywhere; frontier-lab register | User direction: scientific research tool, no fluff, should feel like it comes out of a frontier lab |
| 2026-07-19 | Söhne with Inter/IBM Plex Mono fallback | Söhne is a commercial Klim license — self-host licensed woff2; fallbacks render until then |
| 2026-07-19 | Rev 3: adopt scientific-ML ecosystem conventions | Survey of 23 frontier-lab projects (Aurora, NeuralGCM, Earth2Studio, Open Catalyst, Oceananigans et al.): quickstart code block, BibTeX citation, limitations-in-nav, artifact tables with checksums |
