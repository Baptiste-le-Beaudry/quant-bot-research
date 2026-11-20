# Exp 52 — Contrôle de la queue de la sortie au temps sans stop serré — PRÉENREGISTREMENT

- **ID :** Exp 52 / `A-JUP-TAIL-001` (T-008). Source : `docs/agents/research/H-R02_controle_queue_sans_stop.md`, règle reprise **telle quelle** (paramètres tirés du budget, pas des données). Préenregistré le 2026-10-07, figé par ce commit, avant tout calcul. Juge : Validateur.

## Règle testée (CAPPED) contre la référence (UNCAPPED)

- **UNCAPPED :** règle déployée — entrées du modèle `A-CRYPTO-JUPITER-REFIT-20261005`, SOL+BTC+ETH, sortie au temps 50 barres sans stop, entrée open suivant, 33 % du compte par position, coût `/build`, compte 500 CAD (populations et harness identiques à l'Exp 57).
- **CAPPED :**
  - **Taille :** notionnel_i = min(33 % du compte, B / q_i), B = 2 % du compte ; q_i = mouvement défavorable sur 50 barres au quantile 99,5 % estimé sur TRAIN (P1 : pré-2021-11 ; P2 : tout P1), mis à l'échelle par realized_vol_30 au signal / médiane TRAIN de realized_vol_30.
  - **Rafale :** si une position est ouverte et qu'un **autre** symbole signale dans les 60 min suivant son entrée, la nouvelle position reçoit 0.
  - **Plancher :** pas de position < 20 USD.
- **Populations :** P1 pré-HOLDOUT (2021-11 → 2025-04) ; P2 entrées Exp 50. Rejet seulement.

## Critères (fixés, H-R02)

- **PASS** si, dans P1 **et** P2 : pire jour CAPPED ≥ −10 % ; net moyen par trade gardé ≥ 80 % de UNCAPPED ; rendement annuel CAPPED ≥ 50 % de UNCAPPED ; rendement/MaxDD CAPPED > UNCAPPED.
- **REJET** si pire jour CAPPED < −15 % dans P1 ou P2, ou si rendement/MaxDD ne s'améliore pas dans les deux périodes.
- **INCERTAIN** sinon.
- Rapporté sans effet : instance SOL seule (règle de taille seulement), part des trades réduits/supprimés, pire semaine.

## Variantes comptées

1. Aucune autre valeur de B, de quantile ou de fenêtre de rafale.

## Si PASS

Appliquer la règle de taille au paper Jupiter (décision D-NN), puis au réel éventuel.
