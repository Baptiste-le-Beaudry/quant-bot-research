# Exp 62 — Audit de l'edge de la stratégie A-Equity en exécution réaliste — PRÉENREGISTREMENT

- **ID :** Exp 62 / `A-EQ-AUDIT-001`. Demandé par l'auteur le 2026-10-07. Figé par ce commit, avant tout calcul. Juge : Validateur.
- **Contexte :** A-Equity a passé la découverte (9/15), la confirmation (12/16) et le HOLDOUT Exp 47 (14/15), mais **avec la convention de recherche** (sortie au prix du stop sur franchissement au close). Remplissage réaliste : PF 1,21 → ≈ 1,04 (0,02 % AR). Rejeu forward n = 42 avec entrée réelle : −0,065 %/trade, PF 0,81. HOLDOUT consommé : tout est **en échantillon** et ne peut que rejeter.

## Règles évaluées (mêmes entrées, config D, ledgers walk-forward existants des 15 actifs primaires + 16 de la Task E)

1. **D-STOP** : règle de config D (stop + trailing + sortie au temps) en harness v1.1 (entrée à l'open suivant, stop intrabar avec gaps, coût réel).
2. **D-TIME50** : mêmes entrées, sortie au temps 50 barres au close, sans stop (règle qui a sauvé l'edge crypto), sans dépasser la clôture de séance (sortie forcée à 15:59 ET).

## Coûts (vérifiés sur sources officielles, pour un compte de ≈ 500 CAD, ≈ 160 USD par position)

- **V1 IBKR Canada** (commission fixe/tiered avec minimum par ordre, + spread réel BID/ASK Dukascopy si disponible, sinon 0,02 % AR).
- **V2 courtier canadien sans commission avec API** (s'il en existe un ; sinon marqué « inexistant »), spread + conversion USD/CAD réelle.
- **V3 CFD actions** (Darwinex ou équivalent accessible au Québec), spread/commission officiels.

## Critères (fixés)

- **Edge réaliste** pour une règle et un venue = net moyen par trade groupé > 0 dans les deux moitiés chronologiques ET ≥ 50 % des actifs à net > 0 ET venue utilisable par un bot (API) depuis le Québec à ce budget.
- **PASS** si au moins une combinaison (règle × venue) a un edge réaliste. **REJET (pour 500 CAD)** sinon. Rapporté sans effet : PF, CAGR à 33 %/position, pire jour, budget minimal pour que V1 devienne positif.
- **Forward (descriptif, sans verdict) :** trades forward Equity depuis le refit (2026-10-01) en séparant avant/après D-04 (2026-10-07 02:46:25 UTC) ; distribution (probabilité, features clés, MAE/MFE, PnL, slippage d'entrée) comparée aux trades historiques.

## Variantes comptées

2 règles × 3 venues = 6 combinaisons décisionnelles (compteur de tests multiples : à corriger par le Validateur).
