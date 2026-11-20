# H-R_MARKETS — Une stratégie adaptée à chaque marché accessible depuis le Québec (~500 CAD, non strict)

- **Auteur** : agent Chercheur, tâche T-021 (élargissement demandé par l'auteur), 2026-10-06
- **Question** : pour chaque marché, quelle famille de stratégies a le meilleur edge **documenté net des
  coûts de détail**, sur quel instrument et avec quelle fréquence ? Ensuite : les 3 meilleures paires
  (marché, stratégie), chacune avec une prédiction chiffrée testable en historique.
- **Statut** : revue de littérature + 2 calculs exploratoires (**ne comptent pas**). Aucun test décisionnel.

## 0. Exclusions vérifiées (ne sont pas refaites)

| Déjà fait | Où | Verdict |
|---|---|---|
| Momentum/breakout crypto intraday B1-B8 ; funding BF1-BF2 ; rotation transversale journalière BR1-BR2 (top-2 / bottom-2, 7 jours) | `docs/strategy_b/`, `funding/`, `rotation/` | REJECT (BR1 : +22,6 %, MaxDD −74,6 % contre panier égal +178 %) |
| Indices Nasdaq : dérive intraday BI1, ORB BI2-BI3 | `docs/strategy_b/index/` | REJECT |
| Microstructure QQQ/SPY (déséquilibre, reversal) | Strategy C, C1-C2 | REJECT |
| Dip-buy indices/forex avec paramètres crypto | Exp 32 | REJECT |
| Dip-buy actions (config D) | Strategy A-Equity, Exp 47 | ≈ nul en réaliste (PF 1,21 → ≈ 1,04) |
| Dip-buy métaux/énergie | Exp 54 (en cours) | — |
| Momentum fin de séance / ETF à levier | H-R06 | rejet attendu à 500 CAD |
| Polymarket | H-R07 | bloqué au Québec |

## 1. Plateformes réalistes (rappel, pour les coûts)

| Plateforme | Marchés | Coût de détail | API | Québec |
|---|---|---|---|---|
| Jupiter `/build` (DEX Solana) | crypto spot (SOL, cbBTC, WETH, JUP…) | ≈ 0,00-0,03 % AR coté + ≈ 0,001-0,005 % frais réseau/swap (H-R08) | oui | aucune interdiction trouvée (inférence, T-004) ; serveur hors États-Unis |
| OANDA Canada | forex, CFD indices/métaux/pétrole | spread seul ; US500 ≈ 0,7 pt (≈ 0,01 %) ; financement long indices ≈ taux de référence + 2,5 %/an ; forex EUR/USD exemple −3,00 %/+1,60 % par an long/court ; marge forex 5 % | oui (v20 REST) | inscrit comme courtier en dérivés au Québec (page légale OANDA) ; disponibilité des **CFD** pour un résident du Québec **non vérifiée** |
| IBKR Canada | ETF, actions US | commission minimale par ordre (≈ 0,35-1 USD selon le forfait : **non vérifié**) ⇒ 0,1-0,3 %/côté à 350 USD | oui | oui |
| Wealthsimple | ETF, actions | 0 commission | **non** | oui (manuel, mensuel seulement) |
| CME micro via IBKR | futures | 0,05-0,23 % AR | oui | infaisable sous 2 000 USD (T-004) |

Conséquence : à 500 CAD, **une stratégie fréquente n'est viable qu'avec spread seul (OANDA, Jupiter)** ;
une stratégie mensuelle supporte les commissions minimales d'IBKR.

## 2. Par marché : familles documentées, ampleur nette plausible

### 2.1 Indices (S&P 500, Nasdaq 100)

| Famille | Preuve | Net plausible à 500 CAD | Instrument / fréquence | Verdict |
|---|---|---|---|---|
| **Tournant du mois** (dernier jour + 3 premiers jours) | McConnell et Xu (2008, FAJ) : 1926-2005, tout l'excès de rendement du marché US est concentré dans cette fenêtre ; présent dans 31 pays sur 35. Après les ETF, l'effet S&P se concentre sur le 1er jour (FPA 2011). Quantpedia : encore positif | brut historique ≈ 0,4-0,6 %/fenêtre ; coût CFD ≈ 0,01 % spread + 4-5 nuits de financement (≈ 0,02 %/nuit) ≈ 0,08-0,10 % ⇒ **≈ +0,3 %/mois sur 20 % du temps** ⇒ ≈ +3-4 %/an à 1×, ≈ +10 %/an à 3× | CFD US500 OANDA, 12 trades/an | **retenu (rang 2)** |
| Dérive overnight (close → open) | Cliff, Cooper et Gulen (2008) ; Lou, Polk et Skouras (2019) : momentum gagné la nuit | ≈ +3-4 pb/nuit brut historiquement, financement CFD ≈ 2 pb/nuit + spread 1 pb ⇒ ≈ 0 | CFD, 250 trades/an | écarté (coûts) |
| Dérive pré-FOMC | Lucca et Moench (2015) ; **disparue après 2015** (Kurov, Wolfe et Gilbert 2021, FRL) | ≈ 0 | — | écarté |
| Fin de séance / rebalancement ETF à levier | H-R06 | ≈ 0,01 %/jour | — | exclu (déjà fait) |
| Fade du gap d'ouverture | surtout praticiens (**non académique**) ; Strategy C REJECT sur la microstructure | non documenté net | — | écarté |

### 2.2 Or, argent, pétrole

| Famille | Preuve | Net plausible | Instrument / fréquence | Verdict |
|---|---|---|---|---|
| Momentum série-temporelle (trend-following) | Moskowitz, Ooi et Pedersen (2012) ; Hurst, Ooi et Pedersen (2017, un siècle de données) ; **plus faible depuis 2009 sur les matières premières** (réplications) | sur un seul actif, surtout une **réduction du drawdown** par rapport à la détention ; pas 15 %/an d'alpha | ETF or (IBKR, mensuel) ; CFD long coûte ≈ 6-7 %/an de financement : à éviter | rang 4, faible gain |
| **Or : session asiatique positive, séance occidentale négative** | Blose, Gondhalekar et Kort (2018, J. Econ. Finance) : rendements overnight positifs, rendements de jour négatifs sur COMEX, fix de Londres, ETF ; presse 2026 (**non académique**) : +12,9 % en heures asiatiques contre −15 % en heures nord-américaines au S1 2026 | **exploratoire (ne compte pas), Dukascopy 1m 2012-01 → 2025-09** : sur le BID seul, 22-07 UTC = +4,7 pb/jour (t = 7,9), positif chaque année… **mais c'est un artefact d'écart** : le spread s'élargit à la réouverture (2,4-2,5 pb à 21-23 UTC contre ≈ 2,0 pb le jour) et le BID remonte mécaniquement. En exécutable (achat ASK 22:30, 23:05 ou 00:05, vente BID 06:55) : **−0,42 à −0,56 pb/trade, t entre −0,6 et −0,9**, n ≈ 3 500 | CFD XAU/USD | **écarté** (rejet exploratoire) |
| Dip-buy intraday | Exp 54 | — | — | exclu (en cours) |

### 2.3 Forex majeur

| Famille | Preuve | Net plausible | Verdict |
|---|---|---|---|
| Carry | documenté en institutionnel ; au détail, l'écart de financement OANDA (exemple EUR/USD −3,00 % long / +1,60 % court) mange 4-5 points/an du différentiel | ≈ 0 ou négatif | écarté |
| Reversal autour des fixings (forme en « W ») | Krohn, Mueller et Whelan (2024, J. of Finance) : le dollar s'apprécie avant les fixings (Tokyo, Francfort, Londres) et se déprécie après, 9 devises, 21 ans, très significatif ; explication par le risque d'inventaire des teneurs de marché | quelques pb par jour pour un spread EUR/USD ≈ 1 pb et un aller-retour ≥ 1-2 pb : **marginal**, testable gratuitement sur Dukascopy | rang 5 (test bon marché, gain faible) |
| Momentum série-temporelle FX | faible depuis 2010 | ≈ 0 | écarté |

### 2.4 Actions US liquides

Reversal court terme (Lehmann 1990), dérive post-annonce, momentum overnight (Lou et al. 2019),
pairs trading (Gatev, Goetzmann et Rouwenhorst 2006, en déclin depuis 2002) : tous demandent
plusieurs actions et des allers-retours fréquents. À 350 USD, la commission minimale IBKR (non
vérifiée) coûte 0,1-0,3 %/côté. A-Equity (achat de creux) ≈ nul en réaliste. **Écarté à ce budget.**

### 2.5 Crypto spot sur Solana (Jupiter)

| Famille | Preuve | Net plausible | Verdict |
|---|---|---|---|
| **Momentum série-temporelle journalier/hebdomadaire, long ou cash** | Liu et Tsyvinski (2021, RFS) : momentum significatif aux fréquences journalière et hebdomadaire sur BTC, ETH, XRP ; Padysak et Vojtko (2022) : momentum après les plus hauts sur x jours, achat aux plus bas « hasardeux » ; mise en garde interne : la rotation **transversale** à 7 jours (BR1) a échoué | coût négligeable (≈ 0,05 % AR, quelques dizaines de changements/an) ; valeur surtout en **évitant les marchés baissiers** (2022 : panier −70 %) | **retenu (rang 1)** |
| **Saisonnalité horaire BTC 21-23 UTC** | Quantpedia (2015-2022) ; exploratoire hors publication BTC +5,1 pb/jour, t = 2,25 | ≈ +3-4 pb/jour net via `/build` | **retenu (rang 3)**, fiche H-R10 |
| Achat de creux intraday (stratégie actuelle) | Exp 50, T-006 | ≈ +7 %/an en échantillon | H-R08, H-R09 |

## 3. Classement : 3 meilleures paires (gain attendu × probabilité ÷ coût du test)

| Rang | Marché, stratégie | Gain annuel si vrai (net, 500 CAD) | Probabilité a priori | Coût du test | Score relatif |
|---|---|---|---|---|---|
| 1 | Crypto Solana — momentum journalier long/cash sur BTC, ETH, SOL | +10 à +20 %/an (en grande partie par l'évitement des baisses ; corrélé au marché) | ≈ 30 % | très faible (données journalières en cache) | élevé |
| 2 | S&P 500 — tournant du mois, CFD US500 OANDA | +3-4 %/an à 1× ; ≈ +10 %/an à 3× (levier c, T-017) | ≈ 35 % | faible (Dukascopy USA500 1m → journalier) | moyen |
| 3 | Crypto Solana — BTC 21-23 UTC en cbBTC (H-R10) | +4-6 %/an après décote | ≈ 25 % | très faible (en cache) ; forward lent | moyen |

### Prédiction 1 — momentum journalier long/cash (BTC, ETH, SOL)

- Règle fixée a priori (une seule) : chaque jour à 00:00 UTC, pour chaque actif, **détenir 1/3 du
  capital si close(J−1) / close(J−8) − 1 > 0**, sinon USDC. Coût 0,05 % par aller-retour.
- Rejet sur 2020-10-01 → 2025-03-27 (closes Binance en cache) ; la fenêtre 2025-04 → 2026-08 sert
  seulement à rejeter.
- **Passe** si : CAGR net ≥ +15 %, MaxDD ≤ 0,6 × MaxDD du panier égal détenu (attendu : panier
  ≈ −75 % en 2022), Sharpe ≥ Sharpe du panier, et chaque moitié chronologique a un net > 0.
- **Rejet** si le Sharpe est inférieur à celui du panier ou si 2023-2025 (marché haussier) rend
  < 50 % du panier (le filtre coûterait trop en marché haussier).
- Risque de doublon : BR1 (même horizon de 7 jours mais transversal, toujours investi) ; ici
  absolu, avec sortie en cash. À compter dans le compteur de Strategy B.

### Prédiction 2 — tournant du mois S&P 500 (CFD)

- Règle (McConnell et Xu) : long du close du **avant-dernier** jour de bourse du mois au close du
  **3e** jour de bourse du mois suivant ; coût = 0,01 % de spread + financement des nuits au taux
  de référence + 2,5 %/an.
- Données : Dukascopy USA500 1m → closes 16:00 New York, 2012-01 → 2024-12 ; **2025-01 → 2026-09
  verrouillé** pour un test unique ultérieur.
- **Passe** si : net moyen par fenêtre ≥ +0,25 %, t ≥ 2 (≈ 155 fenêtres ; σ ≈ 2 % sur 4 jours ⇒
  erreur type ≈ 0,16 %, donc il faut ≈ +0,32 % : **le test a une puissance moyenne**), écart avec
  les fenêtres de 4 jours hors tournant ≥ +0,20 point, et les deux moitiés (2012-2018, 2019-2024)
  positives.
- Point d'attention : le levier CFD (3×) crée le gain annuel intéressant mais expose aux krachs de
  début de mois (mars 2020) : à traiter avec T-017.

### Prédiction 3 — BTC 21-23 UTC

Voir `H-R10_btc_heure_21_23_utc_jupiter.md` : moyenne brute ≥ +2 pb/jour et net > 0 à 0,03 % AR
sur 2025-04-01 → 2026-08-17 ; rejet si moyenne brute < 0.

## 4. Lecture d'ensemble

- Aucune des familles documentées n'apporte, seule et nette des coûts de détail, un **alpha** de
  15 %/an à 500 CAD. Les deux paires crypto ont l'avantage décisif du coût (Jupiter `/build` ≈ 0) ;
  la paire indices a l'avantage de la persistance de l'effet (un siècle, 31 pays) mais un gain
  faible sans levier.
- Les effets les plus diffusés (pré-FOMC, overnight actions, or overnight) sont soit disparus, soit
  mangés par le financement ou le spread de détail ; le calcul exploratoire sur l'or montre un
  piège concret : **mesurer sur le BID seul fabrique un effet de t = 7,9 qui disparaît en
  exécutable**. Tout test de saisonnalité intraday doit être fait en ASK/BID.

## Compteur de tests exploratoires (ne comptent pas)

- Or : 1 tableau horaire BID, 1 tableau horaire mid, 3 règles exécutables (entrée 22:30 / 23:05 /
  00:05 UTC, sortie 06:55), 2012-01 → 2025-09 (HOLDOUT d'Exp 54 non lu). Script : scratchpad
  `t021/gold_sess.py`, `t021/gold_sess2.py`. Les fichiers `.pkl` de T-022 ont été **lus seulement**.
- BTC/ETH/SOL : fenêtre publiée 21-23 UTC + tableaux horaires, 2022-02 → 2025-03 (voir H-R10).

## Sources (consultées le 2026-10-06)

- J. J. McConnell, W. Xu (2008), *Equity Returns at the Turn of the Month*, FAJ 64(2) : https://ideas.repec.org/a/taf/ufajxx/v64y2008i2p49-64.html
- FPA (2011), *The Turn-of-the-Month Anomaly in the Age of ETFs* : https://www.financialplanningassociation.org/article/journal/APR11-turn-month-anomaly-age-etfs-reexamination-return-enhancement-strategies
- Quantpedia, *Turn of the Month in Equity Indexes* : https://quantpedia.com/strategies/turn-of-the-month-in-equity-indexes
- D. O. Lucca, E. Moench (2015) ; A. Kurov, M. Wolfe, T. Gilbert (2021), *The disappearing pre-FOMC announcement drift*, FRL : https://ideas.repec.org/a/eee/finlet/v40y2021ics1544612320315956.html
- D. Lou, C. Polk, S. Skouras (2019), *A tug of war: overnight versus intraday expected returns* : https://personal.lse.ac.uk/polk/research/TugOfWar.pdf
- T. Moskowitz, Y. H. Ooi, L. Pedersen (2012), *Time series momentum* ; B. Hurst, Y. H. Ooi, L. Pedersen (2017), *A Century of Evidence on Trend-Following Investing* : https://fairmodel.econ.yale.edu/ec439/hurst.pdf ; données AQR : https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Original-Paper-Data
- L. E. Blose, V. Gondhalekar, A. Kort (2018), *Overnight versus Day Returns in Gold and Gold Related Assets*, J. Econ. Finance 42(3) : https://ideas.repec.org/a/spr/jecfin/v42y2018i3d10.1007_s12197-017-9403-0.html
- **Non académique** : *A Strange Dichotomy: Gold Up on the Year in Asian Markets, Down Big in the West* (2026-07) : https://www.moneymetals.com/news/2026/07/12/a-strange-dichotomy-gold-up-on-the-year-in-asian-markets-down-big-in-the-west-005059
- I. Krohn, P. Mueller, P. Whelan (2024), *Foreign Exchange Fixings and Returns around the Clock*, J. of Finance 79(1) : https://wrap.warwick.ac.uk/id/eprint/177333
- Y. Liu, A. Tsyvinski (2021), *Risks and Returns of Cryptocurrency*, RFS : https://www.nber.org/papers/w24877
- M. Padysak, R. Vojtko (2022) (résumé Quantpedia) : https://quantpedia.com/trend-following-and-mean-reversion-in-bitcoin/
- Quantpedia, *Intraday Seasonality in Bitcoin* : https://quantpedia.com/are-there-seasonal-intraday-or-overnight-anomalies-in-bitcoin/
- OANDA Canada, page légale (courtier en dérivés au Québec) : https://www.oanda.com/resources/legal/canada ; financement : https://help.oanda.com/ca/en/faqs/financing-costs-ca.htm ; spread US500 (source secondaire BrokerChooser) : https://brokerchooser.com/pl/broker-reviews/oanda-review/oanda-sp-500-cfd-spread
- Internes : `docs/strategy_b/` (B, BF, BR, BI), `docs/research_plan_status.md` (Exp 32, 47, 54), `docs/agents/research/H-R06_*.md`, `H-R07_polymarket.md`, `docs/agents/venues/VENUES_500CAD_2026-10-06.md`.
