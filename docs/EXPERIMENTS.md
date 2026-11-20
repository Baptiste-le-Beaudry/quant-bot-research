# Toutes les expériences en un tableau (Exp 0 à 82)

*English summary: one line per experiment, in French. Verdict legend below.*

**Lecture rapide :**
- **Verdicts :** ✅ PASS ou gardé ; ❌ REJET ; ⚠️ incertain, fragile ou à nuancer ; ℹ️ diagnostic ou outil (pas un test).
- **« En échantillon » :** chiffre historique déjà vu. Il sert seulement à rejeter, jamais à confirmer.
- **Aucune expérience n'est confirmée en forward** à ce jour.
- **Détails :**
  - Exp 0 à 50 : [research_plan_status.md](research_plan_status.md), en anglais.
  - Exp 51 à 82 : [agents/REGISTRY.csv](agents/REGISTRY.csv), [agents/hypotheses/](agents/hypotheses/) et [agents/results/](agents/results/), en français.
  - Stratégies B et C : [strategy_b/](strategy_b/) et [strategy_c/](strategy_c/).

## 1. Stratégie A : achat de creux crypto (random forest), Exp 0 à 50

| Exp | Idée testée | Verdict |
|---|---|---|
| 0.1-0.2 | Reproductibilité et audit des dates | ✅ reproduction exacte |
| 1 | Stress : glissement, gaps, latence, funding | ⚠️ le backtest sans frottement surestime l'edge |
| 1b | Largeur du trailing stop | ✅ trailing élargi à 0,80 % (baseline V2) |
| 2 | Walk-forward de la baseline | ✅ ne contredit pas le découpage fixe |
| 3 | Diagnostic des trades par catégorie | ℹ️ aucune catégorie significative seule |
| 4 | Filtre de régime de volatilité | ✅ la concentration en haute volatilité est réelle |
| 5 | Seuil de probabilité du RF | ⚠️ 0,75 confirmé sur ETH ; piste 0,725 |
| 6 | Percentile du stop de protection | ❌ gain de p70 non robuste |
| 7 | Filtre des mauvais trades à l'entrée | ❌ non prévisible |
| 8 | Stress du seuil 0,725 | ❌ même fragilité que l'Exp 6 |
| 9 | Cible en régression | ❌ pas meilleure que la classification |
| 10 | Trades « sauvés » par la sortie flexible | ✅ la sortie flexible est nette positive |
| 11 | Trailing proportionnel à l'ATR | ⚠️ amélioration faible |
| 12 | Filtre de valeur espérée | ❌ ne passe pas le walk-forward |
| 13 | Asymétrie BTC/ETH sous stress | ℹ️ expliquée par la fenêtre de validation d'ETH |
| 14 | Portefeuille BTC+ETH | ✅ diversification réelle |
| 15, 17 | Multiplicateur de levier du portefeuille | ⚠️ utile jusqu'à ~1,2×, fragile au-delà (corrigé plus tard) |
| 16 | Moment d'entrée | ❌ l'entrée immédiate reste la meilleure |
| 18, 20, 21 | Taux de funding comme feature | ❌ ne passe pas le walk-forward |
| 19 | Taille de position dynamique | ❌ aucune méthode n'améliore les deux symboles |
| 22, 23, 25 | Zone de liquidation et levier dynamique | ⚠️ le levier dynamique protège, sans ajouter d'edge |
| 24 | Classifieur tendance/range × volatilité | ❌ pas de cellule exploitable |
| 26 | Risque par trade + Monte-Carlo | ℹ️ refait plus tard avec un moteur corrigé |
| 27-28 | Seuil 0,70 + filtre obligatoire | ✅ amélioration robuste (baseline V3) |
| 29-30 | Horizon du label (5 à 60 min) | ❌ 20 min ne passe pas sur les deux symboles |
| 31 | Contrôle sur données neuves, choix A/B | ✅ A étendue plutôt qu'une stratégie B |
| 32 | V3 appliquée telle quelle au Nasdaq, au S&P 500 et à l'EURUSD | ❌ PF < 1 partout |
| 33 | Extension à 6 autres cryptos | ✅ portefeuille de 8 à 9 symboles (en échantillon) |
| 34 | Retour sur SOL/AVAX | ⚠️ faiblement favorable |
| 35-36 | Stop XRP p80, stop LINK p95 | ✅ gardés (en échantillon) |
| 37-39 | Transfert à ETC, TRX, DOT | ⚠️ ETC et DOT PASS, TRX REJET |
| 40-42 | Filtres de choc BTC, retrait de symboles | ❌ |
| 43-46b | Durée de sortie, extension adaptative | ❌ la sortie à 50 min est confirmée |
| 47 | A-Equity : test unique sur HOLDOUT | ✅ 14/15 (mais frais trop lourds pour 500 CAD : Exp 62) |
| 48 | Confirmation par la largeur du marché crypto | ❌ |
| 49 | Walk-forward crypto sur la fenêtre HOLDOUT | ✅ 7/9, convention recherche (sorties non exécutables) |
| 50 | Sortie exécutable à 50 min | ⚠️ PARTIEL : positive à coûts bas, négative à 0,17 % ; pire jour −41 % sans stop |
| — | **Audit de remplissage réaliste** | ❌ **PF 1,38 → 0,95 avec des stops remplis comme à la bourse** |

## 2. Stratégie B : momentum et cassures (août 2026)

| Test | Idée | Verdict |
|---|---|---|
| B1-B8 | Cassure + expansion de volatilité + volume sur BTC/ETH, filtres de tendance, 15 min, squeeze, déséquilibre acheteurs/vendeurs | ❌ PF ≤ 1 |
| B_FUNDING | Extrêmes de funding (instantanés et persistants) | ❌ |
| B_ROTATION | Rotation transversale entre cryptos (meilleurs et pires) | ❌ battue par le panier égal |
| B_INDEX | Dérive et cassures d'ouverture sur le Nasdaq 100 | ❌ 3 tests indépendants |

## 3. Stratégie C : microstructure SPY/QQQ

| Test | Idée | Verdict |
|---|---|---|
| C1 | Déséquilibre du carnet → continuation (QQQ) | ❌ |
| C2 | Retournement (piste de C1), confirmé sur SPY | ❌ le signe s'inverse entre QQQ et SPY |

## 4. Variantes de la stratégie A sur Jupiter (Solana), Exp 51 à 63

| Exp | Idée | Verdict |
|---|---|---|
| 51 | Creux après baisse de l'open interest | ⚠️ incertain (signes opposés) |
| 52 | Contrôle de la queue de pertes sans stop | ❌ rendement 26 % → 3,6 %/an |
| 53 | Label aligné sur la sortie à 50 min | ❌ |
| 54 | Métaux et énergie (or, argent, pétrole, gaz, cuivre) | ❌ 0/6 |
| 55 | Favoris des marchés de prédiction (Kalshi) | ❌ net −9,5 % |
| 56 | Momentum journalier crypto | ❌ dépend d'un marché haussier |
| 57 | Ajouter cbBTC et WETH à SOL | ✅ mécanique, faible puissance |
| 58 | Seuil de probabilité | ⚠️ fragile |
| 59 | Creux mesuré contre le marché | ❌ |
| 60 | Filtre de régime SMA20 | ❌ signe inversé hors échantillon |
| 61 | Autres jetons Solana | ❌ 0/6 |
| 62 | A-Equity avec les frais réels d'un courtier | ❌ frais 0,46 % ≫ edge 0,03-0,05 % |
| 63 | Attendre la confirmation du rebond | ❌ |

## 5. Futures et challenges « funded », Exp 64 à 73

| Exp | Idée | Verdict |
|---|---|---|
| 64-65 | Momentum dans la zone de bruit intraday (S&P 500, Nasdaq) | ⚠️ seul le Nasdaq est positif ; drawdown trop grand |
| 66 | Effets d'heure en crypto | ❌ |
| 67 | Forward papier MNQ | ℹ️ contrôle en cours |
| 68 | Tendance crypto long/cash | ❌ |
| 70 | Filtre GEX sur MNQ | ❌ |
| 71 | Réplication sur MYM et M2K | ❌ MNQ probablement chanceux |
| 72 | Fade de la cassure d'ouverture (30 min) | ❌ |
| 73 | Direction MNQ contre des entrées au hasard | ⚠️ gain venu de 5 jours |

## 6. Allocation indicielle (viser ~15 %/an), Exp 74 à 80

| Exp | Idée | Verdict |
|---|---|---|
| 74 | S&P ×2 + filtre moyenne mobile 200 jours | ⚠️ PASS, mais le gain vient du levier, pas d'un edge |
| 75 | Volatilité ciblée | ❌ |
| 76 | Actions + suivi de tendance empilés | ⚠️ nul après publication |
| 77-80 | 4 stratégies maison (atelier, validation unique 2010-2026) | ❌ aucune ne bat le S&P à levier égal |

## 7. Effets « qui est de l'autre côté », Exp 81 et 82

| Exp | Idée | Verdict |
|---|---|---|
| 81 | Saison REER : TSX contre S&P 500 | ❌ prédiction UK fausse |
| 82 | Fenêtre de prix des rabais DRIP des banques canadiennes | ⚠️ PASS mécanique, fragile ; veille papier seulement |
