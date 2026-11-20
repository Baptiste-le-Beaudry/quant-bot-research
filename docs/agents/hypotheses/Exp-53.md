# Exp 53 — Aligner le label (10 min) sur la sortie réelle (50 min) — PRÉENREGISTREMENT

- **ID :** Exp 53 / `A-JUP-LABEL50-001` (T-009). Préenregistré le 2026-10-07 par l'orchestrateur, figé par ce commit, **avant tout calcul**. Juge : Validateur.
- **Constat (STATE point 13) :** le modèle déployé (`scripts/build_jupiter_refit_bundle.py`) apprend `fwd_10min > COST_THRESHOLD_PCT (0,12 %)` mais la position est tenue 50 barres sans stop. Le modèle n'optimise donc pas le gain réellement encaissé.

## Hypothèse

Un RandomForest identique (mêmes features, `prune_redundant` 0,9, 100 arbres, échantillon 250 000, BTC+ETH groupés, filtres range_pos_60/realized_vol_30 à la médiane des sélectionnés sur TRAIN) entraîné sur le label **`fwd_50min > 0,12 %`** produit un net par trade plus élevé que le modèle de référence (label 10 min), avec la règle d'exécution déployée.

## Protocole (fixé)

- **Deux modèles par pli**, mêmes plis, mêmes données : **REF** (label 10 min, seuil de probabilité 0,70 comme déployé) et **L50** (label 50 min). Seuil de L50 fixé **sur TRAIN** pour obtenir le même nombre de signaux par jour que REF sur TRAIN (isole la qualité du label, pas le nombre de trades). Aucun autre réglage.
- **Plis :** walk-forward TRAIN expansif / TEST 3 mois, de 2021-11 à 2026-08-17 (HOLDOUT crypto déjà vu : sert à rejeter, pas à confirmer). **P1** = tests 2021-11 → 2025-04 ; **P2** = tests 2025-04 → 2026-08-17.
- **Exécution :** harness v1.1.0 (`quant_bot/execution_harness/`), symboles SOL, BTC, ETH (barres Binance), entrée à l'open de la barre suivante, sortie au temps 50 barres au close, **sans stop**, une position par symbole, coût `/build` (≈ 0,02 % AR + 0,01 USD par swap), compte 500 CAD, 33 %/position.

## Critères (fixés)

Δ = net moyen par trade (L50 − REF), groupé SOL+BTC+ETH.
- **PASS** : Δ ≥ +0,03 point dans P1 **et** P2 ; net moyen L50 > 0 dans P1 et P2 ; Δ > 0 pour ≥ 2 symboles sur 3 dans les deux périodes.
- **REJET** : Δ ≤ 0 dans P1 ou dans P2.
- **INCERTAIN** sinon.
- Rapporté sans effet : nombre de trades, PF, CAGR et MaxDD du compte, pire jour, variante L50 au seuil fixe 0,70, coût `/order`.

## Variantes comptées

1 décisionnelle (L50 à fréquence égale). Rapportée sans effet : L50 seuil 0,70, coût `/order`.

## Si PASS

Nouvelle instance paper Jupiter avec le modèle L50 (préenregistrée, règle d'arrêt type D-05), à côté de l'instance actuelle — pas de remplacement sans forward.
