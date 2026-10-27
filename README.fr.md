# quant_bot — un bot de recherche qui n'a pas trouvé d'edge exploitable (et qui explique pourquoi)

*[English version: README.md](README.md)*

Un bot de recherche complet, crypto et actions : features, modèles d'arbres (random forest, XGBoost, base logistique), moteur de backtest, harness d'exécution réaliste, runners papier, et **toutes les expériences, y compris les rejetées**.

**Verdict d'entrée :** après environ 80 expériences, **aucun edge net, exécutable et confirmé en forward n'existe** pour un petit compte. L'edge brut trouvé (quelques centièmes de pour cent par trade) est de la même taille que les coûts et l'erreur de remplissage réalistes.

> Papier seulement. Pas un conseil financier. Aucun ordre réel n'est passé.

## La leçon principale

2 549 trades, facteur de profit **1,38** au backtest. Mêmes trades avec des stops remplis comme à la bourse : **0,95**. Actions : 1,21 vers environ 1,04. Voir `docs/SCIENTIFIC_VALIDATION_AUDIT.md` et [fill-reality-check](https://github.com/Baptiste-le-Beaudry/fill-reality-check).

## Pourquoi c'est si difficile

- **Coûts de la taille de l'edge.** Edge brut d'environ 0,11 à 0,35 % par trade ; coûts aller-retour réalistes d'environ 0,05 à 0,25 %. Courtiers actions : environ 0,46 % contre 0,03 à 0,05 % d'edge (Exp 62 : rejeté).
- **Puissance statistique.** Environ 1 165 trades (5,5 ans) pour confirmer un edge de 0,11 % par trade.
- **Remplissages.** Stop testé sur le close mais rempli au niveau du stop, gaps ignorés, signaux pris sur des trous de données.
- **HOLDOUT brûlé.** Un holdout déjà vu ne peut que rejeter.
- **Edge seul n'est pas edge de portefeuille**, et effets de sélection (beaucoup de variantes sur un seul historique).

## Ce qui a été testé

Journal complet : `docs/research_plan_status.md` (Exp 0-36) et `scripts/agents/` (Exp 52-82).

La plus prometteuse : **Stratégie A** (rebond sur creux crypto, random forest et filtre de volatilité, sortie à 50 min sur SOL : +0,146 % par trade, PF 1,21 en échantillon). Avec un remplissage réaliste, environ 0 net, non confirmée en forward. Stratégie A-Equity : edge réel en walk-forward mais rejetée pour 500 CAD après frais. Stratégies B (momentum), C (microstructure), extension d'univers, timing de sortie, matières premières, marchés de prédiction : rejetées.

## Les modèles

`quant_bot/signal/model.py` (logistique, random forest, XGBoost), `quant_bot/features/`, `quant_bot/backtest/`, `quant_bot/execution_harness/`, `quant_bot/forward/` (papier, `live_enabled=false`), `scripts/` (une expérience par script), `scripts/audit/` (scanners de bugs).

## Lancer

```bash
pip install -r requirements.txt
python -m pytest -q
```

Les données ne sont pas incluses (voir `SPEC.md`). Code de recherche : certains scripts demandent des jeux de données à télécharger.

Licence MIT.
