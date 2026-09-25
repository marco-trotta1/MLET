# External cropland validation feasibility

Status: feasibility review only. No external outcomes were downloaded or scored.
This file does not freeze a confirmatory experiment.

## Why this review exists

The main cropland result uses the OpenET and flux archive in this repository.
Its earlier selector choice also used outcomes from that archive.
An external test can check whether the crop-only training result transfers.

The proposed target is daily actual ET at unseen cropland sites.
The proposed comparison is all-station SupportGain against crop-only SupportGain.
Both methods must use the same held-out rows and OpenET fallback.
The proposed primary score is the site-macro MAE difference.
Positive values favor crop-only training.

## Candidate source

AmeriFlux lists daily FLUXNET products and daily latent-heat variables.
Its FLUXNET product includes `LE_CORR`, which applies an energy-balance closure correction.
This target is closer to MLET's `ET_corr` label than the raw latent-heat flux.
Convert daily `LE_CORR` from watts per square metre to millimetres per day.
Use the same conversion as the source archive after confirming its formula.

OpenET documents daily ensemble data in the CONUS from 2016 through 2025.
This period overlaps recent AmeriFlux cropland records.
Use the same daily weather inputs and feature order as the ten-member gridMET model.

AmeriFlux site pages list several candidate records under CC-BY-4.0.
These examples do not form a complete candidate inventory.
The [AmeriFlux site search](https://ameriflux.lbl.gov/sites/site-search/) filters by product, policy, years, and vegetation.
This review did not save a complete filtered export.

| Site | Public description | FLUXNET years shown | Policy |
| --- | --- | --- | --- |
| [US-CF1](https://ameriflux.lbl.gov/sites/siteinfo/US-CF1) | Cook East field | 2017 to 2021 | CC-BY-4.0 |
| [US-CF2](https://ameriflux.lbl.gov/sites/siteinfo/US-CF2) | Cook West field | 2017 to 2020 | CC-BY-4.0 |
| [US-CF3](https://ameriflux.lbl.gov/sites/siteinfo/US-CF3) | Boyd North field | 2017 to 2021 | CC-BY-4.0 |
| [US-CF4](https://ameriflux.lbl.gov/sites/siteinfo/US-CF4) | Boyd South field | 2017 to 2021 | CC-BY-4.0 |
| [US-CS1](https://ameriflux.lbl.gov/sites/siteinfo/US-CS1) | Central Sands irrigated potato field | 2018 to 2019 | CC-BY-4.0 |
| [US-CS5](https://ameriflux.lbl.gov/sites/siteinfo/US-CS5) | Heartland Farms irrigated potato field | 2021 | CC-BY-4.0 |
| [US-CS3](https://ameriflux.lbl.gov/sites/siteinfo/US-CS3) | Central Sands irrigated potato field | 2019 to 2020 | CC-BY-4.0 |
| [US-CS4](https://ameriflux.lbl.gov/sites/siteinfo/US-CS4) | Heartland Farms potato field | 2020 to 2021 | CC-BY-4.0 |
| [US-CS6](https://ameriflux.lbl.gov/sites/siteinfo/US-CS6) | Worzella Farms irrigated potato field | 2022 to 2023 | CC-BY-4.0 |
| [US-CS8](https://ameriflux.lbl.gov/sites/siteinfo/US-CS8) | Worzella Farms irrigated potato field | 2023 | CC-BY-4.0 |
| [US-SD1](https://ameriflux.lbl.gov/sites/siteinfo/US-SD1) | Corn and soybean, no cover crops | 2023 to 2025 | CC-BY-4.0 |
| [US-VT2](https://ameriflux.lbl.gov/sites/siteinfo/US-VT2) | Corn and soybean, cover crops; paired with [US-VT1](https://www.osti.gov/dataexplorer/biblio/dataset/2567994) | 2023 to 2025 | CC-BY-4.0 |
| [US-DS2](https://ameriflux.lbl.gov/sites/siteinfo/US-DS2) | Staten Island corn field | 2020 to 2023 | CC-BY-4.0 |
| [US-DS3](https://ameriflux.lbl.gov/sites/siteinfo/US-DS3) | Rice field | 2021 to 2025 | CC-BY-4.0 |
| [US-RGA](https://ameriflux.lbl.gov/sites/siteinfo/US-RGA) | Corn farm | 2021 to 2024 | CC-BY-4.0 |
| [US-RGo](https://ameriflux.lbl.gov/sites/siteinfo/US-RGo) | Organic rice farm | 2021 to 2024 | CC-BY-4.0 |
| [US-RGF](https://ameriflux.lbl.gov/sites/siteinfo/US-RGF) | Corn and wheat rotation | 2023 to 2024 | CC-BY-4.0 |
| [US-UTW](https://ameriflux.lbl.gov/sites/siteinfo/US-UTW) | Irrigated alfalfa | 2021 to 2024 | CC-BY-4.0 |
| [US-UTD](https://ameriflux.lbl.gov/doi/FLUXNET/US-UTD) | Irrigated alfalfa mix | 2023 to 2024 | CC-BY-4.0 |
| [US-UTG](https://ameriflux.lbl.gov/sites/siteinfo/US-UTG) | Alfalfa field edge | none shown; BASE 2025 | CC-BY-4.0 |
| [US-UTN](https://ameriflux.lbl.gov/sites/siteinfo/US-UTN) | Irrigated crop fields near Nephi | none shown; BASE 2023 | CC-BY-4.0 |
| [US-HRA](https://ameriflux.lbl.gov/sites/siteinfo/US-HRA) | Rice field | 2015 to 2024 | CC-BY-4.0 |
| [US-HRC](https://ameriflux.lbl.gov/sites/siteinfo/US-HRC) | Rice field | 2015 to 2024 | CC-BY-4.0 |
| [US-MN1](https://ameriflux.lbl.gov/sites/siteinfo/US-MN1) | Corn and soybean with cover crops | 2017 to 2024 | CC-BY-4.0 |
| [US-MN2](https://ameriflux.lbl.gov/sites/siteinfo/US-MN2) | Corn, soybean, and wheat with cover crops | 2017 to 2024 | CC-BY-4.0 |
| [US-MN3](https://ameriflux.lbl.gov/sites/siteinfo/US-MN3) | Corn and soybean rotation | 2020 to 2024 | CC-BY-4.0 |
| [US-A39](https://ameriflux.lbl.gov/sites/siteinfo/US-A39) | Cropland at ARM SGP Morrison | 2024 | CC-BY-4.0 |
| [US-CC1](https://ameriflux.lbl.gov/sites/siteinfo/US-CC1) | Corn field | none shown; BASE 2021 | CC-BY-4.0 |
| [US-ZF2](https://ameriflux.lbl.gov/sites/siteinfo/US-ZF2) | Corn and soybean rotation; paired with [US-ZF1](https://ameriflux.lbl.gov/sites/siteinfo/US-ZF1) | 2024 to 2025 | CC-BY-4.0 |
| [US-WT1](https://ameriflux.lbl.gov/sites/siteinfo/US-WT1) | Cotton and grain sorghum | 2023 to 2024 | CC-BY-4.0 |
| [US-UTL](https://ameriflux.lbl.gov/sites/siteinfo/US-UTL) | Drip-irrigated alfalfa | 2024 to 2025 | CC-BY-4.0 |
| [US-DFC](https://ameriflux.lbl.gov/sites/siteinfo/US-DFC) | Dairy Forage Research Center crop field | 2018 to 2024 | CC-BY-4.0 |
| [US-DFK](https://ameriflux.lbl.gov/sites/siteinfo/US-DFK) | Dairy Forage Research Center Kernza field | 2018 to 2020 | CC-BY-4.0 |
| [US-UC1](https://ameriflux.lbl.gov/sites/siteinfo/US-UC1) | Upper Chesapeake Bay EC1, corn field, IGBP CVM | 2019 to 2024 | CC-BY-4.0 |
| [US-UC2](https://ameriflux.lbl.gov/sites/siteinfo/US-UC2) | Upper Chesapeake Bay EC2, corn field, IGBP CVM | 2019 to 2024 | CC-BY-4.0 |
| [US-OPE](https://ameriflux.lbl.gov/sites/siteinfo/US-OPE) | Crop production field near wetland | 2022 | CC-BY-4.0 |
| [US-UTE](https://ameriflux.lbl.gov/sites/siteinfo/US-UTE) | Alfalfa field edge | 2024 to 2025 | CC-BY-4.0 |
| [US-Mo1](https://ameriflux.lbl.gov/sites/siteinfo/US-Mo1) | Commercial crop field, CMRB Field 1 | 2015 to 2024 | CC-BY-4.0 |
| [US-Mo3](https://ameriflux.lbl.gov/sites/siteinfo/US-Mo3) | Commercial corn and soybean field, CMRB Field 3 | 2016 to 2023 | CC-BY-4.0 |

The site metadata was checked on 25 September 2026.
The current [US-CF1 profile](https://ameriflux.lbl.gov/sites/siteinfo/US-CF1) lists an AmeriFlux FLUXNET-1F product, version v1.3_r1, for 2017 through 2021.
Its dataset DOI is [10.17190/AMF/1832158](https://doi.org/10.17190/AMF/1832158), under the CC-BY-4.0 policy.
This confirms a current product identifier, not daily `LE_CORR` values or file access.

The fixed gridMET cohort has 151 stations, including `US-Ne1`, `US-Bi1`, and `US-ARM`.
Exclude any candidate within 25 km of any station in this cohort.
The checked AmeriFlux coordinates give these nearest distances:

| Candidate group | Nearest cohort station | Distance |
| --- | --- | ---: |
| US-SD1 | US-KM4 | 149.3 km |
| US-CF1, US-CF2, US-CF3, US-CF4 | US-Hn3 | 178.0 km |
| US-RGA, US-HRA, US-HRC | stonevillesoy | 130.2 km |
| US-UTW | SPV_3 | 323.2 km |
| US-UTG | SPV_3 | 367.9 km |
| US-UTN | SPV_3 | 234.0 km |
| US-VT1, US-VT2 | US-Bo1 | 78.7 km |
| US-RGo | BAR012 | 133.0 km |
| US-RGF | US-Bi1 | 54.6 km |
| US-MN1, US-MN3 | US-Bkg | 151.2 km |
| US-MN2 | US-Bkg | 153.0 km |
| US-A39 | US-ARM | 129.4 km |
| US-CC1, US-CS1, US-CS3, US-CS4, US-CS5 | US-xST | 150.1 km |
| US-CS6, US-CS8 | US-xST | 119.6 km |
| US-ZF2 | US-Bo1 | 108.4 km |
| US-WT1 | LYS_SE | 94.6 km |
| US-UTL | US-GLE | 316.2 km |
| US-DFC | US-IB1 | 205.3 km |
| US-DFK | US-IB1 | 205.5 km |
| US-UC1 | US-Slt | 303.7 km |
| US-UC2 | US-Slt | 303.3 km |
| US-OPE | US-Slt | 216.7 km |
| US-UTE | US-Fwf | 255.3 km |
| US-UTD | US-Fwf | 353.5 km |
| US-Mo1, US-Mo3 | US-MOz | 54.5 km |

Distances use reported site coordinates and great-circle calculations.
The sources do not report coordinate uncertainty.
US-CF1, US-CF2, US-CF3, and US-CF4 span 4.8 km.
Treat these four Cook Agronomy Farm fields as one spatial group.
US-CS1, US-CS3, and US-CS4 are within 14.2 km of US-CC1.
Treat these four Wisconsin fields as one spatial group.
US-CS5 is 12.0 km from US-CC1 and extends this group.
US-CS6 and US-CS8 are 0.8 km apart.
The nearest old Central Sands candidate is US-CS4, 30.5 km away.
Treat US-CS6 and US-CS8 as a separate spatial group.
US-HRA and US-HRC are 20.1 km and 20.5 km from US-RGA.
Treat those three Arkansas sites as one spatial group.
US-MN1 and US-MN3 are 0.9 km apart.
US-MN2 is 2.0 km from US-MN3.
Treat all three Morris fields as one spatial group.
US-Mo1 and US-Mo3 are 2.8 km apart.
Treat the two Central Missouri fields as one spatial group.
US-UTN is 102.5 km from US-UTW.
Treat US-UTN as a separate spatial group.
US-VT1 and US-VT2 are paired fields on one property.
US-ZF1 and US-ZF2 are paired fields on one farm.
US-DS2 and US-DS3 are 3.7 km and 2.0 km from training site US-Bi2.
Exclude both Staten Island sites.
The checked site list forms 22 candidate spatial groups after the 25 km exclusion.
Twenty of these 22 groups list a FLUXNET year range.
The US-UTG and US-UTN groups have no member with a listed FLUXNET year range.
US-DFC/US-DFK, US-OPE, US-UTE, US-Mo1/US-Mo3, US-CS6/US-CS8, US-UTN, and US-UC1/US-UC2 add seven spatial groups.
US-CS1/US-CS3/US-CS4/US-CS5 and US-MN1/US-MN2/US-MN3 extend existing spatial groups.
US-UC1 and US-UC2 are 0.55 km apart. Treat them as one spatial group.
Their IGBP class is CVM, although both site descriptions identify corn fields.
The inventory has 22 candidate groups, and 20 list a FLUXNET year range.
This meets the provisional group-count threshold, but it does not establish 20 eligible groups.
Site-level quality, daily `LE_CORR`, and OpenET footprint support remain unchecked.

## Local later-year holdout

The screened gridMET cohort has 20 rows in 2021, all from station and group `S2`.
This group has 63 earlier rows from 2017 through 2020 and appears in training data.
These 2021 rows cannot support independent site confirmation or a multi-group interval.

## Other public records checked

The [REACCH release](https://verso.uidaho.edu/esploro/outputs/dataset/Data-REACCHPNA-Monitoring---REACCH-Flux/996762919001851) covers five crop towers from 2012 through 2015.
The [US-RC5 AmeriFlux record](https://ameriflux.lbl.gov/sites/siteinfo/US-RC5) covers 2013 through 2015 within this cluster.
Both records end before daily OpenET coverage begins in 2016.
They cannot support the planned daily comparison.

The [US-ARM record](https://ameriflux.lbl.gov/sites/siteinfo/US-ARM) has a cropland classification and a FLUXNET record through 2025.
The fixed MLET cohort contains station `US-ARM` at the same coordinates.
Exclude this record because it is part of model development.
The [US-A74](https://ameriflux.lbl.gov/sites/siteinfo/US-A74) and [US-xSL](https://ameriflux.lbl.gov/sites/siteinfo/US-xSL) records also appear in the fixed cohort.
Do not count them as external sites.
The [US-CRT record](https://ameriflux.lbl.gov/sites/siteinfo/US-CRT) covers 2011 through 2013.
It does not overlap daily OpenET coverage.

The [US-IAB record](https://ameriflux.lbl.gov/sites/siteinfo/US-IAB) describes corn-soy rotation and FLUXNET data from 2019 through 2024.
It is 2.9 km from training station US-Br3, so exclude it.
The [US-UiB record](https://ameriflux.lbl.gov/sites/siteinfo/US-UiB) describes Miscanthus and FLUXNET data from 2008 through 2024.
It is 10.0 km from training station US-Bo1, so exclude it.
The [US-Ro1](https://ameriflux.lbl.gov/sites/siteinfo/US-Ro1) and [US-Ro5](https://ameriflux.lbl.gov/sites/siteinfo/US-Ro5) crop records already appear in the fixed training cohort.
Exclude both from external validation.
The [US-DFK record](https://ameriflux.lbl.gov/sites/siteinfo/US-DFK) has a CC-BY-4.0 FLUXNET product from 2018 through 2020.
It is 0.3 km from US-DFC, so it extends that candidate group without adding an independent group.
The [US-Ne2](https://ameriflux.lbl.gov/sites/siteinfo/US-Ne2) and [US-Ne3](https://ameriflux.lbl.gov/sites/siteinfo/US-Ne3) records already appear in the fixed cohort.
US-Ne1 is also in the cohort, and the three Mead fields lie within 1.6 km.
Exclude all three from external validation.
The [US-Tw3](https://ameriflux.lbl.gov/sites/siteinfo/US-Tw3) and [US-Twt](https://ameriflux.lbl.gov/sites/siteinfo/US-Twt) crop records also appear in the fixed cohort.
Exclude both from external validation.
The [US-KL1 record](https://ameriflux.lbl.gov/sites/siteinfo/US-KL1) lists BASE data from 2009 through 2021, with no FLUXNET range.
It is 10.3 km from training station US-KM4, so exclude it.
The [US-UTD FLUXNET record](https://ameriflux.lbl.gov/doi/FLUXNET/US-UTD) describes alfalfa mix under wheel-line irrigation and uses CC-BY-4.0.
The [2026 FLUXNET site list](https://www.keenangroup.info/fluxnet-paper.html) reports coverage from 2023 through 2024.
The [ORNL MODIS site record](https://modis.ornl.gov/sites/?network=AMERIFLUX&network_siteid=US-UTD) gives coordinates 38.1038, -109.5952.
The nearest training station is US-Fwf at 353.5 km, and the nearest other checked Utah tower is US-UTM at 53.9 km.
US-UTD therefore adds a separate spatial group beyond the 25 km exclusion.
Daily `LE_CORR`, quality fields, and OpenET footprint support remain unchecked.

The [US-UTJ BASE record](https://www.osti.gov/dataexplorer/biblio/dataset/2531150) describes an alfalfa field near the San Juan River.
It gives coordinates 37.2818, -109.5348 and DOI 10.17190/AMF/2531150.
The 2026 FLUXNET site list reports 2024 through 2025, but the [AmeriFlux FLUXNET DOI lookup](https://ameriflux.lbl.gov/doi/FLUXNET/US-UTJ) currently returns no valid listing.
Keep US-UTJ outside the group count until a current FLUXNET product and its policy are confirmed.

The [Milk River release](https://catalog.data.gov/dataset/evapotranspiration-and-associated-meteorological-data-collected-with-eddy-covari-2022-2024) covers two towers from 2022 through 2024.
It provides daily ET and site weather for towers in Canada.
OpenET documents daily coverage for the continental United States.
The release cannot support the planned OpenET comparison at these sites.

The [Parallel 41 network](https://parallel41.nebraska.edu/about) provides daily measured ET and reference ET at crop sites.
Its reviewed page names 19 locations but gives no complete station inventory, coordinates, or record dates.
It offers more tower measurements upon request and does not state a data reuse license.
The available page does not establish 20 eligible spatial groups or the required model inputs.

The [FLUXNET Shuttle](https://data.fluxnet.org/) became operational in 2026.
Its data products use CC-BY-4.0 and include standardized flux and weather data.
The live download page requires an email address and intended-use description.
Its current page lists TERN as reporting and AmeriFlux and ICOS as not reporting.
That snapshot does not establish eligible U.S. crop sites or daily OpenET overlap.
No data request was submitted.
The FLUXNET2015 release predates daily OpenET coverage, which begins in 2016.

The [Swiss FluxNet CH-OE2 record](https://meta.icos-cp.eu/objects/39gLjDLg85pGQzLxDnzjtRU1) covers one cropland site from 2004 through 2023.
Its page lists a CC-BY-4.0 license.
One site cannot establish a multi-site result, and the site has no OpenET baseline.

## Utah Flux Network access review

Reviewed on 25 September 2026.
The [Colorado River Authority describes UFN](https://cra.utah.gov/utah-flux-network/) as a source of field-scale ET measurements for OpenET checks.
It says raw data is available after collection and links to AmeriFlux, EasyFluxWeb, MesoWest, and OpenET.
The Authority identifies Dugout Ranch as an alfalfa field with a flux station.

The linked [EasyFluxWeb page](https://ugs.easyfluxweb.com/) showed a no-permission message for data downloads.
It also showed sign-in and new-user forms, plus station-level download controls.
This page check did not identify permissions or downloadable files for a named UFN crop station.
Treat direct UFN download access as unresolved.
No account was created, and no data request was sent.

The [University of Utah Level 1 page](https://horel.chpc.utah.edu/data/fluxwebsite/) displays raw data with added QC variables for UUCMF and UUPYF.
The page says its displays remain preliminary while QC procedures are refined.
The [UUNET station list](https://horel.chpc.utah.edu/uunet.html) identifies these as Compass Minerals and Playa flux sites.
These pages do not establish eligible cropland outcomes, daily `LE_CORR`, or the needed OpenET overlap.
Do not count them as external cropland groups.

UFN may provide one future external alfalfa site if its daily flux data, QC fields, OpenET support, and reuse terms can be confirmed.
One site would remain exploratory under the 20-group protocol.

## Access and data checks

The checked AmeriFlux configuration path is absent.
The process environment exposes no AmeriFlux variables.
The Earth Engine package is not installed.
The common Earth Engine credential and project paths are absent.
The AmeriFlux portal requires an account for data download.
It sends the stated use to site principal investigators and records the request.
Do not submit a download request until the user authorizes that notification.

The final protocol must select every eligible CC-BY-4.0 US cropland site before downloading outcomes.
It must record each site DOI, policy, location, year range, and distance from training sites.
It must verify that each site has daily `LE_CORR` and the required quality fields.
It must record the OpenET extraction method and spatial support.
Do not treat a point sample as a flux-footprint estimate.

## Minimum evidence for a confirmatory claim

Freeze each training arm before scoring external sites.
Use only the existing clean training cohort through 2021.
Fit the ten-member predictor and SupportGain selector without external labels.
Do not tune or refit after inspecting external outcomes.

Fit one ten-member ensemble per training arm.
Require at least 20 eligible spatial groups after the 25 km exclusion.
If the inventory has fewer groups, report the evaluation as exploratory.
Bootstrap the named MAE difference by spatial group.
Report OpenET, Full, Gain, and SupportGain errors for every site.
Report row counts, site counts, group counts, and quality exclusions.
Report all results, including adverse results.

The AmeriFlux CC-BY-4.0 license permits reuse with attribution.
The download portal asks for intended use and sends it to site PIs.
The policy states that CC-BY use does not require PI collaboration.
The [data policy](https://ameriflux.lbl.gov/data/data-policy/) describes these terms.
The [OpenET availability page](https://openet.gitbook.io/docs/additional-resources/data-availability) lists daily data coverage.
The [FLUXNET processing page](https://fluxnet.org/data/fluxnet2015-dataset/data-processing/) documents `LE_CORR`.
The [FLUXNET Shuttle license](https://data.fluxnet.org/data-policy-license-and-instructions-for-attribution/) permits reuse with attribution.
Its [download page](https://data.fluxnet.org/data/) records email and intended use before download.
