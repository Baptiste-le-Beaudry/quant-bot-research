# H-R20 — Viser ≥ 15 %/an net sur longue période : classement des prochaines pistes (T-071, agent Chercheur, 2026-10-11)

- **Branche :** `agents/t071-hr20` (depuis `agents/orchestration-20261006`, commit ba53a83).
- **Statut :** revue de littérature. **Aucun backtest**, aucune donnée de rendement téléchargée. Le seul calcul (§1) est une identité arithmétique, **exploratoire, ne compte pas**.
- **Profil visé :** l'auteur, Québec, ≈ 15 000 CAD, CELI disponible, accepte un MaxDD jusqu'à −50 %, veut ≥ ~15 %/an net à long terme.
- **Sources :** consultées le 2026-10-11 (§8). « Non académique » = praticien, émetteur de FNB ou presse.

## 0. Réponse courte

1. **Le levier seul ne suffit pas.** Avec un taux sans risque ≈ 3,5 % et un coût de levier ≈ 1 %/an, il faut un **Sharpe net durable d'au moins 0,63-0,73** pour faire 15 %/an à une volatilité de 20-25 % (celle qui donne un MaxDD autour de −40 à −50 %). Le S&P 500 seul a un Sharpe de **0,52** sur 1990-2026 (Exp 74). Il faut donc **d'abord augmenter le Sharpe**, puis seulement ajouter du levier. Le seul moyen documenté sur longue période est d'**empiler des sources de rendement peu corrélées** (« return stacking »).
2. **Piste n° 1 recommandée pour l'Exp 76 : actions ×1 + tendance multi-actifs (managed futures) ×1 empilées**, c'est-à-dire 100 % S&P 500 + 100 % d'une stratégie de tendance en futures, financée par la marge des futures.
   - Mécanisme : la tendance a un Sharpe positif à chaque décennie depuis 1880, une corrélation ≈ 0 avec les actions et elle gagne dans 8 des 10 pires baisses du 60/40 (Hurst, Ooi, Pedersen 2017).
   - Données gratuites sur 41 ans : facteur TSMOM d'AQR (1985 →) + Ken French.
   - Faisable dans le CELI sans marge : RSST (FNB US tout-en-un), ou HSU (S&P ×2, canadien) + DBMF.
   - Probabilité estimée d'atteindre 15 %/an net sur 10-20 ans : **≈ 25-30 %**. C'est la meilleure de la liste, pas une certitude.
3. **Aucune piste n'a plus d'une chance sur trois** d'atteindre 15 %/an net. Le chiffre honnête de l'Exp 74 (≈ 12 %/an attendu) est proche du plafond réaliste. La valeur de la piste n° 1 est surtout de **réduire le MaxDD à rendement égal**, ce qui permet un peu plus de levier.
4. **À ne pas tester :** Nasdaq-100 ×2 filtré (déjà vu dans l'Exp 74 : MaxDD −72 %, hors contrainte) ; vente de puts à levier (H-R16 : dominée par l'indice) ; GEM et rotation sectorielle hebdomadaire (H-R16, H-R18).
5. **Prior sur l'Exp 75 (en cours, je ne la refais pas) :** Cederburg et al. (2020, JFE) trouvent que, testés en temps réel sur 103 stratégies, les portefeuilles à volatilité gérée font **en général moins bien** en Sharpe que les portefeuilles non gérés. Pour un indice de marché seul, l'effet est plus favorable (Moreira-Muir, Harvey et al.), mais le prior de PASS de l'Exp 75 devrait être modeste (≈ 25-35 %).

## 1. La barre à franchir (exploratoire, ne compte pas)

Identité approximative : CAGR ≈ rf + Sharpe × σ − σ²/2 − coût du levier.
Hypothèses : rf = 3,5 %, coût du levier 1 %/an, cible 15 %.

| Volatilité du portefeuille σ | Sharpe net nécessaire | MaxDD typique à cette volatilité (ordre de grandeur, d'après Exp 74) |
|---|---|---|
| 15 % | 0,91 | −30 à −55 % (S&P ×1 : −55 % en 2008) |
| 20 % | 0,73 | −40 à −45 % |
| 22 % | 0,68 | ≈ −45 % |
| 25 % | 0,63 | −45 à −55 % |
| 30 % | 0,57 | −55 à −65 % (×2 sans filtre : −88 %) |

Lecture :
- La fenêtre utile est σ ≈ 20-25 %. Au-delà, la traînée de volatilité (σ²/2) et le MaxDD sortent du cadre.
- Il faut donc un **Sharpe net ≥ ≈ 0,65 sur 25 ans et plus**. Les références :
  - S&P 500 1990-2026 : 0,52 ; règle Exp 74 : 0,55 ; post-2016 : 0,76-0,80 (décennie exceptionnelle) ;
  - 60/40 SPY/IEF 2004-2026 : 0,72 (H-R16), mais porté par 40 ans de baisse des taux ;
  - 80 % 60/40 + 20 % tendance, 1880-2016, net de frais 2/20 : **0,55** contre 0,39 pour le 60/40 seul (Hurst et al. 2017, Exhibit 7). **C'est le gain de Sharpe le mieux documenté sur la plus longue période.**
- Les prévisions 2026 des gérants (AQR : ≈ 3,9 % réel pour les actions US, H-R16) sont plus basses que l'historique. Tout Sharpe historique doit être décoté.

## 2. Anti-doublon (lu avant d'écrire)

| Déjà vu | Où | Conséquence ici |
|---|---|---|
| S&P ×2 + MM200 : PASS mécanique, à nuancer (levier, pas edge ; ≈ 12 %/an attendu) | Exp 74, T-069 | sert de **référence** ; ne pas refaire |
| S&P à volatilité ciblée contre levier constant à vol égale | Exp 75 (en cours) | ne pas refaire ; prior §0.5 |
| NDX/RUT/DAX ×2 + MM200 | Exp 74 critère 4 | NDX : 19,7 % / **−71,7 %** ; déjà vu → post hoc et hors MaxDD |
| Vente de puts, condors, puts nus | H-R16 §3.2 | dominés par l'indice → exclus |
| Trend sur micro-futures à 15 k | H-R16 §3.3 | trop granulaire ; la version FNB (DBMF) est la bonne |
| GEM (dual momentum), GTAA-5, 60/40, DBMF, KMLM détenus seuls | H-R16 §3.5 | descriptifs seulement ; aucun ne fait 15 % seul |
| FNB à levier détenus en permanence (TQQQ/UPRO, HFEA) | H-R16 §3.6 | écartés seuls ; **réexaminés ici seulement comme brique d'empilement** |
| Rotation sectorielle **hebdomadaire**, RSI(2), nuit SPY, tournant du mois | H-R18 | ≈ 0 ; l'horizon mensuel 12-1 n'a pas été testé |
| Tendance crypto long/cash, momentum crypto journalier | Exp 56, Exp 68 | rejetés ; la crypto n'est examinée ici que comme poche passive |
| `docs/research_plan_status.md` | — | aucune étude d'empilement, de parité de risque, de facteurs ou d'or |

Compteur de multiple testing : 75 essais à ce jour (Exp 75 incluse). Ce document n'en ajoute aucun.

## 3. Tableau de classement

« P(15 %) » = ma probabilité subjective que la règle fasse ≥ 15 %/an net sur les 10-20 prochaines années avec un MaxDD ≥ −50 %. « P(PASS) » = probabilité qu'un test préenregistré du type §5 passe.

| Rang | Piste | Mécanisme (une ligne) | Preuve hors échantillon | Données gratuites ≥ 25 ans | CELI (sans marge) | Risque Ahamed | P(15 %) | P(PASS) |
|---|---|---|---|---|---|---|---|---|
| **1** | **Actions ×1 + tendance ×1 empilées** (RSST ; HSU + DBMF) | 2 primes peu corrélées ; la tendance gagne dans les baisses lentes | 137 ans (HOP 2017), mais Sharpe net 0,41 en 2010-16 ; SG Trend 2000-2025 : 5,2 %/an, MaxDD −21 % | oui : AQR TSMOM 1985 → + Ken French | oui (RSST ; ou 50 % HSU + 50 % DBMF) | faible (1-4 rééquilibrages/an) | **25-30 %** | 35 % |
| 2 | Actions + obligations à levier (90/60 type NTSX, ×1,2-1,5) | prime de terme + aversion au levier (Asness et al. 2012) | 2022 : NTSX −25,8 % ; Anderson et al. 2012 : gain mangé par les coûts de levier | oui : Shiller + FRED GS10 (1953 →), Damodaran annuel 1928 → | oui (NTSX US) ; ou HSU + ZFL | faible | 15-20 % | 25 % |
| 3 | Actions + or empilés (90/90 type GDE) | diversification ; l'or n'a pas de prime (Erb-Harvey 2013) | GDE depuis 2022 seulement (période de hausse de l'or) | partiel : or libre depuis 1971-75 ; Yahoo GC=F 2000 → | GDE (US) ; ou HSU + CGL.C | faible | 15 % | 20 % |
| 4 | Poche BTC 5-10 % rééquilibrée sur la piste 1 ou sur un indice ×L | prime de rééquilibrage sur un actif très volatil peu corrélé | 2014-2026 seulement, un seul régime ; études d'émetteurs (Bitwise, Nickel) | **non** (≈ 12 ans) | oui : BTCC, FBTC, EBIT | faible | 25 % (preuve faible) | non testable sur 25 ans |
| 5 | Momentum sectoriel mensuel (12-1, top 3 de 12 secteurs) ×1,25 | Moskowitz-Grinblatt 1999 | décroissance après publication ; les FNB sectoriels ont réduit l'effet | oui : Ken French 12 industries 1926 → | partiel : secteurs ×1 + HSU | moyen (12-36 trades/an) | 10-15 % | 20 % |
| 6 | Facteurs long seulement (momentum, qualité, petite valeur) ×1,25 | primes de facteurs | −58 % après publication en moyenne (McLean-Pontiff 2016) ; petite valeur à plat 2007-2020 | oui : Ken French 1926 →, AQR QMJ 1957 → | oui (FNB facteurs + HSU) | faible | 10 % | 15 % |
| 7 | Nasdaq-100 ×2 + MM200 (HQU, QLD) | levier sur l'indice le plus fort de la dernière décennie | **déjà vu** (Exp 74) : MaxDD −71,7 % depuis 1990 | — | — | — | **exclu** | — |
| 8 | Vente de puts à levier | prime de volatilité | H-R16 : PUT Sharpe 0,47 < SPY 0,56, MaxDD −37 % à ×1 | — | — | — | **exclu** | — |
| — | Repli si tout échoue : levier constant ×1,25-1,3 sur actions mondiales (HEQL ; ou XEQT + HSU) | « diversification dans le temps » pour un jeune investisseur (Ayres-Nalebuff 2013) | c'est la **référence** de T-069 : ≈ 8-12 %/an attendu, MaxDD −60 % possible sur 1990-2026 à vol égale (T-069 §4) | oui | oui | nul | 10-15 % | n/a |

## 4. Détail par piste

### 4.1 Piste 1 — Actions ×1 + tendance ×1 empilées (recommandée pour l'Exp 76)

**Mécanisme.**
- La tendance (time-series momentum) achète ce qui monte et vend ce qui baisse, sur ≈ 60 marchés : indices, obligations, devises, matières premières (Moskowitz, Ooi, Pedersen 2012).
- Explication proposée : sous-réaction puis sur-réaction des investisseurs, et participants qui ne cherchent pas le profit (banques centrales, couvertures). La tendance profite des **baisses lentes** (2000-02, 2008, 2022), qui sont celles qui font les gros MaxDD d'un portefeuille d'actions à levier.
- « Empiler » : 100 $ de capital donnent 100 $ d'actions + 100 $ de tendance, car les futures ne demandent qu'une marge. On ajoute une source de rendement sans retirer les actions (Hoffstein et Gordillo 2021, non académique).

**Chiffres publiés.**

| Source | Période | Résultat |
|---|---|---|
| Hurst, Ooi, Pedersen (JPM 2017), Exhibit 1 | 1880-2016 | excès net de 2/20 et de coûts : **7,3 %/an**, vol 9,7 %, Sharpe **0,76** ; corrélation actions −0,01 |
| idem, par décennie | 2000-2009 / 2010-2016 | Sharpe net 0,61 / **0,41** (après publication de MOP 2012 : plus faible) |
| idem, Exhibit 7 | 1880-2016 | 60/40 : Sharpe 0,39, MaxDD −62 % ; 80 % 60/40 + 20 % tendance : Sharpe **0,55**, MaxDD **−50 %** |
| idem, Exhibit 6 | 10 pires baisses du 60/40 | tendance positive dans 8 sur 10 (exceptions : 1937, krach de 1987) |
| Huang, Li, Wang, Zhou (JFE 2020) | 1985-2015 | la prévisibilité actif par actif est faible ; le profit de la stratégie existe mais ressemble à celui d'une stratégie « moyenne historique ». **Critique sérieuse : le gain vient surtout de la diversification et du levier, pas d'une prédiction fine.** |
| SG Trend Index (TTU, non académique) | 2000-01 → 2025-10 | CAGR **5,23 %** (intérêts du collatéral inclus), MaxDD −20,6 %. 2022 : +27,4 % ; 2025 : ≈ +2,4 % |
| DBMF (H-R16) | 2019-06 → 2026-10 | CAGR 9,7 %, Sharpe 0,64, MaxDD mensuel −17 % |
| RSST (émetteur/presse, non académique) | 2023-09 → | MER 0,99 % ; +20,6 % de lancement à 2024-08 ; +9,3 % sur 12 mois à 2025-10 |

**Pourquoi ça pourrait atteindre 15 % (calcul d'ordre de grandeur, ne compte pas).**
- Hypothèses prudentes : actions excès 5 %/an à 16 % de vol (Sharpe 0,31, décoté) ; tendance excès net 3 %/an à 12 % de vol (Sharpe 0,25, niveau SG Trend 2000-25) ; corrélation −0,1.
- Empilement 100/100 : excès 8 %, vol ≈ 19 %, Sharpe ≈ 0,42 → CAGR ≈ 3,5 + 8 − 1,8 − 1 ≈ **8,7 %**.
- Hypothèses historiques (actions Sharpe 0,45, tendance Sharpe 0,6) : excès ≈ 14,4 %, vol ≈ 19 %, Sharpe ≈ 0,76 → CAGR ≈ **15,1 %**.
- Donc : **15 % seulement si la tendance retrouve son Sharpe historique et que les actions gardent le leur.** D'où P(15 %) ≈ 25-30 %. L'apport sûr est la baisse du MaxDD dans les krachs lents.

**Ce qui pourrait la tuer.**
- Décennie 2010-2019 : la tendance a peu rapporté (taux bas, peu de crises lentes). Si ce régime revient, l'empilement ≈ actions ×1 moins les frais (≈ 1 %/an).
- Krachs rapides (1987, mars 2020) : la tendance n'a pas le temps de se retourner.
- Frais : RSST 0,99 %, DBMF 0,85 %, HSU ≈ 1,5 % (frais totaux rapportés, à vérifier).

**Mise en œuvre au Québec.**

| Option | Contenu | Exposition | Frais | CELI | Remarques |
|---|---|---|---|---|---|
| A | 100 % RSST | 100 % actions US + 100 % tendance | 0,99 % | oui (FNB US, retenue de 15 % sur les dividendes) | un seul titre, aucun rééquilibrage ; historique court (2023) ; gestionnaire de tendance = ReSolve |
| B | 50 % HSU + 50 % DBMF | 100 % S&P + 50 % tendance | ≈ 0,76 + 0,43 = 1,2 % | oui | rééquilibrage trimestriel ; HSU est ×2 quotidien (dérive) |
| C | 50 % HSU + 25 % DBMF + 25 % XEQT | ≈ 125 % actions + 25 % tendance | ≈ 1 % | oui | plus proche des actions ×L ; moins de tendance |

- Les FNB à levier et les FNB américains sont des placements admissibles au CELI. La marge et les futures ne le sont pas (H-R16 §3.5).
- Risque « entreprise » (Ahamed, 2024 FCA 108) : faible avec 1 à 4 rééquilibrages par an et une détention longue.
- Disponibilité de RSST, DBMF et HSU chez Wealthsimple, NBDB, Questrade ou IBKR : **à vérifier** avant tout argent réel.

### 4.2 Piste 2 — Actions + obligations à levier (90/60, parité de risque légère)

- **Mécanisme.** Les investisseurs qui refusent le levier surpayent les actifs risqués ; les actifs sûrs (obligations) offrent plus de rendement par unité de risque. Les détenir à levier aide (Asness, Frazzini, Pedersen 2012 ; Frazzini-Pedersen 2014).
- **Contre-preuve.** Anderson, Bianchi, Goldberg (FAJ 2012) : sur 1926-2010, après coûts réels de financement et de transaction, la parité de risque à levier n'est pas meilleure de façon fiable, et le résultat dépend des dates de début et de fin.
- **Hors échantillon récent.** 2022 : actions et obligations ont baissé ensemble. NTSX −25,8 % en 2022 ; pire baisse −32 % (2021-12 → 2024-07, 30 mois sous l'eau). Le portefeuille UPRO/TMF « HFEA » (forum Bogleheads, non académique) a perdu ≈ −80 % en 2022 (H-R16).
- **Pour.** Les taux sont ≈ 4 % (et non 0,5 % comme en 2020) : la prime de terme future est moins négative qu'à l'époque.
- **Données.** Shiller (mensuel 1871 →, avec le taux 10 ans), FRED GS10 (1953 →) pour reconstruire un rendement obligataire, Damodaran (annuel 1928 →). Vérification sur NTSX (2018 →).
- **CELI.** NTSX (US) ; ou HSU + obligations longues canadiennes (ZFL). Faible rotation.
- **Verdict.** Utile comme 3e brique de la piste 1 (actions + obligations + tendance) ; seule, la corrélation actions-obligations positive (années 1970, 2022) la rend fragile. P(15 %) ≈ 15-20 %.

### 4.3 Piste 3 — Actions + or empilés (90/90)

- **Mécanisme.** L'or est peu corrélé aux actions et protège parfois en crise. Mais il n'a **pas de prime de risque** : rendement réel de long terme ≈ 0, et un prix réel élevé annonce des rendements futurs faibles (Erb et Harvey 2013).
- **Hors échantillon.** GDE (WisdomTree, 0,20 % de frais) existe depuis 2022-03, en pleine hausse de l'or : en tête de sa catégorie à 2025-09 (émetteur, non académique). C'est un biais de période, pas une preuve.
- **Données.** Or libre seulement depuis 1971-1975. Séries gratuites : Yahoo GC=F (2000 →), séries LBMA via d'autres sources (FRED a retiré la série LBMA en 2022), Damodaran annuel.
- **CELI.** GDE (US) ; ou HSU + CGL.C.
- **Verdict.** Diversifiant plausible ; espérance faible ; l'or est au plus haut en 2025-26. P(15 %) ≈ 15 %.

### 4.4 Piste 4 — Poche bitcoin 5-10 %

- **Mécanisme.** Un actif très volatil et peu corrélé, rééquilibré, ajoute une prime de rééquilibrage. Aucun modèle académique ne lui donne une espérance positive démontrée.
- **Preuves.** Seulement des études d'émetteurs ou de gérants crypto (non académiques) : Nickel (2012-12 → 2024-09, 5 % de BTC dans un 60/40 : cumul 396 % contre 199 %) ; Bitwise (BTC positif dans 100 % des périodes de 3 ans depuis 2014) ; Morningstar : à 5 %, le BTC fait déjà plus de 20 % du risque total.
- **Problème.** ≈ 12 ans de données, un seul régime (adoption). Impossible de satisfaire « ≥ 25 ans ou plusieurs marchés ». Le BTC a eu trois baisses de −75 à −85 %.
- **CELI.** BTCC, FBTC, EBIT (FNB canadiens au comptant).
- **Verdict.** C'est un **pari**, pas une stratégie testable. Si l'auteur le veut, 5 % maximum, rééquilibré une fois par an, présenté comme tel. Pas de préenregistrement proposé.

### 4.5 Piste 5 — Momentum sectoriel mensuel

- **Mécanisme.** Moskowitz et Grinblatt (1999) : le momentum des industries explique une grande partie du momentum des actions.
- **Hors échantillon.** L'effet a faibli depuis la publication et l'arrivée des FNB sectoriels (Quantpedia, non académique). H-R18 : la rotation **hebdomadaire** ≈ 0. Le surplus attendu ≈ 1-3 %/an au mieux, avec une volatilité de suivi de 5-8 %.
- **Données.** Ken French, 12 et 49 industries, 1926 →.
- **CELI.** FNB sectoriels US ×1 (pas de levier sectoriel liquide) + HSU pour le levier global. 12-36 transactions par an : risque Ahamed moyen.
- **Verdict.** Un surplus de 1-2 %/an ne change pas la conclusion du §1. P(15 %) ≈ 10-15 %.

### 4.6 Piste 6 — Facteurs long seulement à levier modéré

- **Mécanisme.** Primes momentum, qualité (QMJ, Asness et al. 2019), petite valeur.
- **Hors échantillon.** McLean et Pontiff (2016) : en moyenne −26 % hors échantillon et **−58 % après publication**. En long seulement, on ne capte qu'une partie de la prime. La petite valeur a été à plat de 2007 à 2020.
- **Données.** Ken French (1926 →), AQR QMJ (1957 →).
- **Verdict.** Surplus réaliste ≈ 0-1,5 %/an après frais. P(15 %) ≈ 10 %.

### 4.7 Exclus

- **Nasdaq-100 ×2 + MM200.** Déjà calculé dans l'Exp 74 (critère 4) : 19,7 %/an mais **MaxDD −71,7 %** depuis 1990 (bulle de 2000). Il viole la contrainte de −50 %. Le choisir maintenant serait un choix post hoc sur la meilleure décennie du Nasdaq.
- **Vente de puts à levier.** H-R16 §3.2 : à ×1, Sharpe 0,47 < 0,56 et MaxDD −37 % ; à levier, MaxDD > −60 %.
- **Volatilité ciblée.** C'est l'Exp 75.

## 5. Brouillon de préenregistrement pour l'Exp 76 (piste 1)

À relire et figer par l'orchestrateur **avant tout téléchargement**. Je n'ai téléchargé aucune série de rendements.

**Hypothèse.** Un portefeuille empilé « actions US ×1 + tendance ×1 » a un Sharpe net supérieur d'au moins 0,10 à celui d'un portefeuille d'actions US à levier constant de même volatilité, sur 1985-2026, et ce gain se retrouve après publication et sur d'autres marchés d'actions.

**Données (gratuites, à citer avec la date de téléchargement).**
- Tendance : AQR « Time Series Momentum: Factors, Monthly » (1985-01 →, excès de rendement, 58 marchés, brut de coûts et de frais).
- Actions : Ken French, marché US (Mkt-RF + RF), mensuel ; pour le critère « autres marchés » : Ken French Developed ex US, Europe, Japon (1990-07 →).
- Taux : RF de Ken French.
- Contrôle d'instrument réel (rapporté, sans effet) : DBMF (2019-06 →), RSST (2023-09 →), HSU et SSO via Yahoo.

**Règle (fixée).**
1. TSMOM_t = série AQR « TSMOM » (portefeuille total), **remise à 10 % de volatilité annuelle** avec l'écart-type des 36 mois **précédents** (aucun regard en avant ; les 36 premiers mois servent au calcul et sont exclus).
2. Décote de la tendance : **−3,0 %/an** sur la poche (frais d'un FNB ≈ 0,9 % + coûts de mise en œuvre et écart entre un indice académique et un fonds réel ≈ 2 %).
3. Rendement mensuel du portefeuille : R = (Mkt-RF + RF) + w·(TSMOM_t − 3 %/12) − f, avec **w = 1,0** (décisionnel) et f = 0,5 %/an (frais de l'empilement sur la jambe actions).
4. Rééquilibrage mensuel (implicite dans la formule), coût 0,10 % × |variation de poids|, rapporté.

**Référence (le vrai test, recommandation T-069).**
- Actions US ×L constant : R_ref = L·(Mkt-RF) + RF − 1 %/an × max(L − 1, 0).
- L est choisi pour que la volatilité de la référence égale celle de la règle **sur la même période**.

**Périodes.**
- Entière : 1988-01 → dernier mois disponible.
- Avant publication : 1988-01 → 2012-05 (Moskowitz-Ooi-Pedersen, JFE 2012-05).
- Après publication : 2012-06 → fin.

**Critères (fixés).** PASS si tout est vrai :
1. ΔSharpe (règle − référence) ≥ +0,10 sur la période entière, **et** > 0 après publication.
2. **Robustesse fixée d'avance :** w = 0,5 et w = 1,5 ont aussi ΔSharpe > 0 sur la période entière ; et la règle w = 1,0 avec une décote de **4,5 %/an** garde ΔSharpe > 0.
3. **Même signe ailleurs :** même règle (même TSMOM, même décote, même référence construite sur le marché local) sur Developed ex US, Europe et Japon, 1990-07 → : ΔSharpe > 0 sur au moins 2 des 3.
4. **Rendement et risque :** CAGR net ≥ 15 % sur la période entière **ou** sur l'après-publication, et MaxDD **mensuel** ≥ −40 % sur la période entière (le MaxDD mensuel sous-estime le journalier d'environ 5-10 points).

REJET si ΔSharpe ≤ 0 sur la période entière, ou ≤ 0 sur 2 des 3 marchés du critère 3. INCERTAIN sinon.

**Rapporté sans effet.**
- CAGR, vol, MaxDD, pire année, par décennie ;
- part du surplus venant des 3 meilleures années ;
- fenêtres glissantes de 10 ans (part ≥ 15 %, part < 5 %) ;
- Deflated Sharpe avec N = 76 ;
- version « actions mondiales » (Ken French Developed) ;
- comparaison avec DBMF/RSST réels sur leur période (écart de suivi) ;
- résultats en CAD.

**Variantes comptées.** 1 décisionnelle (w = 1,0, décote 3 %). w = 0,5, w = 1,5 et la décote 4,5 % sont des contrôles obligatoires, pas des choix.

**Si PASS.** Revue du Validateur → fiche pratique CELI (option A ou B du §4.1, nombre de transactions, retenue US, change) → suivi papier 3 mois avec le comparateur « actions ×L constant » affiché à côté → décision de l'auteur.

**Probabilité a priori de PASS : ≈ 35 %.** Le critère 1 est probable sur la période entière (le gain de Sharpe est documenté), mais l'après-publication 2012-2019 a été faible pour la tendance, et le critère 4 (15 %) est exigeant.

**Limites connues avant calcul.**
- L'indice AQR est une construction académique brute de coûts. La décote de 3 % est une hypothèse, pas une mesure ; le contrôle DBMF/RSST ne couvre que 2019 → et 2023 →.
- Données mensuelles : le MaxDD journalier sera plus profond.
- Pour Developed ex US, Europe et Japon, la tendance reste la même série mondiale : le critère 3 teste la combinaison, pas l'indépendance de la tendance.

## 6. Ordre recommandé après l'Exp 76

1. Si l'Exp 76 passe : tester **actions + obligations + tendance** (piste 2 comme 3e brique), avec la même référence et les mêmes critères. Cette fois sur Shiller/FRED pour la jambe obligataire.
2. Si l'Exp 76 échoue : il ne reste aucune piste documentée capable de franchir la barre du §1. La recommandation honnête devient : **levier constant modéré (×1,25-1,3) sur actions mondiales dans le CELI**, ≈ 8-12 %/an attendu, MaxDD possible −55 à −65 %. Ou la règle Exp 74 si l'auteur préfère un MaxDD plancher plus bas à rendement comparable.
3. Pistes 3 à 6 : seulement si l'orchestrateur veut un test de fermeture ; leur P(15 %) ≤ 15 %.

## 7. Questions ouvertes

- Droits CELI réels de l'auteur (Mon dossier ARC) : si < 15 000 CAD, le surplus va dans un compte non enregistré, où la marge est possible (et la piste 1 se fait aussi avec 1 MES + DBMF, mais la granularité redevient un problème).
- Disponibilité de RSST, DBMF, GDE, NTSX et HSU chez le courtier choisi ; certains courtiers demandent une attestation pour les FNB à levier.
- Frais réels de HSU (sources : 1,52 % à 1,75 % ; à vérifier sur le site Global X).

## 8. Sources (consultées le 2026-10-11)

Académiques :
- B. Hurst, Y. H. Ooi, L. H. Pedersen (2017), « A Century of Evidence on Trend-Following Investing », *Journal of Portfolio Management* 44(1). PDF : https://fairmodel.econ.yale.edu/ec439/hurst.pdf (Exhibits 1, 6, 7 lus) ; https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing
- T. Moskowitz, Y. H. Ooi, L. H. Pedersen (2012), « Time Series Momentum », *JFE* 104(2) ; données à jour : https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Factors-Monthly (1985-01 →, mise à jour 2026-05-29)
- D. Huang, J. Li, L. Wang, G. Zhou (2020), « Time series momentum: Is it there? », *JFE* 135(3), 774-794 : https://ideas.repec.org/a/eee/jfinec/v135y2020i3p774-794.html
- S. Cederburg, M. O'Doherty, F. Wang, X. Yan (2020), « On the performance of volatility-managed portfolios », *JFE* 138, 95-117 : https://www.lehigh.edu/~xuy219/research/COWY.pdf
- C. Asness, A. Frazzini, L. H. Pedersen (2012), « Leverage Aversion and Risk Parity », *FAJ* 68(1) : https://www.aqr.com/Insights/Research/Journal-Article/Leverage-Aversion-and-Risk-Parity
- R. Anderson, S. Bianchi, L. Goldberg (2012), « Will My Risk Parity Strategy Outperform? », *FAJ* 68(6) : https://cdar.berkeley.edu/sites/default/files/2012_Anderson-et-al.-WillRiskStrategyOutperfom_1.pdf
- C. Erb, C. Harvey (2013), « The Golden Dilemma », *FAJ* 69(4) : https://www.nber.org/papers/w18706
- I. Ayres, B. Nalebuff (2013), « Diversification Across Time », *JPM* 39(2) : https://papers.ssrn.com/abstract=1687272
- D. McLean, J. Pontiff (2016), « Does Academic Research Destroy Stock Return Predictability? », *JF* 71(1) : https://ivey.uwo.ca/media/3775549/pontiff.pdf
- T. Moskowitz, M. Grinblatt (1999), « Do Industries Explain Momentum? », *JF* 54(4) ; résumé : https://quantpedia.com/strategies/sector-momentum-rotational-system
- M. Gayed, C. Bilello (2016), « Leverage for the Long Run » (article de l'Exp 74) : https://www.cxoadvisory.com/volatility-effects/leveraging-the-u-s-stock-market-based-on-sma-rules/
- Ken French Data Library : https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html ; Developed : https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_developed.html

Non académiques (praticiens, émetteurs, presse) :
- C. Hoffstein, R. Gordillo (2021), « Return Stacking: Strategies for Overcoming a Low Return Environment » : https://www.advisorperspectives.com/commentaries/2021/10/21/return-stacking-strategies-for-overcoming-a-low-return-environment
- RSST (lancement, frais, rendements) : https://www.itiger.com/news/2466431254 ; https://www.tradingview.com/symbols/CBOE-RSST/analysis
- SG Trend Index (CAGR 2000 →, MaxDD) : https://www.toptradersunplugged.com/trend-following-performance-report-october-2025/ ; 2022 : https://thefullfx.com/year-end-drop-fails-to-dampen-stellar-2022-for-trend-followers/
- NTSX 2022 et pire baisse : https://pictureperfectportfolios.com/wisdomtree-us-efficient-core-fund-ntsx-etf-review/
- GDE : https://www.wisdomtree.com/us/insights/blog/it-is-rare-to-be-1-september-30-2025-edition
- HEQL (Global X, ×1,25) : https://www.globalx.ca/wp-content/uploads/2026/08/HEQL-ETF_Fact_Sheet-EN.pdf
- HSU (S&P ×2 quotidien, Global X/BetaPro) : https://ycharts.com/companies/HSU.TO ; frais : https://cbonds.com/etf/8699/
- FNB à levier admissibles au CELI : https://www.stocktrades.ca/canadian-leveraged-etfs/
- Ahamed / Canadian Western Trust v. The King, 2024 FCA 108 : https://canadianlawyermag.com/cl-plus/cases/6268 ; https://www.advisor.ca/tax/tax-strategies/sleepwalking-into-day-trading-can-cause-tax-nightmares
- Bitcoin en portefeuille : https://financialinvestigator.nl/en/nieuws-detailpagina/2024/11/14/nickel-adding-bitcoin-to-balanced-portfolios-has-significant-positive-effect ; https://bitwiseinvestments.com/crypto-market-insights/bitcoins-role-in-a-traditional-portfolio ; https://www.morningstar.com/portfolios/how-much-bitcoin-is-too-much
- FNB de tendance cotés au TSX (historique, existence actuelle à vérifier) : https://stockchase.com/company/view/4495/HMF-T

Documents internes : `REPRISE.md` §3, `REGISTRY.csv`, `research/H-R16_capital_15k.md`, `research/H-R18_swing.md`, `results/Exp-74_2026-10-11.md`, `validation/T-069_exp74_review_2026-10-11.md`, `hypotheses/Exp-75.md`.
