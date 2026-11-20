# Exp 55 — Biais favori/outsider sur marchés de prédiction réglementés — PRÉENREGISTREMENT

- **ID :** Exp 55 / `PRED-FAV-001`. Source : `docs/agents/research/H-R07_polymarket.md` (piste H-R07b). Préenregistré le 2026-10-06, figé par le commit qui ajoute ce fichier.
- **Préalable (étape 0) :** vérifier par sources officielles qu'IBKR ForecastTrader (ForecastEx) est accessible à un résident du Québec via IB Canada, quels contrats, frais, API. **Si non accessible : arrêt, pas de test.**

## Hypothèse

Sur Kalshi (même structure de contrats que ForecastEx), les contrats achetés au meilleur ask entre 0,80 et 0,95 $, 24 h avant la clôture, catégories Économie, Finance et Climat, rapportent plus que leur prix après frais preneur.

## Critères (fixés)

- Net par contrat ≥ **+1,5 %** après frais preneur Kalshi en vigueur à chaque date ;
- IC 95 % (erreurs groupées par événement) > 0 ;
- n ≥ 1 000 contrats ;
- signe positif séparément sur 2021-2024 et sur 2025-04 → 2026-09.
- **REJET** si net < +1 %, IC contient 0, ou signe inversé sur la période récente. **PASS** si tous les critères sont remplis ; **INCERTAIN** sinon.

## Variantes comptées

1 (fenêtre 24 h, bande 0,80-0,95). Rapportés sans effet : bandes 0,70-0,80 et 0,95-0,99, fenêtre 1 h.

## Si PASS

Enregistrer les carnets ForecastEx en lecture seule (4-8 semaines) pour vérifier que le biais et la liquidité existent sur ce venue, puis forward paper préenregistré.
