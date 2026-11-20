# H-R07 — Polymarket depuis le Québec (T-020, agent Chercheur, 2026-10-06)

**Verdict : NON. Polymarket est bloqué pour le Québec. La recherche s'arrête ici, comme la
consigne le demande.** Il n'y a pas d'hypothèse Polymarket à préenregistrer. La section 4 propose
une piste de remplacement légale (H-R07b), qui reste à confirmer.

Anti-doublon : `grep -ri polymarket docs/` (y compris `docs/agents/`, `docs/research_plan_status.md`)
ne donne **aucun résultat** au 2026-10-06. Aucun travail antérieur. Les marchés de prédiction
n'ont jamais été testés dans le projet.

## 1. Légalité et accès depuis le Québec

| Point | Constat | Source (consultée le 2026-10-06) |
|---|---|---|
| Statut du Québec | **CA-QC est « close-only » sur le site ET sur l'API.** On peut seulement fermer une position existante ; tout nouvel ordre est rejeté. Même statut pour CA-ON, CA-BC et CA-AB. Le blocage passe par l'IP (`GET https://polymarket.com/api/geoblock`). | Doc officielle Polymarket « Geographic Restrictions » : https://docs.polymarket.com/developers/CLOB/geoblock |
| Date | Conditions d'utilisation mises à jour le **2026-07-06** : Alberta, Colombie-Britannique et Québec passent en « close-only ». C'est Polymarket qui s'est retiré de lui-même (déclaration du ministre albertain D. Nally). | https://www.casinos.com/ca/news/polymarket-leaves-alberta-two-other-canadian-provinces-before-igaming-launch ; https://www.canadiangamingbusiness.com/2026/07/13/polymarket-blocks-provinces/ (403 pour moi, cité via les résultats de recherche) |
| Ontario | Interdiction de 2 ans réglée avec la CVMO (Blockratize Inc. / Adventure One QSS), approuvée le 2025-04-17 : pénalité de 200 000 $, 25 000 $ de frais, remboursement de 22 966,75 USD. Motif : options binaires de moins de 30 jours offertes à des particuliers sans dispense. | https://www.osc.ca/en/news-events/news/osc-reaches-settlement-current-and-former-operators-polymarket-breach-binary-options-ban ; https://www.capitalmarketstribunal.ca/en/proceedings/decisions-in-brief/decision-brief-ontario-securities-commission-v-blockratize-inc-enforcement-proceeding-settlement |
| Cadre ACVM / AMF | Le Règlement 91-102 sur l'interdiction des options binaires (en vigueur depuis le 2017-12-12) interdit d'offrir à un particulier une option binaire d'une durée de moins de 30 jours. Selon la presse spécialisée, **le Québec n'accorde aucune dispense**, alors que d'autres provinces le peuvent. La plupart des marchés Polymarket (sport, crypto 15 min/horaires, politique) tombent sous cette interdiction. | https://www.fcnb.ca/sites/default/files/2020-01/91-102-NOA-2017-09-28-E.pdf ; https://financefeeds.com/despite-ban-binary-options-brokers-continue-target-quebec-investors/ (source secondaire) |
| Contrats permis au Canada | L'OCRI n'autorise que les contrats d'événements sur des **indicateurs économiques, les marchés financiers et le climat**, avec un terme d'au moins 30 jours. Pas d'élections ni de politique, pas de levier ni de marge. | https://www.investmentexecutive.com/news/product/canadian-regulators-are-opening-the-doors-to-prediction-markets/ ; https://newsroom.wealthsimple.com/wealthsimple-to-launch-prediction-markets-trading-app |
| VPN | Interdit par la section 2.1.4 des conditions de Polymarket. En cas d'infraction : résiliation du compte et gel des fonds. En 2026, Polymarket bloquerait les plages IP des VPN et déclencherait un KYC pour les gros volumes. Je n'ai pas pu lire les conditions officielles directement (contenu rendu en JavaScript). | https://www.tradetheoutcome.com/polymarket-section-2-1-4/ (source non officielle) ; https://www.covers.com/industry/polymarket-reportedly-tightens-vpn-rules-amid-rising-regulatory-pressure-june-1-2026 |
| KYC, USDC sur Polygon | Sans objet, puisque l'accès est bloqué. Un portefeuille non custodial ne change rien : l'API CLOB applique le même géoblocage, et contourner le blocage par l'IP enfreint les conditions. | — |

**Conclusion juridique.** Un bot qui ouvre des positions sur Polymarket depuis le Québec est
impossible sans enfreindre les conditions (VPN), et probablement aussi le Règlement 91-102. Il
expose aussi au gel des fonds. **À écarter.**

Points 2 et 3 de la tâche (frais, rewards de market making, edges propres à Polymarket) : **pas
étudiés**, volontairement. Comme le Québec est bloqué, ils ne serviraient à rien. Je ne les ai
pas comptés comme variantes.

## 2. Alternatives légales (1-2)

| Plateforme | Statut au Québec | Intérêt pour un bot | Limites |
|---|---|---|---|
| **IBKR ForecastTrader (ForecastEx)** via Interactive Brokers Canada | Premier courtier de l'OCRI autorisé pour les « forecast contracts » (2025-04). IB Canada est inscrit comme courtier en placement **auprès de l'AMF, son autorité principale**. L'accès des résidents du Québec est donc probable, mais **reste à confirmer par T-004**. | Zéro commission. **Coupon incitatif de 3,83 % par an** sur la position détenue, versé chaque mois. L'**API TWS prend en charge** les forecast contracts. | Catégories restreintes (pas d'élections). Terme ≥ 30 jours. Livres probablement peu profonds. Conversion CAD→USD. Les pages ForecastTrader m'ont renvoyé une erreur 403 : frais et liste de contrats offerts au Canada à vérifier. Sources : https://www.blg.com/en/insights/2025/04/interactive-brokers-canada-is-the-first-ciro-dealer-to-offer-forecast-contracts-by-forecastex-llc ; https://forecasttrader.interactivebrokers.ca ; https://www.interactivebrokers.ca/en/general/communiques/2025/2025-vol26.php |
| **Wealthsimple Predict** (contrats Kalshi) | Autorisé par l'OCRI en mars 2026. Annoncé le 2026-06-18, lancement prévu à l'été 2026. Environ 4 000 contrats Kalshi (économie, marchés financiers, climat). **Disponibilité au Québec non précisée.** | Aucune API annoncée. Pas automatisable a priori. | Frais non publiés. Utile seulement en manuel. https://newsroom.wealthsimple.com/wealthsimple-to-launch-prediction-markets-trading-app |

## 3. Edge documenté pertinent pour l'alternative

**Biais favori/outsider sur Kalshi.** Source : Bürgi, Deng et Whelan, « Makers and Takers: The
Economics of the Kalshi Prediction Market », UCD, janvier 2026,
https://www.karlwhelan.com/Papers/Kalshi.pdf. Données : 313 972 prix sur 46 282 contrats, de 2021
à 2025-04, marchés ouverts ≥ 24 h, volume ≥ 1 000 $, écart ≤ 20 c.

- Contrats à ≤ 10 c : perte moyenne **> 60 %** après frais.
- Contrats > 70 c : rendement positif, **petit mais statistiquement significatif**, autour de
  +2 à +3 % par contrat après frais preneur (lecture de la figure 5). Exemple de l'article : un
  contrat à 95 c qui gagne 98 % du temps rapporte **+3,1 % avant frais**.
- Frais preneur Kalshi : 0,07·P·(1−P) par contrat, soit environ 1,75 % du prix à 50 c. Les
  makers paient des frais depuis 2025-04.
- Les makers gagnent plus que les preneurs. Le biais semble **diminuer avec le temps**.
- Le résultat tient dans plusieurs catégories. Les auteurs n'ont pas isolé la catégorie
  « économie/finance » avec terme ≥ 30 jours, qui est la seule permise au Canada.

**Ampleur plausible à 500 CAD** (raisonnement, pas un test) : on achète des favoris à 80-95 c
quelques jours avant la clôture, à environ +2 % net par cycle. En supposant le capital déployé une
à deux fois par mois, cela donne un **brut d'environ 15-25 %/an, optimiste**. S'y ajoute le coupon
de 3,83 %. Risques :
- Queue : une perte coûte −80 à −95 % de la mise, donc il faut au moins 10-20 positions
  indépendantes, et les contrats d'un même indicateur sont corrélés.
- Capacité : livres minces.
- Non-transférabilité : rien ne garantit que les prix de ForecastEx aient le même biais que ceux
  de Kalshi.

## 4. Piste classée

### H-R07b (seule piste) — Achat de favoris (80-95 c) sur des contrats économiques ou financiers, juste avant la clôture

- **Mécanisme** : biais favori/outsider. Les participants surpondèrent les petites probabilités
  (Bürgi et al. 2026). C'est une forme de fourniture de liquidité aux acheteurs d'outsiders.
- **Prédiction chiffrée testable** : sur les marchés Kalshi des catégories Économie, Finance et
  Climat, on achète au meilleur ask, à T−24 h de la clôture, les contrats dont le prix est dans
  [0,80 ; 0,95]. Prédiction : rendement moyen **≥ +1,5 % par contrat après frais preneur**,
  intervalle de confiance à 95 % avec erreurs groupées par événement **au-dessus de 0**, et au
  moins 1 000 contrats. Elle doit tenir **séparément** sur 2021-2024 et sur 2025-04 → 2026-09.
- **Rejet rapide (historique, jours)** :
  - API publique de Kalshi. Les données de marché ne demandent pas d'authentification pour
    l'historique des marchés et des trades. C'est ce qu'ont utilisé les auteurs.
  - Pire cas de remplissage : ask au lieu du dernier prix, plus 1 c.
  - Rejet si le rendement net est < +1 %, si l'IC contient 0, ou si le signe s'inverse sur la
    période récente.
  - Compteur : 1 variante (bande et horizon fixés ici, pas d'optimisation).
- **Puis forward/paper** : enregistrer les livres ForecastEx par l'API TWS en lecture seule
  pendant 4-8 semaines. On mesure l'écart, la profondeur à 80-95 c et la calibration réalisée.
  Aucun ordre.
- **Pourquoi la piste pourrait survivre aux coûts** : zéro commission sur ForecastEx, et le
  coupon de 3,83 % paie le portage. Le coût réel est surtout l'écart, qu'on mesure en forward.
- **Prérequis (T-004 Plateformes)** :
  - accès des résidents du Québec à ForecastTrader ;
  - liste des contrats offerts aux clients canadiens ;
  - frais exacts éventuels ;
  - conversion CAD→USD.
- **Probabilité a priori : faible à modérée.** Le biais diminue avec le temps, le transfert de
  Kalshi à ForecastEx n'est pas démontré, et les catégories canadiennes sont étroites. Le **coût
  du test est faible** et le verdict historique se rend en quelques jours.

Écartées, faute d'accès au Québec : market making avec rewards Polymarket, arbitrage
« somme ≠ 1 » ou neg-risk sur Polymarket, marchés crypto horaires ou de 15 min (options binaires
de moins de 30 jours, interdites), arbitrage entre Polymarket et Kalshi.

## Compteur de tests (exploratoire, ne compte pas)

Aucun calcul fait. 0 variante.
