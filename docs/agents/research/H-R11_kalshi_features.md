# H-R11 — Marchés Kalshi de prix (BTC, ETH, SOL, S&P 500, Nasdaq) : feature, filtre ou stratégie ?

- **Auteur** : agent Chercheur, tâche T-032, 2026-10-07
- **Type** : information nouvelle pour le signal (feature/filtre) ; autre marché (stratégie propre)
- **Classement** : **dernier rang** de l'INDEX (après H-R06). Stratégie propre : **écartée**
  (inaccessible au Québec). Feature : **pas de piste sérieuse**. Une seule hypothèse résiduelle
  (H-R11a) peut être rejetée à faible coût, avec une probabilité a priori ≤ 5 %. **Ne pas la lancer
  avant H-R03/H-R04/H-R09.**
- **Statut** : non testée. Un calcul exploratoire de lead-lag à la minute a été fait (§3). Il ne
  compte pas.

## Verdict court

1. **Stratégie propre : non.** Les contrats crypto et indices de Kalshi sont horaires, à 15 min ou
   journaliers. Le Règlement 91-102 interdit au Québec d'offrir à un particulier une option binaire
   de moins de 30 jours. Le contrat de membre de Kalshi exclut le Canada. La voie canadienne,
   Wealthsimple Predict, est limitée aux contrats d'au moins 30 jours (H-R07, Exp 55). La seule
   inefficacité documentée sur ces marchés est un arbitrage de latence de l'ordre de 300 ms. Il est
   réservé aux bots colocalisés, et encore : il ne bat pas le carnet (§2).
2. **Feature : pas de piste, sauf un test de rejet bon marché.**
   - La littérature trouve que le spot (Binance) **mène** les marchés de prédiction crypto, et que
     le carnet du marché de prédiction contient déjà toute l'information exploitable (OpenMarket,
     2026).
   - Notre calcul exploratoire va dans le même sens. Sur 3 × 96 marchés à 15 min, la variation
     minute de la probabilité Kalshi est fortement corrélée au rendement Binance **de la même
     minute** (0,59 à 0,74). Elle n'est pas significativement corrélée au rendement de la minute
     suivante (|t| ≤ 1,1 à +1 min).
   - Kalshi **suit** le spot. Il ne l'anticipe pas.
3. **Données locales (`data/kalshi/`) : inutilisables pour ce sujet.**
   - **Aucune série crypto.** Exp 55 a exclu la catégorie Crypto.
   - Les séries S&P 500 et Nasdaq-100 ne sont présentes que pour un échantillon aléatoire de 6,3 %
     des marchés, en chandeliers **horaires**, et seulement sur les derniers jours avant la clôture.
   - Les chandeliers **minute** existent en revanche, gratuitement et sans clé, par l'API publique
     de Kalshi (vérifié).

## 1. Marchés Kalshi pertinents (sources consultées le 2026-10-07)

Source principale : API publique `https://api.elections.kalshi.com/trade-api/v2`, sans
authentification. Elle donne `series`, `events`, `markets`, `candlesticks` et `historical/*`. Les
volumes sont en **contrats**, chacun réglé à 1 USD au plus.

### Séries, fréquence et début de l'historique

Les dates de début sont tirées de `/events?status=settled` (premier `strike_date`, comptage
exhaustif par pagination). La série Kalshi `KXINX15M` existe, mais `/events` ne renvoie aucun
événement réglé.

| Actif | Série | Contrat | Fréquence | Début (`strike_date`) | Événements réglés |
|---|---|---|---|---|---:|
| BTC | `KXBTCD` | au-dessus/au-dessous d'un seuil à HH:00 ET (échelle de 40 à 190 seuils) | horaire | 2024-06-10 | 12 637 |
| ETH | `KXETHD` | idem | horaire | 2024-06-07 | 12 637 |
| SOL | `KXSOLD` | idem | horaire | **2025-12-09** | 6 772 |
| BTC | `KXBTC15M` | « en hausse sur 15 min ? » | 15 min | 2025-12-10 | 28 074 |
| ETH | `KXETH15M` | idem | 15 min | 2025-12-10 | 28 061 |
| SOL | `KXSOL15M` | idem | 15 min | 2026-01-09 | 25 697 |
| BTC/ETH/SOL | `KXBTC`, `KXETH`, `KXSOL` | fourchettes de prix | horaire | non compté | — |
| S&P 500 | `KXINXU` (horaire, au-dessus/au-dessous), `KXINX` (fourchette journalière) | — | horaire / jour | 2023-06-23 (`KXINXU`) ; 2022-12-21 (`KXINX`) | 3 299 ; 1 131 |
| Nasdaq-100 | `KXNASDAQ100U`, `KXNASDAQ100` | idem | horaire / jour | 2023-06-23 ; 2022-12-21 | 3 299 ; 1 146 |
| S&P 500, Nasdaq | `KXINX15M`, `KXNDQ15M` | 15 min | 15 min | aucun événement réglé renvoyé | 0 |
| TSLA, NVDA, AAPL… | — | **aucune série de prix récurrente**. Il n'existe que des séries « KPI », « mentions » et ponctuelles. | — | — | — |

Ces trois dernières lignes (S&P 500/Nasdaq horaires et journaliers, 15 min, actions) viennent des
fichiers `raw/events/*.json` locaux, sauf les séries à 15 min, interrogées par l'API.

**Règlement.** Pour BTC, ETH et SOL, le contrat se règle sur la moyenne des 60 secondes de l'indice
CF Benchmarks RTI (BRTI, SOLUSD_RTI…) avant l'échéance. Texte vérifié dans `rules_primary` de
`KXBTC15M-26OCT071030-30` et `KXSOLD-26OCT0709-T116.7499`. Ce n'est pas le prix Binance, OKX ou
Jupiter.

**Frais.** `fee_type = quadratic`, multiplicateur 1. Les frais preneur valent 0,07·P·(1−P) par
contrat, soit 1,75 c à 50 c (3,5 % de la mise) ; voir H-R07 et Exp 55.

### Liquidité (instantanés ponctuels, un événement chacun : ordre de grandeur, pas une moyenne)

| Événement | Contrats échangés (total) | Spread médian, marché le plus actif, dernière heure (minute) |
|---|---:|---|
| `KXBTC15M` 2026-10-07 10:15-10:30 ET | 3 410 267 | — |
| `KXETH15M` idem | 274 353 | — |
| `KXSOL15M` idem | 52 100 | — |
| `KXBTCD` 2025-03-14 17 h | 125 158 (50 seuils) | 3 c |
| `KXBTCD` 2025-11-18 17 h | 367 074 (40 seuils) | 2 c |
| `KXBTCD` 2026-10-06 10 h | 1 814 682 (188 seuils) | 1 c |
| `KXETHD` 2025-03-14 17 h | 5 048 | 4 c |
| `KXETHD` 2026-10-06 10 h | 65 668 | 1 c |
| `KXSOLD` 2026-10-06 10 h | **4 532** (300 seuils) | **5 c** |
| `KXINXU` 2025-03-14 15 h | 1 837 | 6 c |
| `KXINXU` 2026-10-06 15 h | 158 473 | 3 c |

Lecture :
- **BTC** : liquide depuis fin 2025. Avant, le marché était plus mince.
- **ETH** : mince avant 2026.
- **SOL**, notre actif principal : **très mince**. Environ 4 500 contrats par heure sur 300 seuils,
  avec un spread de 5 c. La probabilité implicite y a une incertitude d'environ ±2,5 points rien que
  par le spread.
- **S&P 500 horaire** : quasi vide en 2025.

## 2. Littérature : les marchés de prédiction sur prix d'actifs anticipent-ils le sous-jacent ?

| Source (consultée le 2026-10-07) | Données | Résultat utile ici |
|---|---|---|
| « OpenMarket: A Synchronized Polymarket-Binance Dataset for High-Frequency Prediction-Market Research », arXiv 2607.26245 (2026-07), https://www.alphaxiv.org/abs/2607.26245 | 727 M lignes, Polymarket BTC 15 min et Binance BTCUSDT, 2026-02-12 → 2026-05-15, à la milliseconde | **Binance mène** : les cotations Polymarket répondent aux grands mouvements Binance en 347 ms (médiane). Un modèle logistique à 43 variables de microstructure fait **moins bien que la probabilité du carnet lui-même** (AUC 0,8377 contre 0,8405), et le trading simulé est **négatif** (−0,116 unité par tentative). Le carnet est un agrégateur efficient qui **suit** le spot. |
| Dai, Jia, Yu, « Settlement Manipulation in Prediction Markets », arXiv 2606.31675 (2026), https://arxiv.org/html/2606.31675v1 | Polymarket BTC 5 min, 15 min et 4 h ; flux d'ordres Binance | C'est l'**inverse** de notre question : le contrat agit sur le spot. Dans les 10 dernières secondes avant le règlement, le flux net et la volatilité Binance explosent, puis 10 à 25 % du mouvement s'inversent dans les 10 s. L'effet est fort sur le 5 min et « très atténué » sur le 15 min. Il dure quelques secondes : inutilisable pour une sortie à 50 min et une exécution Jupiter. Kalshi n'est pas étudié. |
| Mohanty, Krishnamachari, « Do Prediction Markets Forecast Cryptocurrency Volatility? Evidence from Kalshi Macro Contracts », arXiv 2604.01431, https://arxiv.org/abs/2604.01431 | 10 séries macro Kalshi (Fed, CPI, récession), 6 cryptos, 2023-01 → 2026-03, **journalier** | Les variations journalières de probabilité **macro** prévoient la **volatilité** crypto, pas les rendements. Hors échantillon, gain faible : ratio de MSFE 0,979 (récession). C'est un horizon journalier et une variable de régime, pas une information à la minute. |
| Lee, Lee, Lee, « Cryptocurrency Prediction Markets through the Derivatives Lens: Evidence from Kalshi and Polymarket », SSRN 6748186, https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6748186 (page 403 ; résumé lu via les résultats de recherche) | 113 338 contrats BTC/ETH, Kalshi et Polymarket, 2025-09 → 2026-02 | On peut en extraire des surfaces de volatilité implicite, des densités risque-neutres et des primes de variance. Cela fait des marchés de prédiction des **options binaires** valorisables comme des dérivés : leur contenu est celui d'un marché d'options, pas une information propre. Je n'ai pas pu lire de résultat de prévision des rendements. |
| Bhaskara, Jerfy, « Public Opinion as an Option », arXiv 2609.14267 (2026-09), https://arxiv.org/pdf/2609.14267 | Contrats Kalshi BTC mensuels et annuels, minute, 2024-2026 | Couverture d'une position spot. « Kalshi launched … crypto event contracts in early 2024 ». Pas de test de lead-lag. |
| Bürgi, Deng, Whelan, « Makers and Takers: The Economics of the Kalshi Prediction Market », 2026, https://www.karlwhelan.com/Papers/Kalshi.pdf (déjà cité dans H-R07) | 46 282 contrats | Les preneurs perdent en moyenne et les makers gagnent. Biais favori/outsider. Testé et rejeté sur les catégories Économie, Finance et Climat (Exp 55). |
| Accès : contrat de membre Kalshi (38 juridictions exclues, dont le Canada) ; partenariat Wealthsimple (OCRI, mars 2026, contrats ≥ 30 jours) : https://blockchain.news/news/kalshi-wealthsimple-prediction-markets-canada ; https://news.worldcasinodirectory.com/kalshis-300m-raise-fuels-global-push-to-140-markets-120150 | — | Les contrats horaires et à 15 min ne sont pas accessibles depuis le Québec (voir aussi H-R07 et le Règlement 91-102). Les futures perpétuels S&P 500 lancés par Kalshi le 2026-10-06 (https://parameter.io/kalshi-debuts-perpetual-futures-contract-for-stock-market-index-exposure) relèvent du même cadre américain (CFTC) : non vérifié pour le Canada et présumé inaccessible. |

**Synthèse.**
- Aucun article ne montre que la probabilité d'un marché de prédiction sur le **prix** d'un actif
  liquide anticipe ce prix à un horizon de quelques minutes à quelques heures.
- Les études à haute fréquence montrent le contraire : le spot mène de quelques centaines de ms, et
  les teneurs de marché valorisent ces contrats sur les options et les perps.
- Le seul effet documenté de « prédiction → prix » est mécanique et ne dure que quelques secondes
  (manipulation au règlement).
- Les marchés **macro** de Kalshi ont un faible contenu journalier sur la volatilité. Ce n'est pas
  notre horizon, et ce ne sont pas les marchés demandés.

## 3. Calcul exploratoire (ne compte pas)

Script : `scratchpad/hr11/leadlag.py`, hors dépôt. Il prend les 96 derniers marchés à 15 min réglés
(environ 24 h jusqu'au 2026-10-07 ~15:00 UTC). Variable Kalshi : variation minute du mid
(yes_bid + yes_ask)/2. Les minutes dont le spread dépasse 10 c sont exclues, ainsi que la dernière
minute (moyenne de règlement). Variable spot : log-rendement minute du spot Binance. On calcule la
corrélation de la variation Kalshi à la minute t avec le rendement Binance à t + k.

| Série | n paires | k = −2 | k = −1 | k = 0 | k = +1 | k = +2 |
|---|---:|---:|---:|---:|---:|---:|
| `KXBTC15M` / BTCUSDT | 1 152 | −0,021 | +0,013 | **+0,715** | +0,032 | −0,050 |
| `KXETH15M` / ETHUSDT | 1 152 | +0,009 | −0,004 | **+0,592** | +0,027 | −0,016 |
| `KXSOL15M` / SOLUSDT | 1 152 | −0,054 | +0,009 | **+0,738** | +0,020 | −0,052 |

Les corrélations hors k = 0 vont de |t| 0,1 à 1,8. Sur 21 corrélations calculées (7 décalages × 3
actifs, ±3 compris), aucune n'est significative une fois les tests multiples pris en compte.
À la minute, l'information est **contemporaine** : Kalshi n'ajoute rien au rendement spot de la
minute suivante. Limites : une seule journée ; résolution minute, donc un retard de moins d'une
minute (347 ms selon OpenMarket) reste invisible ; marchés à 15 min et non échelles horaires.

Autres mesures faites (pas des variantes) :
- comptage des événements par série ;
- volumes et spreads de 11 événements ;
- disponibilité des chandeliers minute en `/historical/markets/{t}/candlesticks` (vérifiée pour
  `KXBTCD` 2025-03 et 2025-11, et `KXINXU` 2025-03).

## 4. Données locales `data/kalshi/` (lecture seule, rien déplacé ni supprimé)

| Élément | Constat (échantillonnage léger, 2026-10-07) |
|---|---|
| `raw/series_all.json` | Catalogue complet : 14 714 séries, toutes catégories, dont 276 Crypto. |
| `raw/markets/`, `raw/events/` | 2 291 fichiers chacun, **uniquement** pour les catégories Economics, Financials et Climate and Weather. **Aucune série Crypto.** Les fichiers de marchés sont lourds (`KXINXU.json` 1,6 Go, `KXNASDAQ100U.json` 2,0 Go). Je ne les ai pas chargés, seulement mesurés. Ils contiennent les métadonnées des marchés (résultat, ouverture, clôture), pas de série de prix. |
| `raw/candles/` | 15 457 fichiers, soit l'échantillon aléatoire de 6,3 % d'Exp 55. Format `[ts, yes_bid_close, yes_ask_close, last_price, volume]`, **horaire** (`period_interval=60`), seulement autour des 24 h ou plus avant la clôture. Indices : `KXNASDAQ100U` 1 108 marchés (2024-10 → 2026-09, environ 36 chandeliers par marché) ; `KXINXU` 729 (2024-11 → 2026-09) ; `KXINX` 197 ; `KXNASDAQ100` 244 ; anciennes séries `INX*`/`NASDAQ100*` 2022-2024. Pas de BTC, ETH, SOL ni TSLA. |
| `eligible_index.jsonl` | 246 398 marchés éligibles d'Exp 55 (métadonnées seulement). |

**Conclusion.** Aucune donnée locale ne permet un test crypto. Pour les indices, l'échantillon est
clairsemé, horaire et centré sur la veille de la clôture. Il ne permet pas de reconstituer la
probabilité implicite à une minute donnée. Tout test passerait par l'API publique, en chandeliers
minute, à télécharger **dans un répertoire neuf**, pas dans `data/kalshi/`.

## 5. Mécanismes envisagés et classement

### H-R11a — « Penchant » de l'échelle horaire Kalshi au moment du creux (seule hypothèse testable)

- **Mécanisme supposé.** Au moment où notre modèle signale un creux sur BTC ou ETH, on compare
  l'échelle `KXBTCD`/`KXETHD` de l'heure suivante au spot. Si la médiane risque-neutre implicite
  est au-dessus du spot, les teneurs de marché, qui couvrent sur options et perps, valoriseraient
  un rebond que le spot n'a pas encore fait. Dans le cas inverse, ils anticiperaient une
  continuation. **Contre-argument fort** : le §2 et le §3 montrent que Kalshi suit le spot. Un
  écart entre médiane et spot reflète surtout des cotations périmées, le spread ou la dérive
  risque-neutre, pas une information.
- **Variable.** L = (médiane implicite à la minute du signal − mid spot) / (σ_1h · spot).
  - La médiane implicite est le seuil où la probabilité YES interpolée sur les mids vaut 0,5.
  - On n'utilise que les seuils dont le spread est ≤ 5 c, et seulement les chandeliers minute qui
    se terminent au plus tard à la minute du signal.
  - Le règlement se fait sur le BRTI : le mid spot de référence est Binance (barres d'entraînement).
    On rapporte l'écart BRTI/Binance s'il dépasse 0,05 %.
- **Prédiction chiffrée (à préenregistrer).** Population : entrées déjà sélectionnées par le
  modèle, sortie TIME50_NOSTOP, remplissage réaliste (harness v1.1), BTC et ETH, de 2024-06 à la
  fin des données disponibles.
  1. Le rendement moyen à 50 min du tercile L le plus haut dépasse celui du tercile le plus bas
     d'au moins **0,30 point**, avec le même signe sur BTC et sur ETH.
  2. Le signe tient sur les deux moitiés chronologiques.
  - Rejet si l'écart est < 0,15 point ou si un signe s'inverse. Une seule variante (seuil de
    spread et horizon fixés ici).
  - Compteur : à ajouter au compteur commun des features de filtre (Exp 51 OI, H-R04, H-R09).
- **Puissance.** On peut tabler sur environ 2,3 ans × quelques centaines de signaux BTC+ETH par
  an, mais `KXBTCD` ne couvrait pas toutes les heures en 2024 (12 637 événements en 852 jours,
  environ 15 par jour) et le marché ETH était mince avant 2026. Hypothèse : environ 600 trades
  utilisables et σ ≈ 1,4 %/trade. L'erreur type de l'écart entre terciles est alors d'environ
  0,14 point : un écart de 0,30 point serait détectable à t ≈ 2, pas mieux.
- **Pourquoi il survivrait aux coûts.** Ce n'est qu'un filtre : aucun ordre Kalshi, aucun coût
  supplémentaire. On ne fait que retirer le tercile le moins bon.
- **Limites rédhibitoires pour l'usage réel.**
  - **SOL**, l'actif principal du déploiement Jupiter, n'a d'échelle horaire que depuis 2025-12, et
    elle est très mince (≈ 4 500 contrats/h, spread 5 c) : le filtre ne s'appliquerait en pratique
    qu'à cbBTC/WETH.
  - Le HOLDOUT crypto est déjà vu jusqu'au 2026-08-17 : l'historique sert seulement à **rejeter**.
  - En live, il faudrait un appel à l'API Kalshi à chaque signal. Lecture publique : à vérifier
    dans les conditions d'utilisation des données de Kalshi, que je n'ai pas lues.
- **Probabilité a priori : ≤ 5 %.** **Coût du test : faible.** Environ 3 requêtes de chandeliers
  minute par signal, soit environ 2 000 requêtes à 3/s : moins d'une demi-journée.

### H-R11b — Volatilité implicite de l'échelle Kalshi comme modulateur de taille : écartée, dominée

Notre edge passe par `realized_vol_30` et `atr_norm` (mémoire « Strategy A mechanism »). Une
volatilité implicite à 1 h serait une variable plausible. Mais l'échelle Kalshi en est une version
**bruitée et courte** : historique depuis 2024-06, SOL depuis 2025-12, contenu d'un marché
d'options selon Lee et al. La source naturelle est l'indice **Deribit DVOL** (BTC et ETH, API
publique, historique plus long). Je n'ai pas vérifié depuis quand ; à confirmer avant toute fiche.
Aucun travail DVOL ou volatilité implicite n'existe dans le dépôt
(`grep -ri "dvol|implied vol|deribit" docs/` : aucun résultat pertinent le 2026-10-07). **Piste
dérivée à noter, pas à lancer** : il faudrait une fiche séparée. Probabilité faible, car la
volatilité réalisée est déjà dans le modèle.

### H-R11c — Stratégie propre sur Kalshi (favoris, arbitrage de latence, market making) : écartée

- Inaccessible depuis le Québec : contrats de moins de 30 jours, Règlement 91-102, Canada exclu
  par Kalshi.
- Le seul edge documenté sur les contrats crypto courts est la latence de quelques centaines de ms,
  hors de portée d'un bot à 500 CAD.
- Le biais favori a déjà été rejeté (Exp 55).
- Frais preneur ≈ 3,5 % de la mise à 50 c.

### H-R11d — Contrats S&P 500 / Nasdaq horaires comme filtre du bot Equity : écartée

Le marché était quasi vide en 2025 (environ 1 800 contrats par événement horaire, spread 6 c). Il
existe des sources plus riches pour le même contenu (options SPX/QQQ, VIX). Le bot Equity n'a
d'ailleurs pas d'edge confirmé (STATE : PF ≈ 1,04 réaliste, rejeu forward négatif).

## Anti-doublon

- `JOURNAL.md`, `REGISTRY.csv`, `research_plan_status.md` : le seul travail Kalshi antérieur est
  Exp 55 (biais favori sur Économie, Finance et Climat : REJET) et H-R07 (Polymarket bloqué).
  Aucun test n'a utilisé Kalshi comme feature ni porté sur les séries crypto.
- **Pas un doublon** de H-R03/Exp 51 (OI) ni de Exp 18/20/21 (funding) : autre source.
- **Même famille** de tests « filtre sur les entrées déjà sélectionnées » qu'Exp 41, Exp 51 et
  H-R04 : même compteur de tests multiples. Même risque qu'Exp 41/51 : signes contradictoires entre
  populations.

## Prochaine étape proposée

**Aucune action immédiate.** Si l'orchestrateur veut fermer la question à faible coût, il peut
préenregistrer H-R11a (BTC/ETH seulement, un seul test, rejet si l'écart est < 0,15 point), avec
un téléchargement des chandeliers minute `KXBTCD`/`KXETHD` dans un répertoire neuf. Sinon,
classer « pas de piste ». Garder `data/kalshi/` tel quel (décision l'auteur) : il ne sert pas à
ce sujet.

## Compteur de tests (exploratoire, ne compte pas)

- 21 corrélations de lead-lag (7 décalages × 3 actifs) sur une journée. Pas une variante de
  stratégie.
- Comptages, volumes, spreads et disponibilité des chandeliers : des mesures, pas des tests.
- Aucun calcul sur le registre de trades crypto.
