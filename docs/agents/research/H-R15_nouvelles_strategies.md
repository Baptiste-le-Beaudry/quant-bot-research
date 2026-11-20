# H-R15 — Nouvelles stratégies pour ≥ 15 %/an à ~500 CAD (T-054, agent Chercheur, 2026-10-09)

- **Branche :** `research/new-edges` (depuis `agents/orchestration-20261006`, commit 95bd3c3).
- **Statut :** revue de littérature et calculs exploratoires légers. **Aucun test décisionnel.** Tous les chiffres de cette fiche sont **exploratoires, ils ne comptent pas** et sont **en échantillon**, sauf mention contraire.
- Sources consultées le **2026-10-09** (liste en §8). « Non académique » signale un praticien, un blogue ou une société.
- Scripts et sorties : `docs/agents/research/H-R15_scripts/`. Instantané GEX gelé : `DIX_snapshot_2026-10-09.csv`, sha256 `75495c7b1bf8260679504c1370e43833c618415b252b3b29491f0fb9d8d8c190`.

## 0. Réponse courte

1. **Aucune idée n'est démontrée à 15 %/an net en exécution réelle.** Je n'ai trouvé aucun edge structurel qui le prouve sur des données hors échantillon. Ce qui s'en approche le plus est une **règle de tendance publiée** (ensemble Donchian à volatilité ciblée, Zarattini-Pagani-Barbon 2025), testée ici sur SOL, BTC et ETH avant 2025-04, en échantillon :
   - **long/cash au comptant** : CAGR **+21,6 %** (avec un rendement du cash à 4 % : **+25,8 %**), MaxDD **−12,7 %**, Sharpe **1,74** ;
   - mais ces chiffres viennent d'un marché haussier (panier +100 %/an). **Mon attente hors échantillon est de +5 à +12 %/an**, rendement du cash compris.
2. **Le seul levier qui peut donner ≥ 15 % sur 500 CAD est le compte funded** : on y est payé sur un capital simulé de 10 000 à 100 000 USD, et on ne risque que les frais de l'évaluation. Il ne paie que si deux conditions sont réunies :
   - un Sharpe réel d'au moins ~0,7 ;
   - une queue gauche courte, compatible avec la règle de drawdown.

   La même règle de tendance, en long seul sur Propr, est le meilleur candidat (§3.2). Mais Propr est jeune (lancé en 2026-02, petite levée de fonds, B-book) : **le risque de contrepartie est réel**.
3. **Top 3 proposé :**
   1. **H-R15-A** : tendance multi-horizons, long/cash, SOL/cbBTC/WETH sur Jupiter, cash prêté.
   2. **H-R15-B** : le même signal sur Propr Classic 1-Step 10 K (110 USD).
   3. **H-R15-C** : la zone de bruit MNQ (Exp 65) **filtrée par le gamma des teneurs de marché** (GEX SqueezeMetrics, gratuit), pour Lucid ou Topstep.

   A et B partagent un seul test historique.
4. Écartées : 20 idées, une ligne chacune (§4).
   - Le portage on-chain sur LST est **négatif** depuis 2025-07 : le taux d'emprunt du SOL dépasse le rendement du staking 62 % des jours.
   - Les coffres d'options Solana sont quasi inexistants.
   - Les déblocages de jetons ne s'exploitent qu'à découvert. Je les garde en veille (H-R15-D), sans test possible faute de données gratuites.

## 1. Anti-doublon (lu avant tout calcul)

Lus : `AGENT_RULES.md`, `REPRISE.md` §3, `REGISTRY.csv` (Exp 49-66), `research/INDEX.md` (H-R01 à H-R14, H-R_MARKETS), titres de `research_plan_status.md` (Exp 0.1-50), `validation/T-049_DSR_PBO_2026-10-08.md`, `JOURNAL.md`, `BACKLOG.md`, `venues/FUNDED_FUTURES_2026-10-08.md`, `venues/IDLE_YIELD_2026-10-07.md`, `venues/VENUES_500CAD_2026-10-06.md`, `hypotheses/Exp-56.md` et `results/Exp-56`, `results/Exp-64`, `results/Exp-65`.

| Recouvrement | Avec | Différence / risque de doublon |
|---|---|---|
| H-R15-A/B (tendance) | **Exp 56** : momentum 7 j long/cash BTC/ETH/SOL, **REJET** parce que le marché haussier 2023-25 ne rapportait que 0,43 × le panier ; récent 2025-04 → 2026-08 : +4,2 %/an. Aussi BR1 (rotation transversale), B1-B8 (cassures intrajournalières) | **Même famille (momentum série-temporelle), à compter dans le même compteur.** Différences : (1) règle **publiée et figée** (9 horizons, sortie au milieu du canal, taille par la volatilité), pas un réglage maison ; (2) objectif différent. L'Exp 56 jugeait la capture du marché haussier ; ici, on juge le Sharpe et le drawdown, ce que valorise un compte funded. **Risque de doublon : élevé sur le signal, nul sur l'usage funded.** |
| H-R15-B (Propr) | T-017 (« la convexité Propr ne paie pas les réessais avec un edge nul »), backtests funded du 2026-10-05 (invalides : sortie au stop), `VENUES_500CAD` §2.3 | Ces travaux portaient sur la stratégie A (intrajournalière, queue gauche de −40 % par jour). Ici, la stratégie est lente, à petite exposition et à pire jour de −3,6 %. Elle n'avait jamais été évaluée sous les règles Propr. |
| H-R15-C (GEX) | Exp 64/65 (zone de bruit), Exp 67 (forward papier MNQ) | Même règle et même moteur. **Ajout : un seul filtre a priori**, tiré d'un mécanisme publié (Baltussen et al. 2021). Le HOLDOUT indices a été consommé par l'Exp 65, mais **jamais découpé par le GEX**. Je n'ai regardé que P1 (§7). |
| Portage LST, prêts | T-029 (Jupiter Lend ≈ 4,1 %), T-035 (jitoSOL), H-R13 (JLP) | Non refait ; seule la boucle à levier jitoSOL/SOL est nouvelle (écartée, §4). |
| Polymarket/Kalshi comme signal | H-R11, T-032 (Kalshi suit le spot, lead-lag nul) | Non refait (écarté). |
| Effets d'heure / calendrier | Exp 66 (REJET), H-R10 | Les effets jour/mois n'avaient pas été testés ; la littérature les dit instables (écartés). |

## 2. Critères d'élimination appliqués

Une idée est éliminée si elle échoue à l'un de ces critères :
- **C1 accès :** légale et accessible au Québec, avec un bot ;
- **C2 vitesse :** l'edge se joue en plus de 10 s ;
- **C3 coût :** brut ≥ 3 × coût ;
- **C4 queue :** compatible avec le budget, ou avec les règles de drawdown s'il s'agit d'un compte funded ;
- **C5 testabilité :** données gratuites ou forward rapide ;
- **C6 ampleur :** au moins quelques %/an sur 500 CAD, ou sur le capital funded.

---

## 3. Idées retenues

### 3.1 H-R15-A — Tendance multi-horizons long/cash à volatilité ciblée, SOL/cbBTC/WETH (capital propre, Jupiter)

**Mécanisme.** Le momentum série-temporelle en crypto s'explique par une sous-réaction et des flux qui s'auto-entretiennent : l'attention et les entrées de capitaux suivent les rendements passés (Liu et Tsyvinski 2021). Il n'est pas arbitré, pour trois raisons :
- c'est un **pari de régime**, pas un arbitrage sans risque ;
- il perd dans les marchés sans tendance et sous-performe la détention en marché haussier, ce que les gérants évalués contre un indice ne supportent pas ;
- sa capacité est grande, mais le Sharpe est faible pour un fonds qui paie 2/20.

La **taille par la volatilité** n'est pas un edge en soi. Elle coupe l'exposition quand la volatilité monte, c'est-à-dire dans les krachs, et c'est ce qui raccourcit la queue gauche (Moskowitz, Ooi et Pedersen 2012 ; Hurst, Ooi et Pedersen 2017).

**Preuves.**
- Liu et Tsyvinski (2021, *RFS*) : momentum significatif à 1-4 semaines sur BTC, ETH et XRP (académique).
- Zarattini, Pagani et Barbon, « Catching Crypto Trends » (SSRN 5209907, publié le 2025-05-06, révisé le 2025-10-02). Ensemble de canaux de Donchian sur 5, 10, 20, 30, 60, 90, 150, 250 et 360 jours, entrée au plus haut, sortie au milieu du canal, volatilité ciblée de 25 %, levier ≤ 200 %. Sur le top 20 des cryptos de 2015 à 2025-03, sans biais de survie : **Sharpe > 1,5, alpha de 10,8 %/an contre BTC** (académique, en échantillon pour les auteurs).
- **Exploratoire, ne compte pas** (`trend.py`, Binance journalier 00:00 UTC, 2020-10-01 → 2025-03-27, rien de plus récent n'a été chargé). Règle de l'article simplifiée : signal = moyenne des 9 états ; poids = signal × min(1, 0,25/σ60j)/3 ; décision à la clôture J, détention sur J+1. Coût 0,05 % aller-retour sur la rotation.

  | Variante (exploratoire) | CAGR | Vol | Sharpe | MaxDD | Pire jour | Exposition moyenne | 2022 | 2025 T1 |
  |---|---|---|---|---|---|---|---|---|
  | Panier 1/3 détenu | +99,8 % | 78 % | 1,28 | −85,3 % | −28,5 % | 100 % | −79 % | −25 % |
  | **Long/cash, tv 0,25 (règle de l'article)** | **+21,6 %** | 11,6 % | **1,74** | **−12,7 %** | −3,6 % | 15 % | −6,3 % | −4,1 % |
  | Idem + 4 %/an sur le cash (Jupiter Lend) | +25,8 % | 11,6 % | 2,03 | −8,9 % | −3,6 % | 15 % | −2,6 % | −3,3 % |
  | tv 0,50 + cash (rapporté, **non retenu**) | +48,7 % | 22,9 % | 1,85 | −20,9 % | −7,1 % | 30 % | −9,0 % | −7,5 % |

  - Rotation ≈ 6 fois le capital par an (tv 0,25), donc coût ≈ 0,3 %/an à 0,05 % AR. **Rapport brut/coût ≈ 70.**
  - Le tv de 0,25 est celui de l'article ; je ne le choisis pas pour le meilleur chiffre (0,50 et 0,75 sont « meilleurs » en échantillon, mais ils sont rejetés comme choix post hoc).

**Edge brut, coût, ratio.**
- Brut en échantillon ≈ +22 %/an pour un coût ≈ 0,3 %/an, soit un ratio de **≈ 70** (critère C3 rempli très largement).
- Hors échantillon, en tenant compte de la décroissance après publication (McLean et Pontiff : environ −30 à −50 %) et d'un marché moins haussier, j'attends **+5 à +12 %/an**, rendement du cash compris (Jupiter Lend ≈ 4 %).

**Trades/an et délai de preuve.**
- Environ 50 à 150 swaps par an. Le signal change d'état environ 20 à 40 fois par an et par actif, auxquels s'ajoutent les ajustements de volatilité, qu'une bande de 2 % peut éliminer.
- **La preuve statistique est lente** : à un Sharpe de 1, il faut **≈ 4 ans** de données pour t = 2 ; à un Sharpe de 0,5, ≈ 16 ans.
- L'historique ne sert donc qu'à **rejeter**. Le forward sert à contrôler l'implémentation (règle D-05).

**Pertes extrêmes.**
- En échantillon : MaxDD −12,7 %, pire jour −3,6 %.
- Scénario adverse : un krach de −40 à −50 % sur 2-3 jours au sommet d'une tendance, quand l'exposition atteint 40-60 % (après plusieurs semaines de hausse et de volatilité modérée). Perte ≈ **−15 à −25 %** avant que les sorties au milieu du canal ne déclenchent.
- Risques hors marché :
  - le cash, prêté sur Jupiter Lend, peut subir un exploit et être perdu en totalité (T-029) ;
  - l'USDC peut se découpler (dépeg) ;
  - cbBTC (Coinbase) et WETH (Wormhole) portent un risque de pont ou d'émetteur.

**Accès Québec.** Oui, par Jupiter `/build` depuis un serveur au Canada (déjà en place pour A). Coût cbBTC/WETH : voir H-R08 et Exp 57.

**Données gratuites.**
- Cache Binance 1 min (`docs/_full_data_cache`, jusqu'au 2026-08-17).
- Bougies journalières Hyperliquid (API `candleSnapshot`, vérifiée le 2026-10-09).
- Taux USDC Kamino et Jupiter Lend (T-029).

### 3.2 H-R15-B — Le même signal sur un compte funded crypto (Propr Classic 1-Step)

**Mécanisme (structurel).** Le compte funded est une **option à responsabilité limitée** : on ne perd jamais plus que les frais, et on touche 80 % des gains sur un capital simulé.
- Propr est rentable parce que la plupart des clients ont un edge négatif et surtradent, comme le dit Topstep : 16,8 % de réussite, non vérifié, T-050.
- Une stratégie **lente, à petite exposition, à faible coût et à pire jour court** est exactement le type de client que la règle de drawdown ne tue pas.
- Ce n'est pas « arbitrable » par la firme : elle accepte ce risque en échange des frais payés par les autres.
- **C'est la seule voie trouvée où 500 CAD peuvent rapporter ≥ 15 %/an**, parce que le gain est indexé sur 10 000 USD et non sur 360 USD.

**Règles Propr** (propr.xyz/rules, v1.0 du 2026-02-25, lues le 2026-10-09) :

| Programme | Taille | Frais | Objectif | Perte journalière | DD max |
|---|---|---|---|---|---|
| Classic 1-Step | 10 K | **110 USD** | +10 % | 3 % (sur l'équité, latent inclus, remise à 00:00 UTC) | 6 % statique |
| Classic 1-Step | 100 K | 999 USD | +10 % | 3 % | 6 % statique |

- Sans limite de temps, sans nombre minimal de jours, sans règle de cohérence.
- Positions tenues la nuit et le week-end **permises**.
- **Funding appliqué** : Hyperliquid prélève ≈ 11,6 %/an sur les longs quand la prime est nulle (docs Hyperliquid).
- Payout : 80 %, à la demande, **en balayant tout le profit** (le solde revient au départ).
- Interdits : la **couverture sur un autre compte ou une autre plateforme**, et le « cycling » d'évaluations « comme des billets de loterie ».
- Le compte est servi en hybride A-book/B-book.
- Plafond de 300 000 USD funded au total.

**Preuves (exploratoire, ne compte pas, 2020-10 → 2025-03, en échantillon).** Version perp, long seul, BTC/ETH/SOL :
- coût 0,15 % AR (0,075 % par côté, hypothèse prudente de T-004) ;
- funding Binance réel pour BTC/ETH, base de 0,03 %/jour pour SOL.

| Variante | CAGR | Vol | Sharpe | MaxDD | Pire jour |
|---|---|---|---|---|---|
| Long seul B3 perp | +18,7 % | 11,6 % | 1,54 | −13,2 % | −3,6 % |
| Long seul, 10 cryptos perp | +15,5 % | 9,1 % | 1,63 | −10,3 % | −3,0 % |
| Long/court, 10 cryptos (rapporté) | +10,0 % | 11,1 % | 0,92 | −17,9 % | −4,4 % |
| Jambe courte seule | **−5,0 %** | 9,6 % | −0,48 | −26,7 % | — |

→ **La jambe courte perd en échantillon : long seul.**

**Simulation des règles Propr** (départs glissants tous les 3 jours, horizon 2 ans, perte intrajournalière prudente qui suppose tous les plus bas simultanés). Échelle fixe k × la règle tv 0,25 :

| k (vol) | P(réussite) | P(échec) | Encore ouvert | Jours médians jusqu'à la réussite |
|---|---|---|---|---|
| 0,5 (5,8 %) | 0,51 | 0,14 | 0,35 | 308 |
| 0,75 (8,7 %) | 0,52 | 0,43 | 0,06 | 285 |
| 1,0 (11,6 %) | 0,60 | 0,36 | 0,04 | 190 |

Avec une mise à l'échelle par la volatilité du PnL sur 90 jours, c'est **pire** (réussite 0,43-0,61, échec 0,18-0,52) : les sauts de levier à la reprise d'une tendance coûtent cher. Il faut donc une échelle **fixe**.

**Espérance (modèle, pas un test)** pour 10 K à 110 USD, en payout balayé à chaque +10 % (le coussin repart de zéro), avec p = P(+10 % avant −6 %) :
- En échantillon (p ≈ 0,5) : ≈ 1 cycle funded attendu → 800 USD → **EV ≈ +290 USD par tentative** sur ≈ 1,5-2 ans, soit **≈ +40 à +55 %/an sur 360 USD**.
- Avec un Sharpe divisé par deux hors échantillon : p ≈ 0,4-0,45, d'où **EV ≈ +50 à +150 USD par tentative**.
- À edge nul : EV ≈ 0 une fois les coûts et le funding payés. C'est cohérent avec T-017.
- À 100 K (999 USD), tout est multiplié par 10, mais les frais dépassent le budget de 500 CAD.

**Pertes extrêmes.**
- On perd au plus les frais : 110 USD ≈ 150 CAD par tentative.
- Risque de contrepartie : Propr a été lancé en 2026-02, a levé 1,5 M USD en seed (XBorg, soutien SwissBorg) et n'est pas réglementé (BVI). Il peut refuser ou retarder les payouts. 20 avis Trustpilot seulement (source non académique).
- Clauses « herd trading » et « off-the-shelf » : une règle publiée appliquée telle quelle pourrait être signalée. Il faut une implémentation propre et documentée.

**Accès Québec.** Ni le Canada ni le Québec ne sont exclus. Les comptes sont simulés, les bots permis par API, et l'exécuteur Propr existe déjà en dry-run (2026-10-05). Statut AMF **non vérifié** (inférence, T-004). Fiscalité : revenu probable, non vérifié.

**Données gratuites.** Bougies et `fundingHistory` Hyperliquid (API publique, vérifiée le 2026-10-09), cache Binance.

### 3.3 H-R15-C — Zone de bruit MNQ filtrée par le gamma des teneurs de marché (funded futures)

**Mécanisme.** Baltussen, Da, Lammers et Martens (2021, *JFE*), sur 60 futures de 1974 à 2020 :
- le momentum intrajournalier vient de la **couverture des positions à gamma négatif** (teneurs de marché d'options, ETF à levier) : quand les teneurs de marché sont **courts gamma**, ils achètent la hausse et vendent la baisse, ce qui crée de la continuation ;
- quand ils sont **longs gamma**, ils font l'inverse, ce qui amortit les mouvements et produit du retour à la moyenne.

La zone de bruit (Exp 64/65) est une stratégie de continuation. Elle devrait donc **perdre ses jours de hachage quand le GEX est élevé** et garder ses grands jours de tendance quand il est bas. Ce n'est pas arbitré :
- c'est un flux forcé de couverture ;
- le gain par jour (≈ 10 USD par MNQ) est trop petit pour un desk, mais suffisant pour un compte funded à 2,22 USD AR.

**Preuves.**
- Baltussen et al. 2021 (académique).
- Le GEX historique quotidien de SqueezeMetrics est **gratuit** : `squeezemetrics.com/monitor/static/DIX.csv`, de 2011-05-02 au 2026-10-08, 3 883 jours. Téléchargé et gelé le 2026-10-09 (non académique ; méthode propriétaire).
- **Exploratoire, ne compte pas** (`gex_split.py`), **P1 de l'Exp 64 seulement** (NDX 2012-02 → 2024-03-04 ; SP500 2013-06 → 2024-04-02). Percentile du GEX de la veille dans sa fenêtre glissante de 252 jours ; PnL net quotidien de l'Exp 64 (1 contrat, coût de l'Exp 64).

  | P1, net/jour (Sharpe) | GEX bas | GEX moyen | **GEX haut** |
  |---|---|---|---|
  | NASDAQ100 → MNQ | +8,5 USD (1,12) | +9,3 USD (1,66) | **+0,7 USD (0,16)** |
  | SP500 → MES | +2,4 USD (0,43) | +3,8 USD (1,02) | **−2,5 USD (−0,88)** |

  | P1, filtre « pas de trade si GEX de la veille > 2/3 » | Sharpe net | MaxDD | Pire jour | Part du net venant des 5 meilleurs jours |
  |---|---|---|---|---|
  | MNQ sans filtre → avec | 0,97 → **1,04** | −1 548 → **−1 079 USD** | −624 USD | 22 % → 21 % |
  | MES sans filtre → avec | 0,23 → **0,51** | −3 891 → **−2 434 USD** | −371 USD | 94 % → 46 % |

  Le tercile « GEX haut » est le plus mauvais **sur les deux indices**, ce qui va dans le sens du mécanisme. En revanche, les jours où le GEX est négatif en valeur absolue sont mauvais aussi (n = 290 et 278), contrairement au mécanisme. **Signal modeste**, à confirmer sur une autre période.

**Edge brut, coût, ratio.** P1 MNQ : brut 21 256 USD contre coûts 5 597 USD, **ratio ≈ 3,8** (Exp 64), au-dessus de la limite. Avec le filtre, environ un tiers des jours en moins, donc moins de coûts aussi.

**Trades/an et délai de preuve.** ≈ 140 trades par an (2/3 des ≈ 210). À un Sharpe de 1, il faut **≈ 4 ans** pour t = 2. Le forward (Exp 67) ne peut donc que détecter un effondrement.

**Pertes extrêmes.**
- Pire jour en P1 : −624 USD par MNQ.
- Pour mémoire, Exp 65 sans filtre : MaxDD −3 949 USD (2025-04 → 2026-02), ce qui fait perdre un compte de 50 K. Le filtre doit ramener ce chiffre sous 2 000 USD, sinon c'est un REJET.
- Risque de données : le GEX est un **modèle propriétaire** qui peut être révisé après coup (biais de prévision). Étape 0 obligatoire (§5.3).

**Accès Québec.** Lucid ou Topstep : Canada admis, bots permis (T-050). Topstep impose des ordres depuis le PC personnel (pas de VPS). Le GEX du jour J−1 est publié après la clôture de J−1, donc il est disponible avant l'ouverture de J.

**Données gratuites.** DIX.csv, Dukascopy 1 min (en cache), fichiers quotidiens des Exp 64/65.

### 3.4 H-R15-D (veille, hors top 3) — Vendre à découvert les déblocages de jetons « équipe/investisseurs » sur Propr

**Mécanisme.** Les bénéficiaires d'un déblocage connu à l'avance couvrent ou vendent avant la date. L'offre arrive à date fixe, et le prix baisse avant l'événement.

**Preuves (non académiques).**
- Keyrock (2024-12, > 16 000 déblocages) : 90 % ont un effet négatif, qui commence environ 30 jours avant. Déblocages « équipe » : ≈ −25 % en moyenne. Rendements **non ajustés du marché**.
- Tokenomist (2026-06) : 236 événements de 2024-06 à 2026-03, médiane à 1 mois de **−4,85 % contre des pairs comparables** (n = 221).

**Calcul d'ordre de grandeur.**
- Edge ≈ 3-5 % par événement sur 30 jours, contre un coût de 0,15 % AR plus le funding. Le funding devient souvent **négatif pour les vendeurs à découvert** sur ces jetons, ce qui peut coûter 1-4 %/mois. Ratio de 1 à 20 selon le funding.
- σ par événement ≈ 20 %, soit un Sharpe d'environ 0,2 par événement. Il faut ≈ 200 événements pour t ≈ 2,8.

**Pourquoi hors du top 3.**
- (1) Pas de données gratuites : l'API d'émissions DefiLlama est payante (HTTP 402, vérifié) et Tokenomist aussi.
- (2) Queue droite des jetons à découvert : squeezes de +30-50 % en un jour face à une perte journalière maximale de 3 %, d'où une taille ≤ 3-5 % par événement.
- (3) Le court en échantillon perd déjà en tendance (§3.2).

**Proposition :** construire à la main, sans argent, un calendrier forward de 6 mois (gros déblocages > 2 % de l'offre en circulation, jetons cotés sur Hyperliquid), puis décider.

---

## 4. Écartées (une ligne chacune)

| Idée | Raison (critère) |
|---|---|
| Boucle à levier jitoSOL/SOL (Kamino Multiply) | Exploratoire (`loop.py`, DefiLlama jitoSOL × emprunt SOL du marché principal Kamino, 2025-03 → 2026-10) : spread **négatif 62 % des jours** ; à 5x, moyenne +3,0 %/an, **< jitoSOL seul (6,2 %)** ; T3 2026 à 5x : −6,4 %/an ; pic d'emprunt à 27 % (2026-07-08) ; rendement libellé en SOL ; les marchés dédiés (Jito market, groupes d'élévation) peuvent avoir d'autres taux, **non vérifié** (C6, C4) |
| Staking « delta-neutre » (USDC + jitoSOL − dette SOL) | ≈ 4-5 %/an au mieux, risque de liquidation et d'oracle (C6) |
| Écarts de taux USDC entre protocoles (Kamino vs Jupiter Lend) | Écart 0,3-1 pt ⇒ 2-5 CAD/an (C6) ; déjà couvert par T-029 |
| Coffres d'options Solana (vente de volatilité) | Friktion fermé en 2023-01, marché résiduel (PsyFinance, Chest) ; dérivés à la légalité non vérifiée ; profil = bêta long + queue gauche (C1, C4) |
| ETF « covered call » crypto (ex. Amplify SOLM) via IBKR | Bêta plafonné, pas d'alpha ; 1 USD par ordre (C6) |
| Déblocages de jetons en long seul | L'edge est à la baisse ; sans vente à découvert, il ne reste qu'à éviter les jetons ; le rebond après déblocage n'est pas démontré (C6) → voir H-R15-D |
| Rééquilibrages d'indices crypto | Encours indiciels négligeables, aucun flux mesurable (C6) |
| Inclusions S&P (actions crypto) | IBKR à 1 USD par ordre, capital, course des pros à l'annonce (C3, C2) |
| Airdrops / points | EV non mesurable (biais de survivant, filtres anti-sybil), non systématisable (C5) |
| Migrations de jetons / pools | Rares et non systématiques (C5) |
| Calendrier crypto (week-end, fin de mois, jour de semaine) | Effets variables dans le temps et non persistants (Quantpedia ; études 2024) ; heures déjà rejetées (Exp 66) (C3) |
| Polymarket/Kalshi comme signal | Kalshi suit le spot (H-R11) ; événements macro trop rares pour un test (C5) |
| Achat de stablecoins en dépeg (USDC 2023 à 0,87, etc.) | 1-3 événements/an, ≈ 0,5-3 %/an du capital, queue gauche de défaut, impossible à prouver (C5, C4) |
| Arbitrage d'escompte LST (Sanctum) | Bots, écarts < 0,1 % (C2, C3) |
| Flux d'ordres DCA Jupiter | Réarbitrés dans le bloc (C2) |
| Liquidations Kamino/Drift | Bots < 1 s (C2) |
| Retour à la moyenne intrajournalier sur indices les jours de GEX élevé (« l'inverse de l'Exp 65 ») | C'est l'inverse de trades au brut ≈ +2,7 USD/jour en P1 MNQ ⇒ net négatif après 2 × 2,22 USD (C3) |
| Tendance futures multi-jours en funded futures | Positions aplaties chaque jour (Topstep 16:10 ET, Lucid 16:45 ET) (C1) |
| Base CME / cash-and-carry | MBT = 0,1 BTC ≈ 11 k USD de notionnel (IBKR min 2 000 USD), funded seulement en intrajournalier ; Propr interdit la couverture externe (C1) |
| Tendance long/court sur Propr | Jambe courte −5 %/an en échantillon ; réussite 0,27-0,39 (C4) |

---

## 5. Classement et préenregistrements proposés (à exécuter par l'orchestrateur)

| Rang | Idée | Gain si vrai (500 CAD) | Probabilité a priori | Coût du test | Délai du verdict |
|---|---|---|---|---|---|
| **1** | **H-R15-A** tendance long/cash Jupiter | +5 à +12 %/an (capital propre) ; MaxDD −10 à −25 % | ≈ 40 % de PASS en P2 | très faible (données en cache, < 1 h) | quelques heures (rejet) ; forward lent |
| **2** | **H-R15-B** même signal sur Propr 10 K | EV ≈ +50 à +290 USD par tentative de 110 USD (≈ +15 à +55 %/an sur 360 USD), **si payouts honorés** | ≈ 25 % (dépend de A + contrepartie) | faible (ajoute la simulation des règles + funding Hyperliquid) | même calcul que A, puis 3 mois sur l'environnement Beta |
| **3** | **H-R15-C** zone de bruit MNQ × GEX | EV d'un challenge Lucid/Topstep ≈ +0 à +2 k USD/an si Sharpe ≥ 1 et MaxDD < 2 k | ≈ 20 % | très faible (fichier Exp 65 + DIX.csv, quelques minutes) | immédiat (rejet) ; forward Exp 67 en ombre |

A et B partagent le même calcul. **Un REJET de A entraîne celui de B** (même signal). Ils ne comptent pas comme deux preuves indépendantes.

### 5.1 Préenregistrement proposé — Exp 68 (H-R15-A) : tendance multi-horizons long/cash, SOL/BTC/ETH

- **Règle (unique, celle de Zarattini-Pagani-Barbon 2025, simplifiée et figée) :**
  - Closes journaliers à 00:00 UTC (Binance, cache 1 min).
  - Pour chaque actif i et chaque horizon n ∈ {5, 10, 20, 30, 60, 90, 150, 250, 360} : état = 1 si close > max(close des n jours précédents) ; retour à 0 si close < (max + min)/2 des n derniers closes (aujourd'hui inclus) ; sinon, l'état est conservé.
  - Signal_i = moyenne des 9 états.
  - Poids w_i = signal_i × min(1 ; 0,25/σ_i)/3, où σ_i = écart-type des rendements journaliers sur 60 jours × √365. Somme des poids ≤ 1 ; le reste en USDC.
  - Décision à la clôture J, détention sur J+1.
  - Code de référence : `docs/agents/research/H-R15_scripts/trend.py` (`run_spot`), à reprendre tel quel.
- **Coût :** 0,05 % AR sur la rotation (principal) ; stress à 0,20 % AR pour BTC/ETH, rapporté. **Rendement du cash = 0 pour la décision** ; avec la série USDC Kamino (T-029), rapporté.
- **Périodes :**
  - P1 = 2020-10-01 → 2025-03-27 : en échantillon, **déjà vu par le Chercheur** (§3.1), rapporté sans effet.
  - **P2 = 2025-03-28 → 2026-08-17 : décisionnelle.** C'est après publication pour l'article. Elle a été vue par l'Exp 56 pour une autre règle, et **le régime y est connu (panier −14 %/an)** : biais possible en faveur d'une règle long/cash, que les critères compensent en exigeant un Sharpe et pas seulement un « moins pire que le panier ».
- **Critères (P2) :**
  - **PASS** si les quatre conditions sont remplies : Sharpe net ≥ 0,5 ; MaxDD ≥ −15 % ; CAGR net > 0 ; Sharpe > celui du panier 1/3 détenu.
  - **REJET** si Sharpe net ≤ 0 ou MaxDD < −20 %.
  - **INCERTAIN** sinon.
  - **Rapporté sans effet :** par actif, par année, stress de coût, rendement du cash, rotation, nombre de swaps, pire jour.
- **Variantes :** **1 décisionnelle.** Compteur de la famille momentum série-temporelle crypto : Exp 56 (3) + exploratoires T-054 (6 configurations de tendance, 3 tv au comptant, 2 univers) + 1.
- **Si PASS :** forward papier 3 mois (contrôle d'implémentation, sans argent), cotations `/build` réelles à chaque rebalancement. Le « go » argent réel revient à l'auteur. **Si REJET :** famille fermée pour le capital propre, et H-R15-B tombe avec.

### 5.2 Préenregistrement proposé — Exp 69 (H-R15-B) : même signal, règles Propr Classic 1-Step 10 K

- **Prérequis :** Exp 68 ≠ REJET.
- **Règle :** signal et poids de l'Exp 68, **long seul**, en perps BTC/ETH/SOL.
  - Échelle fixe **k = 0,69** = 0,08 / 0,116, où 0,116 est la vol de la règle sur P1, mesurée avant P2. Elle vise ≈ 8 % de vol, entre le DD de 6 % et l'objectif de 10 %.
  - Pas de mise à l'échelle par la vol du PnL.
- **Coûts :** 0,075 % par côté sur la rotation ; **funding horaire Hyperliquid réel** (API `fundingHistory`, BTC/ETH/SOL), payé par le long ; prix de référence = bougies journalières Hyperliquid (rapporter l'écart avec Binance).
- **Règles simulées :**
  - perte journalière 3 % du solde de début de journée UTC, mesurée sur le **pire intrajournalier** (somme des w × (bas/close précédent − 1), tous les plus bas supposés simultanés) ;
  - DD statique de 6 % ; objectif +10 %.
- **P2 = 2025-03-28 → 2026-08-17 (décisionnelle).** Départs glissants chaque jour de P2, horizon jusqu'à la fin de P2.
- **Critères :**
  - **PASS** si Sharpe net (perp, funding inclus) ≥ 0,5 **et** P(échec) ≤ 0,35 sur les départs glissants **et** aucun pire intrajournalier ≤ −3 %.
  - **REJET** si Sharpe ≤ 0 **ou** P(échec) > 0,5.
  - **INCERTAIN** sinon.
  - Rapporté : P(réussite), délai médian, funding payé en %/an, EV par tentative selon le modèle de §3.2.
- **Variantes :** 1. Les 10 cryptos et la version long/court sont exclues (déjà vues, non retenues).
- **Si PASS :** 3 mois sur l'environnement Beta de Propr (l'exécuteur dry-run existe), lecture du `tradingFeeRate` réel, contrôle du funding appliqué. Ensuite seulement, demander à l'auteur un « go » pour **une seule** évaluation 10 K (110 USD). Pas de cycling.

### 5.3 Préenregistrement proposé — Exp 70 (H-R15-C) : zone de bruit MNQ, sans trade les jours de GEX élevé

- **Étape 0 (bloquante), contre la révision des données :**
  - comparer l'instantané gelé (sha256 ci-dessus) à au moins 2 copies archivées de DIX.csv (Wayback Machine, une en 2023 ou avant, une en 2025), sur toutes les dates communes ;
  - si plus de 1 % des valeurs de `gex` diffèrent de plus de 1 %, **REJET pour données révisées** (biais de prévision impossible à exclure) ;
  - si aucune archive n'est trouvable, le dire et passer en **forward seul**.
- **Règle :** moteur et lecture de l'Exp 64, inchangés (commit 33b5a15). Le jour J est **à plat** si pct(GEX de J−1) > 2/3, où pct = rang de GEX(J−1) parmi les 251 valeurs précédentes. Sinon, la règle s'applique sans changement.
- **Données de décision :** `docs/agents/results/Exp-65_2026-10-08_daily.csv`, fenêtre **H = 2024-03-05 → 2026-08-18**, MNQ (le HOLDOUT a été consommé par l'Exp 65, mais le découpage par GEX n'a jamais été regardé). P1 a déjà été vu par le Chercheur et n'est rapporté qu'à titre d'information.
- **Critères (H, MNQ) :**
  - **PASS** si les quatre conditions sont remplies : Sharpe net filtré ≥ 0,8 ; MaxDD filtré ≥ −2 000 USD ; part du net venant des 5 meilleurs jours ≤ 50 % ; Sharpe filtré ≥ Sharpe non filtré (0,81).
  - **REJET** si MaxDD filtré < −2 500 USD, ou Sharpe filtré < 0,5, ou Sharpe filtré < non filtré.
  - **INCERTAIN** sinon.
  - **Rapporté sans effet :** SP500 → MES (même filtre), seuil 1/2 au lieu de 2/3, pire jour, jours < −1 000 USD.
- **Variantes :** 1 décisionnelle (seuil 2/3 fixé ici). Les 4 regards exploratoires de P1 sont comptés.
- **Si PASS :**
  1. Ombre forward : appliquer le filtre aux décisions de l'Exp 67 à partir de DIX.csv téléchargé avant 09:30 ET chaque jour. **Aucun runner n'est modifié** : calcul hors ligne.
  2. Rejouer la série filtrée par bootstrap par blocs dans `funded_futures_ev_sim.py` (règles Lucid Flex et Topstep 50K).
  3. Demander un « go » pour un challenge seulement si la borne basse de l'EV est > 0.

---

## 6. Arithmétique honnête de « 15 %/an » et capital nécessaire

| Voie | Rendement attendu (hors échantillon, mon estimation) | Capital | Pire cas |
|---|---|---|---|
| A seul (capital propre) | +5 à +12 %/an (cash compris) | 500 CAD suffisent (aucun minimum) ; la taille ne change pas le % | −15 à −25 % sur le capital |
| A + stratégie A actuelle (D-TIME50) | +5 à +15 %/an, corrélés (deux paris longs crypto) | 500 CAD partagés | −25 à −35 % |
| B (Propr 10 K) | EV +50 à +290 USD par tentative de 110 USD, si payouts honorés ⇒ **≈ +15 à +55 %/an sur 500 CAD**, très incertain | 110 USD par tentative ; 999 USD pour 100 K (au-delà du budget) | −110 USD par tentative ; perte des gains si Propr fait défaut |
| C (Lucid/Topstep 50 K) | ≈ 0 à +2 000 USD/an si Sharpe ≥ 1 et MaxDD < 2 000 USD ; ≈ −200 à −400 USD si edge nul | ≈ 175 USD (Lucid) ou 49 USD/mois + API (Topstep) | perte des frais |

**Conclusion :**
- **Avec son propre capital, je ne vois pas de voie crédible vers 15 %/an** dans ces contraintes. L'option la plus proche (A) vaut probablement 5-12 %.
- **Les 15 % ne sont atteignables qu'avec un compte funded (B, puis C)**, à trois conditions :
  - un Sharpe hors échantillon ≥ ~0,7 ;
  - une queue gauche contenue, ce qui est le cas de A/B par construction (pire jour −3,6 %) ;
  - une firme qui paie.

  Cette dernière condition **ne se teste pas sur l'historique**.

## 7. Compteur de calculs exploratoires (ne comptent pas)

- **Tendance** (`trend.py`, ≤ 2025-03-27 seulement) :
  - 6 configurations : panier, long/cash B3, long/court B3, long/court 10, long 10, jambe courte ;
  - 3 tv au comptant (0,25 / 0,50 / 0,75, plus une ligne avec cash) ;
  - simulations Propr : long/court 10 × 4 V, long/court B3 × 2 V, long 10 × 3 V, long B3 × 3 V (échelle par la vol du PnL), long B3 × 3 k fixes.
  - Biais de survie possible sur l'univers à 10 (cryptos choisies en 2026).
- **GEX** (`gex_split.py`, P1 Exp 64 seulement) : terciles × 2 indices, GEX < 0 × 2 indices, 1 filtre (2/3) × 2 indices. **Fenêtre H de l'Exp 65 non regardée.**
- **Boucle LST** (`loop.py`) : 3 leviers (3 / 5 / 7,5).
- Aucun calcul sur le registre de trades de la stratégie A ni sur les données Exp 50/HOLDOUT.

## 8. Sources (consultées le 2026-10-09)

- Zarattini, Pagani, Barbon (2025), *Catching Crypto Trends: A Tactical Approach for Bitcoin and Altcoins*, SSRN 5209907 : https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907 ; page de l'auteur : https://abarbon.com/papers/catching-crypto-trends ; résumé des règles (CXO Advisory, non académique) : https://www.cxoadvisory.com/technical-trading/crypto-asset-trend-following-strategies/ ; Concretum : https://concretumgroup.com/catching-crypto-trends-a-tactical-approach-for-bitcoin-and-altcoins/
- Liu, Tsyvinski (2021), *Risks and Returns of Cryptocurrency*, RFS (déjà cité dans H-R_MARKETS).
- Moskowitz, Ooi, Pedersen (2012), *Time Series Momentum*, JFE ; Hurst, Ooi, Pedersen (2017), *A Century of Evidence on Trend-Following Investing* (cités, non relus aujourd'hui).
- Propr, règlement v1.0 (2026-02-25) : https://propr.xyz/rules ; revue (non académique) : https://fundedtrading.com/propfirm/propr/ ; Trustpilot : https://ca.trustpilot.com/review/propr.xyz ; annonce de lancement : https://regional-front.cointelegraph.com/press-releases/propr-launches-onchain-prop-trading-firm-hyperliquid
- Hyperliquid, funding : https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding ; API `info` (`fundingHistory`, `candleSnapshot`) testée : https://api.hyperliquid.xyz/info
- Baltussen, Da, Lammers, Martens (2021), *Hedging Demand and Market Intraday Momentum*, JFE : https://www3.nd.edu/~zda/intramom.pdf ; https://pure.eur.nl/en/publications/hedging-demand-and-market-intraday-momentum/
- SqueezeMetrics, DIX/GEX (non académique) : https://squeezemetrics.com/monitor/static/DIX.csv ; mécanisme GEX (non académique) : https://spotgamma.com/gamma-exposure-gex/
- Déblocages : Keyrock via CryptoSlate (2024-12-06, non académique) : https://cryptoslate.com/90-of-token-unlocks-drive-prices-down-declines-begin-a-month-ahead/ ; BeInCrypto : https://beincrypto.com/keyrock-research-token-unlocks/ ; Tokenomist (2026-06-29, non académique) : https://tokenomist.ai/research/do-token-unlocks-crash-prices ; API d'émissions DefiLlama payante (HTTP 402) : https://api.llama.fi/emissions
- Kamino, réserves et historique (API officielle) : https://api.kamino.finance/kamino-market/7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF/reserves/metrics ; jitoSOL APY (DefiLlama, agrégateur) : https://yields.llama.fi/chart/0e7d0722-9054-4907-8593-567b353c0900 ; Kamino Multiply (non académique) : https://eco.com/support/en/articles/15083163-kamino-finance-guide
- Options Solana : SolanaFM (non académique) https://solanafm.substack.com/p/what-are-the-best-strategies-involving ; Amplify SOLM : https://amplifyetfs.com/wp-content/uploads/files/Amplify_SOLM_FactSheet.pdf
- Calendrier crypto : Quantpedia (non académique) https://quantpedia.com/are-there-any-simple-calendar-effects-in-bitcoin-market/ ; https://ideas.repec.org/a/ahs/journl/v9y2024i1p43-60.html

## 9. Questions ouvertes pour l'orchestrateur

1. Exécuter d'abord l'Exp 68, puis l'Exp 69 (même calcul, une heure au plus), puis l'Exp 70 (quelques minutes). Elles sont indépendantes de toute modification d'un runner.
2. Propr : faire vérifier par l'agent Plateformes, sans argent :
   - le `tradingFeeRate` réel ;
   - l'application du funding ;
   - la clause « herd/off-the-shelf » appliquée à une règle publiée ;
   - l'historique public des payouts (on-chain).
3. Fichiers écrits hors de `research/` : aucun. Aucun fichier Codex modifié.
