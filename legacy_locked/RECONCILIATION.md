# Primary model reconciliation

## Locked primary
- Implementation: statsmodels logit `method='lbfgs', maxiter=500`
- n=3936, events=407
- RD Both vs Neither = 9.24 pp
- OR Both vs Neither = 2.80
- Bootstrap: B=1000, seed=20261014 → RD 9.24 (4.30 to 12.77)

## Discordant sensitivity re-fit
- Implementation: `method='newton'` (and related sensitivity helpers)
- RD = 7.60 pp; OR = 2.40
- Matches prior reported ~7.60 pp / ~2.40 OR

## Exact difference
Same patients, same variables, same design matrix and reference levels.
Only the MLE optimiser differed, moving the Both coefficient and therefore both OR and g-computation RD.
