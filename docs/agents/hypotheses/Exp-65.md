# Exp 65 — Momentum zone de bruit sur MNQ seul, test unique sur le HOLDOUT indices — PRÉENREGISTREMENT

- **ID :** Exp 65 / `F-NOISE-MOM-MNQ-001`. Préenregistré le 2026-10-08 par l'orchestrateur, figé par ce commit, **avant tout calcul sur le HOLDOUT**. Juge : Validateur.
- **Origine (post hoc, à pénaliser) :** l'Exp 64 n'a pas pu réussir (Sharpe net P1 SP500 = 0,23 < 0,5), mais NASDAQ100 → MNQ donne un Sharpe net de 0,97 en P1, en échantillon (coûts = 26 % du brut, pire jour −624 USD, MaxDD −1 548 USD). MNQ a été choisi **après** avoir vu P1 : les critères sont donc plus sévères que ceux de l'Exp 64.
- **Décision HOLDOUT (orchestrateur) :** le HOLDOUT positionnel des fichiers indices (derniers 20 % des lignes, `scripts/nasdaq_baseline_test.py` ; NASDAQ100 à partir du 2024-03-05 12:21 UTC) est consommé **une seule fois**, par cette expérience. Il n'est pas consommé pour l'Exp 64, dont le PASS était déjà exclu.

## Règle et exécution

Identiques à l'Exp 64, sans aucun changement : moteur `scripts/agents/exp64_noise_momentum.py` et lecture de l'article figée au commit 33b5a15. Seule la fenêtre change : `--holdout-decision docs/agents/hypotheses/Exp-65.md`. 1 contrat MNQ, coût de 2,22 USD aller-retour.

## Périodes

- **H** = HOLDOUT NASDAQ100 complet, du 2024-03-05 à la fin des données.
- **H-post** = du 2024-11-27 à la fin (après la publication de l'article).

## Critères (fixés)

- **PASS** si, sur MNQ :
  - Sharpe net ≥ 0,7 sur H ;
  - Sharpe net ≥ 0,5 sur H-post, avec plus de 200 jours tradés ;
  - pire jour > −1 000 USD (limite journalière Topstep) ;
  - MaxDD > −2 000 USD (drawdown maximal Topstep 50K).
- **REJET** si le Sharpe net est ≤ 0,3 sur H, ou ≤ 0 sur H-post.
- **INCERTAIN** sinon.
- **Rapporté sans effet :** SP500 → MES sur son HOLDOUT, ce qui donne au passage le verdict P2 de l'Exp 64 ; Sharpe calculé sur le % du notionnel ; résultat par année.

## Si PASS

1. Bootstrap des jours nets dans les règles Topstep et Lucid (`docs/agents/venues/funded_futures_ev_sim.py`).
2. Au moins 3 mois de forward papier MNQ sur flux live depuis le PC de l'auteur.
3. Ensuite seulement, demander à l'auteur un « go » pour un challenge.

**Si REJET :** la piste des indices funded est fermée.
