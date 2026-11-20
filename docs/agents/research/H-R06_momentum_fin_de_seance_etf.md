# H-R06 — Momentum intraday de fin de séance et rééquilibrage des ETF à levier (SPY/QQQ/TQQQ) à 500 CAD

- **Auteur** : agent Chercheur, tâche T-010, 2026-10-06
- **Type** : autre marché accessible, base académique solide ; **prédiction : rejet par les coûts à 500 CAD**
- **Classement** : 6/6 (probabilité de succès < 10 % à ce budget ; test très peu coûteux, à faire seulement pour fermer la question)
- **Statut** : non testée formellement ; un calcul **exploratoire, ne compte pas** est rapporté.

## Mécanisme

- **Momentum intraday du marché** : le rendement de la dernière demi-heure est prédit par celui du
  reste de la journée (Gao, Han, Li, Zhou 2018, JFE, SPY 1993-2013 ; plus fort les jours volatils,
  de gros volume et d'annonces macro). Baltussen, Da, Lammers et Martens (2021, JFE) le retrouvent
  sur plus de 60 contrats à terme 1974-2020 et l'expliquent par la **couverture gamma** (teneurs de
  marché d'options courts en gamma, ETF à levier qui doivent acheter après une hausse et vendre
  après une baisse en fin de séance) ; l'effet **se retourne les jours suivants**.
- **ETF à levier** : le rééquilibrage quotidien crée une pression de prix en fin de séance qui se
  retourne à l'ouverture suivante (Shum et Hejazi, et littérature résumée par Ivanov et Lenkey, qui
  contestent l'ampleur une fois les flux de capitaux pris en compte).
- Zarattini, Aziz et Barbon (2024) : une version « zone de bruit » avec stop suiveur sur SPY,
  19,6 %/an net 2007-2024, Sharpe 1,33 — mais avec un levier jusqu'à 4x, des positions longues et
  courtes, et des coûts de 0,0035 USD/action (gros compte).

Mécanisme opposé au nôtre (continuation, pas rebond), mais crédible et documenté.

## Prédiction chiffrée et testable

Point mort à 500 CAD (≈ 351 USD) chez IBKR Canada, seul courtier canadien avec API pour actions
US identifié : tarification par paliers 0,0035 USD/action, **minimum 0,35 USD/ordre** + frais de
bourse/réglementaires ⇒ ≈ 0,10 %/côté sur 350 USD ; tarif fixe 0,005 USD/action, minimum 1,00 USD
(plafonné à 1 % de la valeur) ⇒ ≈ 0,29 %/côté. **Aller-retour ≥ 0,20-0,25 %**, plus l'écart
acheteur-vendeur et le change CAD→USD.

Calcul exploratoire, ne compte pas (CFD S&P 500 Dukascopy 1 min, `data/indices/SP500_1m.csv`,
2012-2019 uniquement, 1 647 jours exploitables, heure de New York ; script dans le scratchpad de
session, non versionné) :

| Signal | Gain moyen du pari directionnel 15:30→16:00 | Long seulement quand signal > 0 | Corrélation |
|---|---|---|---|
| Rendement veille 16:00 → 15:30 | **+0,011 %/jour** | +0,004 % | 0,091 |
| Première demi-heure (Gao et al.) | −0,001 %/jour | −0,008 % | −0,020 |

|rendement de la dernière demi-heure| moyen ≈ 0,13 %. L'edge brut est **≈ 20 fois plus petit** que
l'aller-retour minimal à 500 CAD.

Prédiction formelle : sur toute variante publiée (dernière demi-heure, zone de bruit sans levier,
pression de rééquilibrage TQQQ/SPXL), le rendement brut moyen par trade reste **< 0,10 %**, donc
sous le point mort de 0,20-0,25 % ; **rejet** attendu. Succès seulement si une variante
préenregistrée dépasse 0,30 %/trade brut dans les deux moitiés.

## Pourquoi survivrait (ou non) aux coûts réels à 500 CAD

Il ne survit pas, sauf si un courtier offre à la fois : commission nulle, API, compte en USD sans
change par trade. Wealthsimple (commission nulle) n'a **pas d'API** ; le change de 1,5 % par
conversion s'ajoute sans compte USD. Questrade : API de négociation limitée (à confirmer par
T-004). En outre, la règle américaine « pattern day trader » (25 000 USD) pourrait s'appliquer aux
comptes sur marge d'IB Canada pour les titres US : les sources consultées se contredisent (à
trancher par T-004) ; en compte au comptant, pas de vente à découvert, donc long seulement (pour
le côté vendeur : acheter un ETF inverse).

## Comment tester (rejet rapide seulement)

- Dukascopy SP500/NASDAQ100 1 min (en cache) sur 2012-2019, et TQQQ/SPXL/SOXL 1 min
  (`data/*_1m_20230328_20260826.csv`) **après vérification des bornes HOLDOUT** : rendement brut par
  trade de 2-3 variantes publiées, sans levier, préenregistrées, toutes rapportées.
- Pas de forward tant qu'aucune variante ne dépasse 0,30 % brut : le coût fixe par ordre domine.
- À rouvrir seulement si le capital dépasse ~5 000 CAD (minimum IBKR 0,35 USD ⇒ 0,01 %/côté).

## Anti-doublon

- Exp 32 (Strategy A sur Nasdaq/S&P 500, REJECT) et B_INDEX (momentum/cassure 15 min-1 h sur
  indices, « en cours » depuis 2026-08-24, résultat à vérifier dans `docs/strategy_b/index/`) :
  B_INDEX est le plus proche ; cette fiche n'ajoute que **le calcul de coût à 500 CAD** et le
  mécanisme gamma/fin de séance (fenêtre fixe 15:30-16:00), non testé.
- Strategy A-Equity (Exp 47, config D) : creux intraday sur actions, PF ≈ 1,04 en remplissage
  réaliste à 0,02 % AR (STATE point 2) : même verdict de coût à 500 CAD.

## Sources (consultées le 2026-10-06)

- L. Gao, Y. Han, S. Z. Li, G. Zhou (2018), *Market intraday momentum*, Journal of Financial Economics : https://profiles.wustl.edu/en/publications/market-intraday-momentum/
- G. Baltussen, Z. Da, S. Lammers, M. Martens (2021), *Hedging Demand and Market Intraday Momentum*, Journal of Financial Economics : https://www3.nd.edu/~zda/intramom.pdf ; https://pure.eur.nl/en/publications/hedging-demand-and-market-intraday-momentum/
- C. Zarattini, A. Aziz, A. Barbon (2024), *Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)*, SFI Research Paper 24-97 : https://www.sfi.ch/de/publications/n-24-97-beat-the-market-an-effective-intraday-momentum-strategy-for-s-p500-etf-spy
- CXO Advisory, *Front-running leveraged ETFs at the end of the day* : https://www.cxoadvisory.com/volatility-effects/front-running-leveraged-etfs-at-the-end-of-the-day
- Penn State, *The market impact of leveraged ETFs: a survey of the literature* : https://pure.psu.edu/en/publications/the-market-impact-of-leveraged-etfs-a-survey-of-the-literature/
- A. Barbon et al., *Liquidity Provision to Leveraged ETFs and Equity Options Rebalancing Flows* : https://abarbon.com/papers/liquidity-provision-to-leveraged-etfs-and-equity-options-rebalancing-flows
- IBKR Canada, commissions actions (paliers 0,0035 USD/action, min 0,35 USD ; fixe 0,005 USD, min 1,00 USD) — page officielle https://www.interactivebrokers.ca/en/index.php?f=49637 (accès 403 le 2026-10-06, chiffres tirés de l'extrait du moteur de recherche : **à reconfirmer par T-004**)
- IBKR, *Canada FAQs* (règle PDT pour IB Canada) : https://www.interactivebrokers.eu/de/general/education/faqs/canada.php
