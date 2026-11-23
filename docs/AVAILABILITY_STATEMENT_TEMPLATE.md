# Availability of data and materials (paste into manuscript)

## Conservative (recommended until full raw-to-cohort extractors are public)

INSPIRE is available through PhysioNet to credentialed users who complete the required training and sign the data-use agreement (version 1.4.2: doi 10.13026/1eay-yc85; https://physionet.org/content/inspire/1.4.2/). Patient-level records cannot be redistributed by the authors. Aggregate supplementary results accompany this manuscript. Analysis code for the locked re-run—including exposure reconstruction, primary and sensitivity models, bootstrap estimation, and table/figure export—is publicly available at https://github.com/X-Allen0777/BMC-Geriatrics-CAR-IOH-ICU-code (release v1.0.1). Scripts used to assemble the analytic cohorts from credentialed INSPIRE extracts are included under `legacy_locked/`; because those extracts are derived under the PhysioNet data-use agreement, the corresponding intermediate cohort files are not redistributed in the public repository and are available to the editorial office on request for verification by credentialed users.

## Avoid overclaiming

Do not state “complete extraction, cleaning, cohort-construction … code” unless every
script that builds the upstream extract tables from raw INSPIRE files is also deposited.
