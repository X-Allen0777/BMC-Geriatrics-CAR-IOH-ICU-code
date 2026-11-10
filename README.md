# CAR x intraoperative hypotension to early ICU admission — public analysis code

Reproducible analysis code accompanying a BMC Geriatrics revision using the
**INSPIRE** perioperative dataset (PhysioNet).

> **No patient-level data are redistributed in this repository.**

## INSPIRE access
- Version used for the locked re-run: **1.4.2**
- DOI: https://doi.org/10.13026/1eay-yc85
- URL: https://physionet.org/content/inspire/1.4.2/
- Requires PhysioNet credentialing, required training, and a signed DUA.

Place downloaded files under `data/inspire/` (see that folder's README).

## Quick start (credentialed users)
```bash
python -m venv .venv
pip install -r requirements.txt
copy config\config.example.json config\config.json
python analysis\rerun_pipeline.py --config config\config.json
```

## What is locked
- CAR cut: `0.0738095238`
- IOH: cumulative minutes with MAP < 65 mmHg >= 30
- MAP physiologic range: 20-250 mmHg
- Epoch grid: 5 minutes
- Analysis window: anaesthesia `[anstart_time, anend_time)`
- Primary bootstrap: B = 1000, seed `20261108`, percentile intervals

See `docs/INSPIRE_version_note.json` and `docs/MANIFEST.md`.

## License
MIT (code). INSPIRE data remain under the PhysioNet data-use agreement.


## Editorial verification (Comment 1)

See RUN_REPRODUCE.md for software requirements and the exact command:

`ash
python analysis/rerun_pipeline.py --config config/config.json
`

This regenerates the exposure audit, Table 2, Supplementary Table S3 inputs, and Supplementary Table S11.

Submission identifiers:
- GitHub: https://github.com/X-Allen0777/BMC-Geriatrics-CAR-IOH-ICU-code
- Release used previously: v1.0.0
- Commit: e81269f95104e0a82d0ec45105eb8a34686cb8a5
