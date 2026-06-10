# Standards Matrix

This seed matrix freezes the protocol-to-jurisdiction mapping for the China + Taiwan biodiversity survey platform. It is intentionally concise and is designed to drive field-form design, export profiles, and later backend validation work.

## Shared Rules

- Shared backend objects: `SamplingEvent`, `ObservationRecord`, `DesignAsset`, `TrackLog`, `MapPackage`, `ExportJob`.
- Shared jurisdiction values: `mainland_china`, `taiwan`.
- Shared programs: `terrestrial_vertebrates`, `plants`, `insects`.
- Shared export strategy: one converged backend, jurisdiction-specific export bundles.
- Shared offline rule: Android must support offline maps, cached taxonomy lookup, and local event/record capture for every protocol.

## Protocol Matrix

| Protocol | Jurisdiction | Required event fields | Optional event fields | Effort fields | Required record fields | Optional record fields | Export target |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `bird_line_transect` | mainland_china | transect name, transect length, survey round, start/end time, weather, observer count, route geometry | wind, cloud, precipitation, habitat, disturbance notes | distance walked, duration, pace | taxon, detection type, count, time | distance band, bearing, behavior, breeding code, flock size, route segment | mainland event summary + species list |
| `bird_line_transect` | taiwan | transect name, transect length, survey round, start/end time, weather, observer count, route geometry | wind, cloud, precipitation, habitat, disturbance notes | distance walked, duration, pace | taxon, detection type, count, time | distance band, bearing, behavior, breeding code, flock size, route segment | Taiwan event summary + species list |
| `bird_point_count` | mainland_china | point id, visit index, point duration, start/end time, weather, observer count, point geometry | radius, wind, cloud, precipitation, habitat | point duration, station count, travel distance | taxon, detection type, count, time | distance band, behavior, breeding code, point id, flock size | mainland event summary + species list |
| `bird_point_count` | taiwan | point id, visit index, point duration, start/end time, weather, observer count, point geometry | radius, wind, cloud, precipitation, habitat | point duration, station count, travel distance | taxon, detection type, count, time | distance band, behavior, breeding code, point id, flock size | Taiwan event summary + species list |
| `mammal_trap_net` | mainland_china | trap method, station count, deployment start/end, bait type, observer count | trap model, check interval, microhabitat, permit reference, welfare notes | trap nights, active trap count, checked station count | taxon, capture status, time, trap station id | mark, sex, life stage, body mass, release status, sample collected | mainland event summary + species list |
| `mammal_trap_net` | taiwan | trap method, station count, deployment start/end, bait type, observer count | trap model, check interval, microhabitat, permit reference, welfare notes | trap nights, active trap count, checked station count | taxon, capture status, time, trap station id | mark, sex, life stage, body mass, release status, sample collected | Taiwan event summary + species list |
| `herp_infrared_camera` | mainland_china | camera station id, camera action, deployment start/end, camera model, observer count | sensor mode, trigger interval, height, orientation, bait/lure, habitat | camera days, active camera count, file count | taxon, detection time, evidence type, camera station id | individual count, life stage, behavior, media file, sequence id, confidence | mainland event summary + species list |
| `herp_infrared_camera` | taiwan | camera station id, camera action, deployment start/end, camera model, observer count | sensor mode, trigger interval, height, orientation, bait/lure, habitat | camera days, active camera count, file count | taxon, detection time, evidence type, camera station id | individual count, life stage, behavior, media file, sequence id, confidence | Taiwan event summary + species list |
| `plant_quadrat` | mainland_china | plot id, plot area, plot shape, start/end time, observer count, plot geometry | canopy cover, slope, aspect, substrate, disturbance notes | sampled area, subplot count, duration | taxon, time | cover, height, DBH, abundance, phenology, specimen reference | mainland event summary + species list |
| `plant_quadrat` | taiwan | plot id, plot area, plot shape, start/end time, observer count, plot geometry | canopy cover, slope, aspect, substrate, disturbance notes | sampled area, subplot count, duration | taxon, time | cover, height, DBH, abundance, phenology, specimen reference | Taiwan event summary + species list |
| `plant_transect` | mainland_china | transect name, transect length, subplot count, start/end time, observer count, transect geometry | width, slope, aspect, dominant community, disturbance notes | sampled length, sampled area, duration | taxon, time | cover, height, DBH, abundance, phenology, subplot id | mainland event summary + species list |
| `plant_transect` | taiwan | transect name, transect length, subplot count, start/end time, observer count, transect geometry | width, slope, aspect, dominant community, disturbance notes | sampled length, sampled area, duration | taxon, time | cover, height, DBH, abundance, phenology, subplot id | Taiwan event summary + species list |
| `insect_transect` | mainland_china | transect name, transect length, start/end time, weather, observer count, route geometry | temperature, wind, cloud, habitat, microhabitat notes | distance walked, duration, sampled band width | taxon, count, time | life stage, behavior, microhabitat, route segment, capture/release flag | mainland event summary + species list |
| `insect_transect` | taiwan | transect name, transect length, start/end time, weather, observer count, route geometry | temperature, wind, cloud, habitat, microhabitat notes | distance walked, duration, sampled band width | taxon, count, time | life stage, behavior, microhabitat, route segment, capture/release flag | Taiwan event summary + species list |

## Standards Baseline by Protocol

| Protocol | Mainland China baseline | Taiwan baseline |
| --- | --- | --- |
| `bird_line_transect` | `HJ 710.4-2014`, 2018 county biodiversity survey regulations (birds) | official bird monitoring SOP + TaiCOL-backed taxonomy package |
| `bird_point_count` | `HJ 710.4-2014`, 2018 county biodiversity survey regulations (birds) | official bird monitoring SOP + TaiCOL-backed taxonomy package |
| `mammal_trap_net` | `HJ 710.3-2014`, 2018 county biodiversity survey regulations (mammals) | method-specific mammal form mapped to TaiCOL-backed taxonomy |
| `herp_infrared_camera` | `HJ 710.5-2014`, `HJ 710.6-2014`, 2018 county biodiversity survey regulations, 2024 infrared camera standard | amphibian monitoring SOP where applicable, plus method-specific reptile/herp camera form mapped to TaiCOL-backed taxonomy |
| `plant_quadrat` | `HJ 710.1-2014`, `HJ 710.14-2023`, 2018 county biodiversity survey regulations (plants) | method-specific vegetation form mapped to TaiCOL-backed taxonomy |
| `plant_transect` | `HJ 710.1-2014`, `HJ 710.14-2023`, 2018 county biodiversity survey regulations (plants) | method-specific vegetation form mapped to TaiCOL-backed taxonomy |
| `insect_transect` | 2018 county biodiversity survey regulations (insects) | method-specific insect transect form mapped to TaiCOL-backed taxonomy |

## Taxonomy Package Freeze

- Mainland seed packages:
  - `cn_mainland_terrestrial_vertebrates_seed`
  - `cn_mainland_plants_seed`
  - `cn_mainland_insects_seed`
- Taiwan seed packages:
  - `tw_terrestrial_vertebrates_seed`
  - `tw_plants_seed`
  - `tw_insects_seed`
- All packages use one internal taxon key with jurisdiction-specific status flags.
- Mainland packages are expected to support at least scientific names, simplified Chinese names, and English common names.
- Taiwan packages are expected to support at least scientific names, traditional Chinese names, English common names, and synonyms.

## Implementation Notes

- `Terrestrial vertebrates` are isolated in one module shell but keep protocol-specific forms.
- `Plants` and `Insects` stay isolated in their own module shells.
- All modules converge into the same backend event/record/export stream.
- This document is a seed alignment artifact, not the final legal compliance package. Later lanes can extend field dictionaries and exports, but they should not rename the seven protocol IDs or the two jurisdiction IDs frozen here.
