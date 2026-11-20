# H-R08 — Élargir l'univers sur Jupiter à coût bas : cbBTC/WETH via `/build` d'abord, puis JUP/BONK/PENGU/TRUMP

- **Auteur** : agent Chercheur, tâche T-021, 2026-10-06
- **Levier** : (a) plus de trades sur une plateforme à coût bas (même signal, même sortie au temps 50 min sans stop)
- **Classement T-021** : 1/3 (seul levier qui, en arithmétique, approche 15 %/an sans levier)
- **Statut** : non testée. Les chiffres de coût viennent de cotations mesurées (**exploratoire, ne compte pas**). Les chiffres de rendement sont **en échantillon** et sélectionnés après coup (backtest Jupiter, Exp 50) : ils servent à dimensionner l'hypothèse, pas à la prouver.

## Arithmétique de départ

Rendement annuel du compte ≈ N trades/an × net/trade × fraction du compte par trade (sans
chevauchement). SOL seul : 212 × 0,107 % × 0,33 ≈ **+7,5 %/an** (STATE : ≈ +7 %/an, en échantillon).
Pour 15 %/an à 33 % par position il faut une somme de 45 points de net/trade par an :
**0,21 %/trade avec 212 trades**, ou **0,09 %/trade avec 500 trades**. Augmenter l'edge par trade
de 0,107 à 0,21 % n'a jamais été obtenu dans ce projet (voir H-R09) ; doubler le nombre de trades
à edge comparable l'est, en échantillon, si le coût BTC/ETH tombe au niveau SOL.

## Mécanisme

1. **Même mécanisme, autres paires profondes.** Le rebond après creux sélectionné par le modèle est
   une rémunération de la fourniture de liquidité (Kitron et Wengrowicz 2026 : reversal 15 min sur
   90 % de 183 paires Binance, croissant avec le flux taker agressif ; Nagel 2012). BTC et ETH sont
   déjà dans le modèle (registre 9 symboles, Exp 33-36, 49) : sur la fenêtre Exp 50, BTC 39 et ETH
   182 trades/an contre SOL 271. En échantillon (T-006), BTC/ETH ont un brut **plus élevé** que
   SOL (+0,136 % contre +0,073 % sous la règle de référence), mais les frais `/order` de 10 pb par
   swap (0,20 % AR) les rendent négatifs (−0,104 %/trade).
2. **Le coût est un choix de chemin, pas une propriété du marché.** Sur Jupiter, cbBTC et WETH
   ont des pools aussi profonds que SOL à 50-500 USD : l'écart aller-retour coté sans frais de
   plateforme est ≈ 0,00-0,01 % (mesures ci-dessous). Les 0,20 % viennent uniquement des frais
   `/order` « everything else ». H-R01 (rang 1 de T-010) traite le **coût** du chemin `/build` ;
   cette fiche traite la **conséquence sur le nombre de trades** et l'univers, sans dupliquer la
   mesure de coût.
3. **Jetons natifs Solana (JUP, BONK, PENGU, TRUMP).** Bianchi, Babiak et Dickerson (2022) : le
   rendement de la fourniture de liquidité (reversal court terme) est **plus élevé dans les paires
   petites, volatiles et peu actives**. Argument pour ; mais côté projet, chaque extension d'univers
   hors majeures a échoué au niveau portefeuille (Phase A : ETC/DOT passent seuls puis REJECT en A5 ;
   TRX REJECT ; Exp 49 : DOGE PF médian 0,37, LINK 0,07). DOGE est l'analogue « memecoin » le
   plus proche et c'est l'un des deux échecs.

## Mesures de coût (exploratoire, ne compte pas)

Cotation achat USDC→jeton puis revente du montant obtenu, `lite-api.jup.ag/swap/v1/quote`
(routeur, **sans frais de plateforme** ; frais réseau, priorité et MEV exclus), 2026-10-06
23:38 et 23:50 UTC, depuis le Québec. Deux passages (le second très limité par le débit 429).
Script : scratchpad de session `t021/jup_rt_multi*.py`, non versionné.

| Jeton | AR coté 50 USD | 165 USD | 500 USD | Frais `/order` ajoutés | Perp Binance 1m depuis |
|---|---|---|---|---|---|
| SOL | 0,000 / 0,002 % | −0,016 / −0,003 % | −0,001 / 0,001 % | +0,04 % | 2020-09 (déjà en cache) |
| cbBTC | −0,004 / 0,001 % | −0,001 / 0,006 % | 0,005 / 0,009 % | +0,20 % | BTC 2019 (cache) |
| WETH (Wormhole) | 0,004 / 0,008 % | 0,003 / 0,005 % | 0,004 / 0,014 % | +0,20 % | ETH 2019 (cache) |
| WBTC (Wormhole) | 0,009 / 0,016 % | 0,005 / 0,019 % | 0,004 / 0,014 % | +0,20 % | — |
| jitoSOL | ≈ 0 | ≈ 0 | ≈ 0 | +0,10 % | = SOL (aucun trade nouveau) |
| **JUP** | 0,003 / 0,017 % | 0,013 / 0,019 % | 0,020 / 0,023 % | +0,20 % | 2024-01 |
| PENGU | −0,024 % (1 mesure) | −0,002 % | 0,013 % | +0,20 % | 2024-12 |
| TRUMP | 0,028 / 0,039 % | 0,030 / 0,039 % | 0,047 / 0,051 % | +0,20 % | 2025-01 |
| BONK | 0,038 / 0,074 % | 0,055 / 0,088 % | 0,074 / 0,107 % | +0,20 % | 2023-11 (1000BONK) |
| RAY | 0,096 / 0,097 % | 0,097 / 0,104 % | 0,101 / 0,111 % | +0,20 % | 2021-08 |
| PYTH, WIF, FARTCOIN, ORCA | 0,11-0,25 % | 0,14-0,28 % | 0,15-0,44 % | +0,20 % | 2023-11 → 2024-12 |
| JTO, POPCAT, RENDER, W, HNT | 0,17-0,56 % | 0,24-0,75 % | 0,40-1,24 % | +0,20 % | — |

Lecture : **avec `/order`, aucun jeton hors SOL ne descend sous 0,20 % AR**, donc la question « quels
jetons à ≤ 0,1 % AR » n'a de sens que via `/build`. Via `/build`, seuls cbBTC, WETH, JUP (et
peut-être PENGU, TRUMP) restent ≤ 0,05 % AR à 50-165 USD ; BONK ≈ 0,05-0,09 % ; les autres
dépassent 0,1 % et sont exclus. Les memecoins (PENGU) passent parfois par JupiterZ (RFQ), ce qui
explique un AR coté négatif : non garanti en exécution.

## Prédiction chiffrée et testable

**Étape 1 (principale) — SOL + cbBTC + WETH au coût `/build`.** Harness T-006 (v1.1, après C1),
règle déployée (entrée open suivant, sortie close +50 barres, sans stop), coût **mesuré** par
H-R01 (à défaut 0,04 % AR + frais réseau fixes), une position par symbole, 33 % du compte par
position, capital partagé (un signal sans cash est sauté et compté), pré-HOLDOUT 2021-11 → 2025-04 :

1. BTC et ETH ont chacun un net/trade **> +0,05 %** à ce coût (T-006 donne +0,136 % brut en
   règle de référence ; on attend ≈ +0,10 % net en sortie au temps).
2. Le compte SOL+BTC+ETH fait **≥ +12 %/an** (contre ≈ +7 % pour SOL seul, même harness),
   avec un **MaxDD ≤ −35 %** et un nombre de trades exécutés ≥ 1,8 × celui de SOL seul.
3. Même signe (BTC et ETH nets > 0) sur la fenêtre Exp 50 (déjà vue : sert seulement à rejeter).

Rejet si l'un des deux symboles est ≤ 0 en net, ou si le compte à trois ne dépasse pas SOL seul de
≥ 3 points/an (le gain ne compenserait pas la complexité et le risque de queue concurrent).

**Étape 2 (conditionnelle, seulement si l'étape 1 passe) — JUP et BONK en mode transfert.**
Modèle joint figé, aucun réglage par jeton (règle Phase A), données Binance USDT-M 1m de JUP
(2024-01) et 1000BONK (2023-11) jusqu'au 2025-04 : ≈ 15-17 mois chacun, puissance faible.
Prédiction : net/trade > 0 au coût `/build` mesuré **sur les deux** et test A5 (portefeuille
fantôme) qui améliore le compte. Prior défavorable (DOGE, LINK, Phase A) : probabilité ≤ 20 %.
PENGU et TRUMP n'ont pas assez d'historique pré-HOLDOUT (< 4 mois) : forward seulement.

## Trades en plus (estimation)

- cbBTC + WETH : ≈ **+220 à +290 trades/an** (fenêtre Exp 50 : 221 ; backtest Jupiter
  2021-2026 : ≈ 500/an à trois symboles, dont ≈ 212 SOL). Après partage du capital à 33 % par
  position, une partie des signaux simultanés est sautée (backtest Jupiter : 3 % de signaux sautés).
- JUP/BONK : inconnu ; les symboles en mode propre de l'Exp 49 donnaient 6-39 trades/an chacun.
  Ordre de grandeur **+20 à +100 trades/an** pour les deux, à edge incertain.

## Pourquoi survivrait aux coûts réels

Parce que le coût de cbBTC/WETH via `/build` (≈ 0,01-0,03 % AR coté + frais réseau ≈ 0,005 % par
swap à 116 USD) est **inférieur à l'edge brut en échantillon de BTC/ETH** (≈ 0,13-0,18 %), avec
une marge plus large que SOL (brut ≈ 0,07-0,11 %). Point faible : le prix d'exécution est celui
du pool cbBTC/WETH sur Solana, alors que le signal vient de Binance/OKX (écart non mesuré :
T-012). Le pont (cbBTC de Coinbase, WETH de Wormhole) ajoute un risque de dépeg en crise.

## Gain estimé (en échantillon, avant décote)

SOL seul ≈ +7 %/an → SOL+BTC+ETH ≈ **+13 à +17 %/an** si BTC/ETH tiennent +0,10 %/trade
(arithmétique : 250 × 0,10 % × 0,33 ≈ +8 points). Après décote de sélection (univers choisi après
coup, sortie choisie parmi 16 variantes) de 30-50 % sur l'edge : **+9 à +12 %/an**. MaxDD attendu
**−25 à −35 %** (backtest Jupiter SOL+BTC+ETH à 0,05 % AR fixe : −29,8 %, pire jour −18,4 % ;
trois positions concurrentes à 33 % = 99 % du compte exposé un jour de krach).

## Risque de doublon

- **H-R01** (coût `/build`) : complémentaire. H-R01 mesure le coût ; H-R08 en tire l'univers. Le
  même enregistreur de cotations doit couvrir cbBTC et WETH (pas seulement SOL).
- **Backtest Jupiter** (`research_plan_status.md`, 2026-10-05) : SOL+BTC+ETH déjà simulé, mais
  avec l'ancien moteur (empilement de positions, −4,7 points selon T-006) et des frais `/order`.
  Le refaire au harness v1.1 avec le coût `/build` est un test nouveau, pas une répétition.
- **Phase A / Exp 37-39, Exp 33-34, Exp 49** : l'étape 2 répète le schéma « nouveaux jetons en mode
  transfert » qui a échoué 3 fois sur 3 au niveau portefeuille ; c'est pourquoi elle est
  conditionnelle et à faible prior.
- Compteur de tests : étape 1 = 1 variante (univers fixé a priori : les trois actifs déployés) ;
  étape 2 = 1 variante (JUP+BONK ensemble).

## Sources (consultées le 2026-10-06)

- Jupiter, frais `/order` par paire : https://developers.jup.ag/docs/swap/fees
- Jupiter, chemin `/build` sans frais : https://developers.jup.ag/docs/swap
- Cotations : https://lite-api.jup.ag/swap/v1/quote (mesures du 2026-10-06, 23:38 et 23:50 UTC)
- Historique Binance USDT-M 1m (listage S3) : https://data.binance.vision/?prefix=data/futures/um/monthly/klines/
- D. Bianchi, M. Babiak, A. Dickerson (2022), *Trading volume and liquidity provision in cryptocurrency markets*, Journal of Banking & Finance 142 : https://econpapers.repec.org/RePEc:eee:jbfina:v:142:y:2022:i:c:s0378426622001418
- N. A. Kitron, J. M. Wengrowicz (2026), *Short-horizon mean reversion in cryptocurrency markets* : https://arxiv.org/abs/2608.21888
- S. Nagel (2012), *Evaporating Liquidity*, RFS : https://www.nber.org/papers/w17653
- Internes : `docs/agents/STATE.md`, `docs/agents/research/H-R01_execution_jupiter_build_500cad.md`, `docs/research_plan_status.md` (Exp 49, 50, Phase A, backtest Jupiter), `docs/experiment50_trades.csv` (comptage par symbole uniquement), `docs/jupiter_backtest_summary.csv`.
