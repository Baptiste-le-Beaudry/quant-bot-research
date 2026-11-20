# H-R03 — Creux de « déleveraging » (open interest en baisse) vs creux de nouvelles positions vendeuses (open interest en hausse)

- **Auteur** : agent Chercheur, tâche T-010, 2026-10-06
- **Type** : information nouvelle pour le signal (filtre ou multiplicateur de taille)
- **Classement** : 3/6 (gain attendu élevé si vrai ; probabilité modérée ; rejet en échantillon rapide et gratuit ; confirmation forward lente sauf si l'écart entre terciles est grand : avec σ ≈ 1,6 %/trade (T-007), un écart de 0,15 pt reste difficile à confirmer en forward, il faut un écart ≥ 0,4 pt ou une baisse nette de σ pour un verdict en moins d'un an)
- **Statut** : non testée. **Débloque une piste déjà jugée prioritaire mais crue impossible faute de données.**

## Mécanisme

Un creux intraday peut venir de deux flux très différents :

- **Ventes forcées / déleveraging** : des longs à levier sont liquidés ou réduisent. Le flux vendeur
  est non informationnel (contrainte de marge), l'open interest (OI) **baisse** pendant la chute.
  Da, Liu et Schaumburg (2014) montrent que seule la composante « non fondamentale » des mouvements
  de prix se retourne à court terme, et que côté acheteur le reversal rémunère des **chocs de
  liquidité**. Kitron et Wengrowicz (2026) trouvent en crypto un reversal à 15 min présent sur 90 %
  de 183 paires Binance, qui **grandit avec l'intensité du flux taker agressif** et n'est pas
  conditionné par la profondeur consommée : rémunération de la fourniture de liquidité, pas
  sélection d'information. De Nicola (2021) attribue l'autocorrélation négative intraday du BTC à la
  surréaction, à la volatilité excessive et aux **liquidations en cascade**.
- **Nouvelles positions vendeuses** : l'OI **monte** pendant la chute ; des vendeurs ouvrent des
  shorts, potentiellement informés. Pas de raison de rebond, risque de continuation.

Notre RandomForest ne voit ni l'OI ni les liquidations (features : prix, volatilité, volume,
`taker_imbalance_20` ; `quant_bot/features/build.py`). Le rapport de décomposition de l'alpha
(`docs/strategy_a/STRATEGY_A_ALPHA_DECOMPOSITION.md`, ligne « Open interest (change in OI) ») avait
déjà classé cette variable « plausiblement très informative » mais l'avait écartée parce que
l'endpoint gratuit de Binance ne garde que ~30 jours.

**Fait nouveau (vérifié le 2026-10-06)** : l'archive publique `data.binance.vision`
(`/data/futures/um/daily/metrics/<SYMBOL>/<SYMBOL>-metrics-<date>.zip`) fournit l'OI USDT-M toutes
les **5 minutes**, au moins depuis le **2020-10-01** (HTTP 200 vérifié pour BTCUSDT 2020-10-01,
2021-06-01, 2021-12-01 ; SOLUSDT 2021-12-15, 2022-11-08, 2025-10-10 ; 288 lignes/jour). Colonnes :
`create_time, symbol, sum_open_interest, sum_open_interest_value, count_toptrader_long_short_ratio,
sum_toptrader_long_short_ratio, count_long_short_ratio, sum_taker_long_short_vol_ratio`.
L'archive des liquidations (`liquidationSnapshot`) renvoie 404 pour les dates testées : l'OI reste
le proxy disponible.

## Prédiction chiffrée et testable

Variable : ΔOI_15 = variation relative de `sum_open_interest` sur les 15 minutes précédant le signal,
en n'utilisant que des valeurs horodatées ≤ signal − 5 min (latence de publication à vérifier).

Parmi les entrées déjà sélectionnées par le modèle (sortie TIME50_NOSTOP, remplissage réaliste) :

1. Le tercile ΔOI_15 le plus négatif (déleveraging) a un rendement moyen à 50 min supérieur d'au
   moins **0,15 point** au tercile ΔOI_15 le plus positif.
2. Le signe tient dans les **deux moitiés chronologiques** et sur **≥ 5/9 symboles** (et 3/3 pour
   SOL/BTC/ETH, l'univers Jupiter).
3. Bonus de mécanisme : le tercile « OI en hausse » concentre une part disproportionnée des
   trades < −5 % (queue), ce qui relie cette fiche à H-R02.

Rejet si (1) ou (2) échoue. Aucune recherche de seuil ou de fenêtre (15 min fixée ici ; 5 et 60 min
seulement rapportées).

## Pourquoi survivrait aux coûts réels à 500 CAD

Pas d'ordre supplémentaire. Si la prédiction est vraie, on retire ou réduit le tiers de trades le
moins bon : le rendement moyen par trade monte (≥ +0,05 pt attendu si l'écart de terciles est
de 0,15 pt), ce qui élargit la marge au-dessus du coût Jupiter (0,01-0,05 % AR selon H-R01). Le
nombre de trades baisse d'un tiers : les frais fixes Solana par trade restent < 0,01 %.

## Comment tester

- **Rejet rapide (en échantillon, historique = rejet seulement)** : télécharger les fichiers
  `metrics` pour les 9 symboles (≈ 2 000 fichiers/symbole, quelques Mo chacun) **dans un répertoire
  neuf et isolé**, fusion causale `merge_asof(direction="backward")` avec garde de 5 min ; tableau
  par terciles sur le registre pré-HOLDOUT re-sorti en TIME50_NOSTOP puis sur les entrées Exp 50.
  Diagnostic seulement, comme l'Exp 41 (pas de filtre construit si le diagnostic échoue).
- **Écart de source** : en live, le signal vient d'OKX (STATE point 12). L'OI d'OKX est disponible
  par API publique ; il faut vérifier que ΔOI OKX et ΔOI Binance ont le même signe sur la plupart
  des signaux (lien T-012) avant toute utilisation live.
- **Confirmation** : forward paper avec ΔOI_15 enregistré à chaque signal (sans filtrer) pendant
  quelques mois ; le verdict se lit sur les terciles forward.

## Anti-doublon

- Exp 18/20/21 : **funding** comme feature (moyenne 24 h), INVESTIGATE, non promu ; B_FUNDING :
  stratégie de funding extrême, CLOSED/REJECT. Le funding mesure le positionnement sur 8-24 h, pas
  le flux de la dernière demi-heure. Aucun test d'OI, de liquidations ou de ratio long/short
  n'existe dans `docs/research_plan_status.md`, `REGISTRY.csv` ou `docs/strategy_b/`.
- Exp 41 / 48 : largeur de choc et co-occurrence d'entrées, pas de positionnement à levier.
- `taker_imbalance_20` est déjà une feature : la prédiction porte sur l'OI, qui distingue ouverture
  et fermeture de positions, ce que le déséquilibre taker ne fait pas.

## Risques et limites

- Sémantique de `create_time` (début ou fin de la fenêtre de 5 min ?) et latence de publication à
  établir avant tout calcul : un décalage de 5 min introduit une fuite.
- L'OI agrège tous les comptes : une baisse peut venir de shorts qui rachètent (rebond déjà en
  cours), d'où le besoin de conditionner sur le prix (creux) ; c'est le cas par construction ici.
- Pour SOL, la part du marché à levier sur Binance a changé dans le temps ; le signe peut ne pas
  être stationnaire (cf. Exp 42 : effets de régime).

## Sources (consultées le 2026-10-06)

- Z. Da, Q. Liu, E. Schaumburg (2014), *A Closer Look at the Short-Term Return Reversal*, Management Science 60(3) : https://pubsonline.informs.org/doi/10.1287/mnsc.2013.1766 ; version NY Fed : https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr513.html
- N. A. Kitron, J. M. Wengrowicz (2026), *Short-horizon mean reversion in cryptocurrency markets: a matched cross-market measurement*, arXiv:2608.21888 : https://arxiv.org/abs/2608.21888
- G. De Nicola (2021), *On the Intraday Behavior of Bitcoin*, Ledger 6 : https://epub.ub.uni-muenchen.de/97651/
- R. M. Garcia Seuma (2026), arXiv:2607.27070 (OI et flux taker à 5 min autour de 7 cascades) : https://arxiv.org/abs/2607.27070
- Archive Binance (vérifiée par requêtes HTTP le 2026-10-06) : https://data.binance.vision/data/futures/um/daily/metrics/SOLUSDT/SOLUSDT-metrics-2025-10-10.zip
- Interne : `docs/strategy_a/STRATEGY_A_ALPHA_DECOMPOSITION.md` (tableau des données candidates), `quant_bot/data/download_funding_oi.py` (limite de 30 jours de l'endpoint REST).
