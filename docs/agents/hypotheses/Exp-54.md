# Exp 54 — Achat de creux intraday sur métaux et énergie (calibré au domaine, sorties exécutables) — PRÉENREGISTREMENT

- **ID :** Exp 54 / `A-COMMOD-001` (Exp 52 et 53 restent réservées : queue de la sortie au temps, alignement du label). Demandé par l'auteur le 2026-10-06 (« aller voir d'autres marchés… l'or ou l'argent »).
- **Préenregistré :** 2026-10-06 par l'orchestrateur, figé par le commit qui ajoute ce fichier, **avant tout téléchargement ou modélisation**. Juge : Validateur.
- **Antécédents :** faisabilité 2026-10-05 (`docs/research_plan_status.md` « Feasibility probe — commodities », FEASIBLE, not started) ; Exp 32 (indices/forex : REJECT avec paramètres crypto inchangés) ; Strategy A-Equity (calibration au domaine qui a corrigé l'échec de population, `docs/strategy_a_equity/STRATEGY_A_EQUITY_SPEC.md`).

## Hypothèse

Le mécanisme d'achat de creux intraday sélectionné par modèle produit un edge net positif sur les matières premières liquides, où le coût par mouvement typique est 3-9x plus bas qu'en crypto, avec des sorties exécutables.

## Univers (fixé, critère exogène : toutes les matières premières Dukascopy 1m de la faisabilité)

XAUUSD, XAGUSD, WTI (`LIGHT.CMD-USD`), Brent (`BRENT.CMD-USD`), cuivre (`COPPER.CMD-USD`), gaz naturel (`GAS.CMD-USD`). Barres 1m BID **et** ASK Dukascopy, de 2012-01-01 (ou début des données) au 2026-09-30.

## Découpage

- **HOLDOUT verrouillé :** 2025-10-01 → 2026-09-30, jamais lu dans cette expérience (réservé à un test unique ultérieur, préenregistré séparément).
- Walk-forward sur le reste : TRAIN expansif depuis le début, TEST 3 mois, pas de 3 mois, premier TRAIN ≥ 3 ans.

## Modèle et sélection (repris de la config D Equity, sans réglage)

Mêmes features et mêmes deux modèles (RF et logistique) que `scripts/strategy_a_equity/own_asset_walkforward.py`, un modèle par instrument. Porte de sélection = top décile du score sur TRAIN, filtre range/vol calibré sur TRAIN comme config D. Label : rendement à 10 min > coût aller-retour médian **mesuré sur TRAIN** (spread ASK-BID médian).

## Exécution (exécutable, aucune convention optimiste)

Entrée à l'**ASK** à l'open de la barre suivant le signal ; sortie **au temps, 50 barres, au BID du close**, **sans stop** (règle déployée en crypto) ; une position à la fois par instrument ; heures de marché seulement (pas d'entrée si la sortie tombe après la clôture du jour de négociation de l'instrument). Coût = spread réel ASK/BID barre par barre **+ commission** dans deux scénarios : 0 (CFD/spread seul) et 0,005 %/côté.

## Critères (fixés)

- **Passe instrument :** PF net médian par pli > 1 pour **les deux modèles**, au scénario commission 0,005 %/côté, et ≥ 50 % des plis avec PF > 1.
- **PASS** = ≥ 3/6 instruments passent ET moyenne nette groupée par trade > 0 dans les deux moitiés chronologiques. **REJET** = ≤ 1/6 ou moyenne groupée ≤ 0. **PARTIEL** sinon.
- Rapporté sans effet sur le verdict : MFE/MAE, pire jour, nombre de trades/an, rendement à 33 % de notionnel par position.

## Variantes comptées

2 modèles × 2 scénarios de commission × 6 instruments ; 1 règle de sortie. Aucune autre variante.

## Si PASS

Étudier le venue (comment trader ces instruments depuis le Québec avec ~500 CAD : PAXG/XAUT sur Solana, ETF, futures micro, funded CFD), puis forward paper préenregistré, et HOLDOUT unique.
