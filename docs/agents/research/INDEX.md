# Fiches d'hypothèse — index classé (T-010, agent Chercheur, 2026-10-06)

Objectif commun : rentabilité nette, réelle et exécutable à 500 CAD pour un résident du Québec.
Aucune fiche n'est un résultat : ce sont des hypothèses à préenregistrer avant tout test.
Sources consultées le 2026-10-06, listées dans chaque fiche.

## Critère de classement

Espérance de gain × probabilité de succès ÷ coût du test, **pondéré par la vitesse de
vérification** (consigne de l'orchestrateur après T-006/T-007) : le harness réaliste donne un net
≈ 0 %/trade pour la stratégie actuelle sur Jupiter SOL, même en échantillon (compte 500 CAD :
−12,9 % sur 3,2 ans à 33 %), et un edge de ~0,1 %/trade avec un écart-type de ~1,6 % demande
~1 170 trades (plus de 5 ans) pour être confirmé en forward. Une hypothèse vaut donc surtout si
son **rapport signal/bruit par trade est élevé** ou si elle se **vérifie en semaines**.

| Rang | Fiche | Type | Signal/bruit attendu | Délai de verdict | Probabilité (a priori) | Coût du test |
|---|---|---|---|---|---|---|
| 1 | [H-R01 — Jupiter `/build` sans frais de plateforme](H-R01_execution_jupiter_build_500cad.md) | coût d'exécution | élevé (mesure de coût, pas de pari) | 2-4 semaines (cotations), puis ~20 micro-swaps réels sur décision | élevée | très faible |
| 2 | [H-R05 — Or via PAXG sur Solana : écart de base et retour](H-R05_or_paxg_solana.md) | nouveau marché, fourniture de liquidité | élevé si l'écart existe (trade court, faible variance) | ~6 semaines d'enregistrement, sans argent | faible (bots d'arbitrage) | faible |
| 3 | [H-R03 — Creux de déleveraging (OI en baisse) vs OI en hausse](H-R03_creux_deleveraging_open_interest.md) | nouvelle information pour le signal | moyen ; élevé seulement si l'écart entre terciles est ≥ 0,4 pt | rejet en échantillon en quelques jours ; forward lent | modérée | faible (archive Binance gratuite, vérifiée) |
| 4 | [H-R02 — Queue sans stop : taille par la queue + plafond par rafale](H-R02_controle_queue_sans_stop.md) | gestion du risque (pour T-008 / Exp 51) | réduit σ et la kurtosis, pas le signal | rejet en échantillon rapide ; queue confirmable en forward seulement sur des années | modérée | faible |
| 5 | [H-R04 — Creux résiduel (propre à la pièce) vs creux de marché](H-R04_creux_residuel_vs_marche.md) | nouvelle information pour le signal | moyen | rejet en échantillon en quelques jours | faible à modérée (Exp 41 et 48 se contredisent) | très faible (données en cache) |
| 6 | [H-R06 — Momentum de fin de séance / ETF à levier (SPY, QQQ, TQQQ)](H-R06_momentum_fin_de_seance_etf.md) | autre marché | très faible : edge exploratoire ≈ 0,01 %/jour pour un aller-retour ≥ 0,20 % | déjà quasi tranché | < 10 % à 500 CAD | très faible |
| 7 | [H-R07 — Polymarket depuis le Québec (T-020)](H-R07_polymarket.md) | autre marché | — | **tranché : Polymarket bloqué au Québec** (close-only, site + API, depuis 2026-07-06) ; piste de remplacement H-R07b (favoris 80-95 c sur IBKR ForecastEx, biais favori/outsider) : rejet historique en quelques jours via l'API Kalshi | faible à modérée (H-R07b) | faible |

Ordre de lancement conseillé : H-R01 et H-R05 tournent en **enregistrement de cotations
seulement** (aucun ordre, aucune clé), en parallèle. H-R03 puis H-R04 se jugent en échantillon sur
la même population, avec le harness T-006, et doivent compter dans le même compteur de tests
multiples. H-R02 alimente la préinscription d'Exp 51 (T-008). H-R06 ne se rouvre qu'au-delà de
~5 000 CAD.

## Constats transverses

1. **Le seul fait vraiment nouveau côté données** : l'archive `data.binance.vision` fournit l'open
   interest USDT-M toutes les 5 min depuis au moins 2020-10 (vérifié par HTTP). La décomposition de
   l'alpha avait écarté l'OI parce qu'elle croyait l'historique limité à 30 jours (H-R03).
2. **Le seul levier de coût nouveau** : Jupiter ne prend pas de frais de protocole sur le chemin
   `/build`, contre 2/10 pb par swap sur `/order` utilisé dans tous nos calculs (H-R01). À
   reconfirmer par T-004.
3. **Littérature sur les cascades** : le rendement de la fourniture de liquidité est le plus élevé
   pendant le stress (Nagel 2012), et aucune alerte précoce de cascade n'est stable d'un événement à
   l'autre (Garcia Seuma 2026). Filtrer les cascades coupe les meilleurs trades (Exp 40, 41) : il
   faut contrôler la taille et la simultanéité (H-R02), pas filtrer.
4. **Ordre de grandeur académique** : le reversal crypto à 15 min est réel sur 90 % des paires
   Binance, mais l'edge brut moyen est ≈ 1,3 pb/trade, sous le coût spot (Kitron et Wengrowicz
   2026). Notre ≈ 0,1-0,25 % brut vient de la sélection (creux en volatilité élevée) ; c'est
   cohérent avec un edge qui existe mais reste petit devant σ.

## Pistes écartées a priori (non transformées en fiches)

Ajout T-020 (2026-10-06) : **Polymarket** est écarté pour le Québec (géoblocage CA-QC close-only, VPN interdit, Règlement 91-102). Voir H-R07.

| Piste | Raison | Source |
|---|---|---|
| Ordres limit « buy below » (Jupiter Trigger) | Doublon de l'Exp 16 (entrées limit à −0,10/−0,20/−0,30 % : pires sur BTC et ETH, sélection adverse) ; et Trigger V2 coûte 0,10 % + routage, plus cher qu'un swap `/build` | `research_plan_status.md` Exp 16 ; https://docs.jup.ag/user-docs/trade/spot/limit-orders |
| Liquidité concentrée (LP Orca/Raydium/Uniswap v3) | Le LP moyen perd : 49,5 % des LP Uniswap v3 négatifs, perte impermanente 260 M$ > frais 199 M$ ; perte structurelle LVR proportionnelle à la volatilité ; seuls les LP « juste-à-temps » (infrastructure de bloc) gagnent | Loesch et al. 2021, https://arxiv.org/abs/2111.09192 ; Milionis et al., https://arxiv.org/abs/2208.06046 |
| Arbitrage de funding (spot long + perp court) | Pas de perps légaux pour particuliers au Canada (CSA) ; Hyperliquid exclut l'Ontario, légalité au Québec non établie ; rendement ≈ 5 %/an sur le capital couvert (≈ 25 CAD/an à 500 CAD) avant frais et risque de plateforme ; B_FUNDING déjà REJECT comme signal | `BROKER_OPTIONS_QUEBEC.md` ; https://www.datawallet.com/fr/crypto/hyperliquid-supported-and-restricted-countries ; `docs/strategy_b/funding/` |
| Actions tokenisées xStocks (24/7 sur Solana) | Non offertes aux résidents du Canada | https://support.kraken.com/ca/articles/getting-started-with-xstocks |
| CFD or/pétrole chez des courtiers offshore | Courtiers non inscrits = illégaux selon l'AMF | `BROKER_OPTIONS_QUEBEC.md` |
| Reversal 15 min « contre la bougie précédente » | Edge ≈ 1,3 pb/trade, sous 5 pb d'aller-retour | https://arxiv.org/abs/2608.21888 |

## Compteur de tests (exploratoire, ne compte pas)

- Cotations Jupiter aller-retour (SOL, PAXG, XAUt0 à 120 et 1 000 USD) : mesure, pas une variante.
- Momentum de fin de séance S&P 500, 2012-2019 : **2 variantes** regardées (signal première
  demi-heure ; signal reste de la journée), résultats rapportés dans H-R06.
- Aucun calcul sur les trades crypto (registre pré-HOLDOUT ou Exp 50), volontairement, pour ne pas
  contaminer les préinscriptions d'Exp 51 et suivantes.

## Questions ouvertes pour l'orchestrateur

1. T-004 (Plateformes) : confirmer « zéro frais Jupiter sur `/build` », les commissions IBKR Canada
   (page officielle en 403 pour moi) et l'application de la règle PDT aux comptes IB Canada.
2. Sémantique et latence de `create_time` dans les fichiers `metrics` de Binance avant tout calcul
   H-R03 (risque de fuite de 5 min).
3. Autoriser un enregistreur de cotations PAXG/XAU (H-R05) et `/build` (H-R01) sur un serveur
   **hors États-Unis** si on veut rester dans les conditions de Jupiter, même sans ordre.

---

# T-021 — Leviers vers ≥ 15 %/an net réaliste (agent Chercheur, 2026-10-06)

Leviers traités : (a) plus de trades à coût bas, (b) plus d'edge par trade. Le levier (c), taille
par trade, est traité par T-017. Point de départ (STATE, **en échantillon**) : SOL seul, sortie au
temps 50 min sans stop, +0,107 %/trade, ≈ 212 trades/an, 33 %/position ⇒ ≈ +7 %/an, MaxDD −23,6 %.

| Rang | Fiche | Levier | Gain estimé (après décote) | Probabilité | Coût du test |
|---|---|---|---|---|---|
| 1 | [H-R08 — Univers Jupiter à coût bas : cbBTC/WETH via `/build`, puis JUP/BONK](H-R08_univers_solana_cout_bas.md) | (a) | +2 à +5 points/an (SOL+BTC+ETH ≈ +9 à +12 %/an) | modérée (BTC/ETH déjà dans le modèle, brut > SOL en échantillon) | faible (harness v1.1 + coût H-R01) |
| 2 | [H-R09 — Régime de tendance journalière (SMA20) : demi-taille sous la tendance](H-R09_regime_tendance_journaliere.md) | (b), et queue | 0 à +2 points/an ; −5 à −8 points de MaxDD si vrai | ≈ 30 % | très faible |
| 3 | [H-R10 — BTC 21-23 UTC en cbBTC via `/build`](H-R10_btc_heure_21_23_utc_jupiter.md) | (a), stratégie autonome | +4 à +6 points/an | ≈ 25 % | très faible ; forward lent (~4 ans) |
| — | [H-R_MARKETS — une stratégie par marché](H-R_MARKETS_strategies.md) | autres marchés | voir la fiche (classement de 3 paires) | — | — |
| dernier | [H-R11 — Marchés Kalshi de prix comme feature (T-032, 2026-10-07)](H-R11_kalshi_features.md) | feature / autre marché | ≈ 0 : Kalshi suit le spot (lead-lag minute exploratoire nul) ; stratégie propre inaccessible au Québec | rejet H-R11a possible en < 1 jour (API publique) | ≤ 5 % | faible |

## Arithmétique honnête de « 15 %/an »

Rendement ≈ N trades/an × net/trade × 0,33. Pour 15 %/an il faut 45 points de net/trade par an :
**0,21 %/trade à 212 trades** (jamais obtenu : doubler l'edge par trade n'est pas réaliste au vu
des Exp 4-46) ou **≈ 0,09 %/trade à 500 trades** (plausible en échantillon si BTC/ETH coûtent
autant que SOL).

| Combinaison | Rendement attendu (en échantillon → après décote 30-50 %) | MaxDD attendu |
|---|---|---|
| SOL seul, `/order` (actuel) | ≈ +7 % → +4-5 % | −24 à −29 % |
| SOL `/build` (H-R01) | ≈ +9 % → +5-6 % | idem |
| SOL+cbBTC+WETH `/build` (H-R01 + H-R08) | ≈ +15-17 % → **+9-12 %** | −25 à −35 % |
| + H-R09 (si vrai) | ≈ +16-18 % → +10-13 % | −20 à −28 % |
| + H-R10 sur le capital libre (si vrai) | ≈ +22-26 % → **+13-17 %** | −28 à −38 % (deux stratégies longues crypto, corrélées en krach) |

**Lecture** : 15 %/an n'est atteignable sans levier que par la combinaison H-R01 + H-R08 + au moins
une des deux autres, et seulement si l'edge en échantillon ne fond pas de plus de 30 % en forward ;
le MaxDD attendu est alors ≈ −30 % (deux fois le rendement annuel). Avec la décote de 50 %
(cohérente avec l'écart backtest Jupiter +14,1 % → +6,5 % réaliste trouvé par T-006), on reste
**≈ +9-13 %/an**. Aucune de ces combinaisons n'est confirmée, et la confirmation forward d'un edge
de 0,1 %/trade demande des années (T-007) : seuls les **coûts** (H-R01, H-R08) se confirment en
semaines.

## Mesures et calculs exploratoires de T-021 (ne comptent pas)

- Cotations Jupiter aller-retour sans frais de plateforme, 19 jetons × 3 tailles × 2 passages
  (2026-10-06, 23:38 et 23:50 UTC) : tableau dans H-R08.
- Saisonnalité horaire BTC/ETH/SOL 2022-02 → 2025-03 (fenêtre publiée seulement) : H-R10.
- Or, sessions asiatique/occidentale, 2012-01 → 2025-09 : 2 tableaux horaires + 3 règles
  exécutables ; **artefact d'écart démontré** (BID seul t = 7,9 ; exécutable t ≈ −0,7) :
  H-R_MARKETS §2.2.
- Aucun calcul sur le registre de trades crypto (pré-HOLDOUT ou Exp 50), sauf le comptage des
  trades par symbole de l'Exp 50.

## Questions ouvertes pour l'orchestrateur

1. Étendre l'enregistreur de cotations de H-R01 à cbBTC et WETH (et JUP), à chaque signal et à
   21:00/23:00 UTC (H-R10), sans argent.
2. Préinscrire H-R08 étape 1 sur le harness v1.1 (après correction C1, T-018).
3. Vérifier qu'un résident du Québec peut ouvrir des **CFD** chez OANDA Canada (rang 2 de
   H-R_MARKETS) : à confier à l'agent Plateformes.

---

# T-041 — Fournir la liquidité (agent Chercheur, 2026-10-08)

| Fiche | Verdict | Chiffre clé (exploratoire, en échantillon) |
|---|---|---|
| [H-R13 — JLP, CLMM, carnets on-chain](H-R13_fourniture_liquidite.md) | **Aucun essai réel** ; veille sans argent H-R13a proposée (priorité basse) | JLP non couvert 2025-26 : +7,8 %/an, MaxDD −46 % ; JLP couvert via Jupiter Perps 2026 : ≈ +3 %/an (< Jupiter Lend 4,1 %) ; CLMM Orca SOL/USDC : frais 4,7 % < LVR 5,7-8,9 % par $ virtuel |

---

# T-042 — Listings Coinbase/Binance/Upbit (agent Chercheur, 2026-10-08)

| Fiche | Verdict | Chiffre clé (exploratoire, en échantillon, 22 événements) |
|---|---|---|
| [H-R14 — Acheter sur Jupiter après une annonce de listing](H-R14_listings.md) | **Pas d'argent, pas de test décisionnel** ; mesure de latence sans argent H-R14a proposée ; préenregistrement H-R14b conditionnel (latence ≤ 2 s) | Saut médian +11,8 % en 60 s, mais atteint en 1-2,5 s ; achat à +5 s, sortie +5 min : −0,7 % brut (médiane −1,7 %) ; net central ≈ −2,7 %/événement ≈ −30 %/an |

---

# T-054 — Nouvelles stratégies (agent Chercheur, 2026-10-09)

| Fiche | Verdict | Chiffre clé (exploratoire, en échantillon) |
|---|---|---|
| [H-R15 — Nouvelles stratégies, top 3 + préenregistrements Exp 68-70 proposés](H-R15_nouvelles_strategies.md) | Rien de démontré à 15 %/an en capital propre ; 15 % seulement via funded si Sharpe hors échantillon ≥ ~0,7 et payouts honorés. Top 3 : A tendance multi-horizons long/cash Jupiter ; B même signal sur Propr 10 K ; C zone de bruit MNQ filtrée par le GEX | A (2020-10 → 2025-03) : CAGR +21,6 %, MaxDD −12,7 %, Sharpe 1,74 (attente hors échantillon +5 à +12 %/an) ; C (P1) : MNQ Sharpe 0,97 → 1,04, MaxDD −1 548 → −1 079 USD ; boucle LST : spread négatif 62 % des jours depuis 2025-03 |

# T-061 — Funded optimal (agent Chercheur, 2026-10-10)

| Fiche | Verdict | Chiffre clé (exploratoire, en échantillon) |
|---|---|---|
| [H-R17 — Réussir un funded futures : barrière, série réelle MNQ, statistiques publiées, préenregistrement Exp F2](H-R17_funded_optimal.md) | Edge nul perdant (−27 à −100 pour 100 USD, forme réelle) ; statistiques Topstep/FPFX compatibles avec le hasard. Meilleure combinaison : Lucid Flex 50K, MNQ zone de bruit 1 micro, sans stop journalier, en promotion. Pas de marge de sécurité ; ne rien acheter avant Exp F2 (Dow/Russell) | Pour 100 USD : +161 (edge H mesuré), +10 à +17 (demi-edge), −61 à −65 (edge nul) ; stop journalier : −76 à −92 % de l’edge |

# T-063 — Swing et horizons intermédiaires (agent Chercheur, 2026-10-10)

| Fiche | Verdict | Chiffre clé (exploratoire, en échantillon) |
|---|---|---|
| [H-R18 — Swing (jours-semaines) et intermédiaire (heures-3 j) : classement de 10 pistes, préenregistrements Exp A (RSI(2) FNB indiciels, MOC) et Exp B (SPY la nuit)](H-R18_swing.md) | Rien à 15 %/an avec risque favorable ; seul effet solide = rebond de l'indice sur 2-5 j (effet de marché, pas de sélection) ; complément de quelques points/an au mieux | RSI(2) 35 FNB 2017-2026 +0,37 %/trade brut (t 9,8) mais portefeuille 5 cases +3,8 %/an, Sharpe 0,43 ; IBS couvert SPY −0,006 %/jour ; nuit SPY Sharpe 0,74 < détention 0,88 |
# T-064 — Retour à la moyenne funded (agent Chercheur, 2026-10-10)

| Fiche | Verdict | Chiffre clé (exploratoire, découverte ≤ 2019, ne compte pas) |
|---|---|---|
| [H-R19 — Retour à la moyenne intrajournalier pour funded futures ; vérification E-nano et firmes ; préenregistrement R1](H-R19_funded_meanrev.md) | Rien ne tient : 0/41 configurations nettes > 0 sur ≥ 2 indices. Seul survivant partiel : fade d'ORB 30 min sur NDX (fortuit probable). E-nano : coût AR 6,4 × MNQ, aucune firme vérifiée. R1 proposé comme test de fermeture (a priori ≈ 10 %) | F2 OR30 Sharpe net MNQ +0,68 / MES −0,88 / MYM −1,44 ; NNQ 0,0245 % contre MNQ 0,0038 % |

# T-071 — Viser ≥ 15 %/an net sur longue période (agent Chercheur, 2026-10-11)

| Fiche | Verdict | Chiffre clé (littérature ; aucun backtest) |
|---|---|---|
| [H-R20 — Classement de 8 pistes « levier + diversifiants » et brouillon de préenregistrement Exp 76](H-R20_quinze_pour_cent.md) | N° 1 : actions ×1 + tendance ×1 empilées (RSST ; HSU + DBMF dans le CELI), P(15 %) ≈ 25-30 %, P(PASS) ≈ 35 % ; aucune piste > 1 chance sur 3 ; Nasdaq ×2 filtré et puts à levier exclus | Barre : Sharpe net ≥ 0,63-0,73 à vol 20-25 % pour 15 %/an ; tendance 1880-2016 Sharpe net 0,76 (0,41 en 2010-16) ; 80 % 60/40 + 20 % tendance : Sharpe 0,39 → 0,55, MaxDD −62 → −50 % (Hurst et al. 2017) |

# T-075 — Marchés sur 5 ans et nouvelle stratégie « qui est de l'autre côté ? » (agent Chercheur, 2026-10-11)

| Fiche | Verdict | Chiffre clé (littérature et données publiques ; aucun backtest) |
|---|---|---|
| [H-R21 — Marchés prometteurs sur 5 ans ; 15 idées de flux forcés ; finalistes F1 saison REER/CELI et F2 rabais DRIP ; brouillons Exp 81-82](H-R21_nouvelle_strategie.md) | Partie 1 : hors US (valeur, petites cap.) devant US, confiance faible (pouvoir prédictif à 5 ans faible). Partie 2 : 13 idées sur 15 éliminées (connues, non exécutables ou sans données) ; 2 finalistes canadiennes, compléments de +0,5 à +2 %/an au mieux, P(PASS) ≈ 10 % chacune ; N = 95 (prudent 132) | CAPE Shiller 41,9 ; TIPS 10 ans 2,91 % réel (2026-10-09) ; AQR réel US 3,9 % contre hors US 4,9 % ; GMO US grandes cap. −7,4 % réel |
