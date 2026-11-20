# Exp 64 — Momentum intraday « zone de bruit » (Zarattini-Aziz-Barbon 2024) sur MES/MNQ, coût funded futures — PRÉENREGISTREMENT

- **ID :** Exp 64 / `F-NOISE-MOM-001` (T-050, proposition H_F1 de `venues/FUNDED_FUTURES_2026-10-08.md`). Préenregistré le 2026-10-08 par l'orchestrateur, figé par ce commit, **avant tout calcul**. Juge : Validateur.
- **Contexte :** chez Topstep ou Lucid (Québec admis, bot autorisé), le coût d'un aller-retour MES/MNQ est d'environ 0,004-0,01 % du notionnel. Les frais ne bloquent donc plus les stratégies indices. La question qui reste est celle de l'edge.

## Règle (celle de l'article, sans réglage)

« Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY) », Zarattini, Aziz, Barbon (2024, SSRN) :
- **Bornes de bruit** : ouverture du jour × (1 ± σ_min), où σ_min est la moyenne sur 14 jours du mouvement absolu depuis l'ouverture à la même minute. Borne haute ajustée par max(ouverture, clôture de la veille), borne basse par min(…), comme dans l'article.
- **Décision** toutes les 30 min, de 10:00 à 15:30 ET : position longue si le prix est au-dessus de la borne haute, courte s'il est sous la borne basse, sinon à plat.
- **Stop suiveur** : la borne du côté de la position ou le VWAP, selon le plus proche, comme dans l'article.
- **Sortie** à 15:59 ET au plus tard.
- **1 contrat fixe**, sans le levier dynamique de l'article.

Si un détail de l'article est ambigu, le développeur prend la lecture la plus littérale, la consigne dans le rapport **avant** de calculer, et ne la change plus.

## Exécution

- Données : Dukascopy USA500 → MES, USATECH → MNQ, en 1 minute (`data/indices/`). **Vérifier d'abord les bornes HOLDOUT** de ces fichiers au REGISTRY et les respecter.
- Entrée à l'ouverture de la barre suivant la décision. **Sortie de stop à l'ouverture de la barre suivant le franchissement**, jamais au niveau du stop.
- Coût : 1,22 USD aller-retour + 1 tick par côté (MES : 1,25 USD/tick ; MNQ : 0,50 USD/tick). Multiplicateurs : MES 5 USD/pt, MNQ 2 USD/pt.
- Les demi-séances et les jours sans données complètes sont exclus.

## Périodes

- **P1** = 2012-01 → 2024-10 (réplication, en échantillon de l'article).
- **P2** = 2024-11-27 → fin des données (après publication : la seule vraie hors-échantillon).

## Critères (fixés)

- **PASS** : Sharpe net annualisé ≥ 0,5 dans P1 **et** P2, sur USA500 **et** USATECH, avec plus de 200 jours tradés en P2.
- **REJET** : Sharpe net ≤ 0 en P2 sur au moins un des deux indices, ou Sharpe net < 0,5 en P2 sur les deux.
- **INCERTAIN** sinon.
- **Rapporté sans effet** : rendement net par jour en USD et en % du notionnel, MaxDD en USD, pire jour face à la limite journalière de Topstep, part du brut mangée par les coûts, Sharpe brut.

## Variantes comptées

2 au total : la règle de l'article (décisionnelle) + une alternative rapportée **sans effet sur le verdict** (momentum de la dernière demi-heure, Gao et al. : signe du rendement de 9:30 à 15:30, position de 15:30 à 16:00).

## Si PASS

1. Rejouer la série quotidienne nette, par bootstrap par blocs, dans les règles Topstep et Lucid (`funded_futures_ev_sim.py`).
2. Faire au moins 3 mois de forward papier sur flux live.
3. Ensuite seulement, demander un « go » à l'auteur pour un challenge.

**Si REJET :** la piste des indices funded est fermée.
