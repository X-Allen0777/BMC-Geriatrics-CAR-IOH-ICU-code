# -*- coding: utf-8 -*-
"""MICE specification note aligned to the locked Model 3 Clinical primary model.

Scope (reconciled):
- Multiple imputation is applied ONLY among operations with non-missing CAR
  (CAR-available analytic universe), for missing Model 3 covariates.
- Imputation does NOT restore patients missing CAR and therefore does not remove
  selection associated with CRP/albumin testing.

Variable handling:
- Continuous: age, op_duration_min, creatinine, bmi, hb, glucose, (albumin if used
  only to derive CAR upstream — CAR itself is not imputed here)
- Binary: female, emop, general_anes
- Ordinal: ASA physical status — imputed on the numeric 1–5 scale used in the
  primary model (entered linearly, not as dummy indicators), then rounded to
  nearest integer in {1,2,3,4,5} after imputation draws
- Categorical: proc_axis — imputed as polytomous (joint_arthroplasty / spine /
  other_orthopedic); phenotype is derived after imputation from locked CAR cut
  and map65_min (CAR cut and IOH threshold held fixed; not re-estimated inside MICE)

Analysis after imputation:
- Fit the SAME locked Model 3 formula and lbfgs settings on each imputed dataset
- Combine logit coefficients with Rubin's rules for the Both vs Neither OR
- Optionally pool g-computation RDs by imputing then standardising within each
  completed dataset and combining point estimates with Rubin's rules

This file is a specification companion; run with mice / sklearn IterativeImputer
or equivalent in the public repository release.
