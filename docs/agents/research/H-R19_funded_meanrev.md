# H-R19 — Retour à la moyenne intrajournalier pour comptes funded futures (T-064)

- **Agent :** Chercheur. **Date :** 2026-10-10. **Branche :** `research/funded-meanrev` (depuis `agents/orchestration-20261006`, commit 24dca3a).
- **Statut :** recherche et calculs **exploratoires, ils ne comptent pas**. Aucun test décisionnel, aucun compte, aucun achat.
- **Scripts :** `docs/agents/research/H-R19_scripts/` (commit a18cd02) ; sorties dans `outputs/`.
- **Données :** Dukascopy 1 min en lecture seule, `NASDAQ100_1m.csv`, `SP500_1m.csv`, `DOW30_1m.csv`, **séances ≤ 2019-12-31 seulement**. Le chargeur (`build_grids.py`) lit le fichier par blocs et s'arrête au premier bloc qui franchit le 2020-01-01 UTC ; ce bloc est tronqué avant tout calcul. Aucune barre de 2020 ou après n'a servi à un calcul. `RUSSELL2000_1m.csv` n'a pas été ouvert (il commence en 2018-08 et n'a que 191 jours éligibles avant 2020).
- **Sources** consultées le 2026-10-10 (§8). « Non vérifié » = lu seulement sur une source secondaire, ou pas lu.

## Réponse courte

1. **Aucune famille de retour à la moyenne ne tient** sur la fenêtre de découverte (2012-2019) une fois les coûts réels des micros déduits.
   - **Critère de tri :** net > 0 sur au moins 2 indices sur 3, avec t ≥ 2. Aucune des 41 configurations ne le remplit.
   - **Ce qu'on observe :** sur les indices américains, l'intrajournalier est dominé par la **continuation**. Les fades du VWAP, des excès d'ouverture et des barres IBS perdent déjà **avant coûts** (de −0,5 à −5 pb par trade).
   - C'est exactement la faiblesse connue de ces familles, les journées de tendance. C'est aussi ce que disent la littérature (Gao 2018, Baltussen 2021, Zarattini 2024) et nos Exp 64/65.
2. **Seul survivant partiel : le fade de l'échec de cassure du range d'ouverture de 30 min (F2), sur le Nasdaq seulement.**
   - Résultat : +0,89 pb net par trade, t = 1,75, Sharpe net 0,68 à l'échelle MNQ actuelle, stable sur les deux moitiés.
   - Mais il échoue sur le S&P 500 (−0,88) et sur le Dow (−1,44), ses voisins OR 45 et OR 60 min sont plats (0,00), et c'est le meilleur de 41 regards. Il est **probablement fortuit**.
   - Espérance funded exploratoire avec l'edge mesuré : +54 à +111 USD pour 100 USD dépensés selon la firme et la taille. Au demi-edge : ≈ 0. À edge nul : négative. **Même profil de fragilité que la zone de bruit (H-R17).**
3. **Le seul effet mécanistiquement cohérent est trop petit.** Les jours de gamma des teneurs de marché élevé (GEX de la veille dans le tiers supérieur), le fade du VWAP devient positif **avant coûts sur les 3 indices** : c'est la prédiction de Baltussen et al. (2021).
   - Gain net : seulement +0,1 à +0,24 pb par trade (Sharpe 0,1-0,3), loin du point mort funded (Sharpe ≈ 0,45-0,5, H-R17).
4. **Le texte collé est vrai sur les spécifications E-nano, mais sa conclusion est fausse.**
   - Les E-nano existent (lancement le 2026-08-24, 1/10 de micro, tick 2× plus grand en points et 5× plus petit en USD).
   - Mais la commission reste celle d'un micro (0,61 USD par côté chez Topstep Brokerage). **Le coût aller-retour du NNQ est ≈ 0,024 % du notionnel, contre ≈ 0,0038 % pour le MNQ, soit 6,4 fois plus cher.** Pour le Russell (N2K) et le S&P (NES), c'est 4,6 à 6,4 fois plus.
   - Aucune firme vérifiée ne les accepte : la liste officielle de Topstep (2026-07-13) ne les contient pas.
   - Un compte personnel E-nano à 500 CAD n'est pas réaliste : marge IBKR de 2 000 USD (non vérifié pour IB Canada) et coût de 0,4 % du compte par aller-retour.
5. **Recommandation : ne rien acheter.** Un seul préenregistrement est proposé (§6, « R1 », fade d'ORB 30 min sur MNQ), comme **test de fermeture peu coûteux**. Probabilité a priori de PASS : ≈ 10 %. Si l'orchestrateur préfère ne pas dépenser ce regard, **fermer la piste « retour à la moyenne funded » dès maintenant est défendable**.

## 0. Anti-doublon (lu avant de calculer)

| Travail existant | Ce qu'il a établi | Lien avec H-R19 |
|---|---|---|
| Exp 64 / 65 / 70 / 71 (zone de bruit) | Momentum intrajournalier : MNQ Sharpe net 0,97 (P1), 0,81 (H) ; MES 0,23 / −0,26 ; MYM −0,50 ; M2K −1,57 (**brut −0,93 : M2K retourne à la moyenne**) ; filtre GEX REJET | H-R19 cherche le profil **inverse**. Le Russell « inverse » est connu sur 2019-2026 : c'est une **fuite**, voir §6 |
| Exp 64, variante Gao (dernière demi-heure) | Sharpe net −1,37 (SP500), −0,22 (NDX) | **Point 3 du texte collé : déjà testé, non refait** |
| B_INDEX BI1-BI3 (`docs/strategy_b/index/`) | ORB continuation sur le Nasdaq, VALIDATION **2021-09-23 → 2024-03-05** : dérive −0,009 % à −0,031 %, 51-52 % de gagnants | Le fade d'ORB (F2) est l'inverse partiel. **Cette fenêtre est exclue de la fenêtre de décision proposée** (§6) |
| Exp 32 (stratégie A sur indices, 10 min) | Achat de creux type crypto sur Nasdaq/SP500 : PF 0,58, REJECT (TRAIN ≈ 2011-2020) | Famille « creux » déjà fermée ; H-R19 ne la rouvre pas |
| Strategy C1/C2 (QQQ/SPY, flux d'ordres) | Renversement de signe opposé entre QQQ et SPY ; rendement exécutable négatif partout | Même leçon : un retour à la moyenne vu sur un indice ne se transfère pas |
| H-R17 §5 K7 | « Retour à la moyenne à fort taux de réussite : aucune preuve d'edge » | H-R19 le mesure : confirmé |
| H-R_MARKETS (dérive overnight, or overnight) | Écartés (coûts CFD, artefact d'écart) | Dérive overnight des futures : morte depuis 2021 selon ses auteurs (§3, F7) |
| `research_plan_status.md` | Aucun fade de VWAP, de gap, d'IBS ni d'ORB sur les indices | Pas de doublon direct |

**Risque de doublon : moyen.**
- F1-F5 sont neuves dans le projet, mais F5 est l'inverse exact de la zone de bruit à 10:00, F2 celui de BI3, et F6 utilise le GEX de l'Exp 70.
- Toutes les fuites sont déclarées au §6.

## 1. Vérification du texte collé

### 1.1 Contrats CME E-nano

| Affirmation | Verdict | Preuve |
|---|---|---|
| Lancés le 2026-08-24 | **Vrai** | Communiqué CME du 2026-08-03 (repris par Finviz et The Post-Searchlight), « pending regulatory review » ; CQG : « On August 24, 2026, the CME began trading E-nano » [N1, N2, N3] |
| Codes NNQ, NES, N2K, NDOW | **Vrai** | Topstep Brokerage, NinjaTrader, MetroTrade, Ironbeam [N4-N7]. NES, NNQ et N2K sont cotés au CME, NDOW au CBOT [N3] |
| 1/10 d'un micro | **Vrai** | NNQ = 0,20 USD × indice (MNQ : 2 USD) ; NES = 0,50 (MES : 5) ; N2K = 0,50 (M2K : 5) ; NDOW = 0,05 (MYM : 0,50) [N3, N4] |
| Tick 2× plus grand en points, valeur ÷ 5 | **Vrai** | NNQ 0,5 pt = 0,10 USD (MNQ 0,25 pt = 0,50) ; NES 0,5 pt = 0,25 USD (MES 1,25) ; N2K 0,2 pt = 0,10 USD (M2K 0,50) ; NDOW 2 pt = 0,10 USD (MYM 0,50) [N4-N6]. CME l'explique par l'arrondi du multiplicateur fractionnaire (extrait de recherche de la FAQ CME) |
| Horaires | **Vrai** | ≈ 23 h/jour, du dimanche 18:00 au vendredi 17:00 ET, pause de 17:00 à 18:00 ET [N5] |
| Commissions | **Égales à celles des micros, donc pas 10 fois plus basses** | Topstep Brokerage : bourse 0,35 + commission 0,25 + NFA 0,01 = **0,61 USD par côté, « the same as those charged on Micro E-mini contracts »** [N4]. MetroTrade : 0,29 USD par côté, comme pour les micros [N6]. Le volume E-nano ne compte pas dans les remises de volume CME [N7] |
| Marges | Non publiées par la CME à la lecture | Estimation de courtier : ≈ 5-11 USD intrajournalier [N6] ; ≈ 1/10 du micro [N7]. **Non vérifié** |
| Firmes qui les acceptent | **Non vérifié, probablement aucune** | **Topstep** : la page officielle des produits permis (mise à jour le 2026-07-13) liste ES, MES, NQ, MNQ, RTY, M2K, YM et MYM, **pas les E-nano** [F1]. Le grille de frais TopstepX ne les liste pas non plus [F2]. Topstep Brokerage (compte personnel) les propose [N4]. **Lucid** : 9 contrats d'indices approuvés, sans E-nano (secondaire, 2026-08-12) [F3]. **Tradeify, MFFU, FundedNext, Phidias, FTMO Futures** : aucune mention trouvée |

Le site cmegroup.com bloque les accès automatisés (« IP blocked … scraping prohibited »), comme lors de l'Exp 71. Je ne l'ai pas contourné. Les spécifications viennent de quatre courtiers concordants et du communiqué. **Une relecture manuelle sur cmegroup.com reste conseillée.**

**Coût aller-retour en % du notionnel.**
- Niveaux du 2026-08-24, d'après les notionnels CQG : NES 3 826 USD, NNQ 5 805, N2K 1 498, NDOW 2 671.
- Coût = commission tout compris 1,22 USD + 1 tick de glissement par côté.

| Contrat | Notionnel | AR tout compris | **AR en % du notionnel** | Commission seule |
|---|---|---|---|---|
| MNQ | 58 046 | 1,22 + 1,00 = 2,22 | **0,0038 %** | 0,0021 % |
| **NNQ** | 5 805 | 1,22 + 0,20 = 1,42 | **0,0245 %** (6,4 × MNQ) | 0,021 % (10 ×) |
| MES | 38 264 | 1,22 + 2,50 = 3,72 | 0,0097 % | 0,0032 % |
| NES | 3 826 | 1,22 + 0,50 = 1,72 | 0,045 % (4,6 ×) | 0,032 % |
| M2K | 14 975 | 2,22 | 0,0148 % | 0,0081 % |
| N2K | 1 498 | 1,42 | 0,095 % (6,4 ×) | 0,081 % |
| MYM | 26 709 | 2,22 | 0,0083 % | 0,0046 % |
| NDOW | 2 671 | 1,42 | 0,053 % (6,4 ×) | 0,046 % |

**Lecture.**
- La granularité ne sert à rien. Avec une commission par contrat fixe, le coût relatif d'un E-nano est 5 à 10 fois celui du micro.
- Le seul survivant partiel de H-R19 (F2 sur NDX, +1,27 pb brut par trade) devient **négatif en NNQ** (1,27 − 2,45 = −1,2 pb).
- Pour une stratégie funded, l'E-nano ne servirait qu'à régler une taille fractionnaire (par exemple 1,5 MNQ = 1 MNQ + 5 NNQ). Encore faudrait-il que la firme l'accepte, ce qui n'est pas le cas chez Topstep à ce jour.

### 1.2 Firmes sans drawdown suiveur, sans cohérence, ou acceptant les bots

| Firme / produit (texte collé) | Canada / Québec | Bot entièrement automatisé | Drawdown / cohérence | Verdict |
|---|---|---|---|---|
| **Phidias « Express to Live » (E2L)** | **Oui** : le Canada n'est pas dans l'annexe 1 des pays exclus des CGU officielles ; droit de Gibraltar [F4] | **Non.** CGU : « the use of robots, fully automated trading algorithms or any form of automated trading is not authorized, except for semi-automated software, provided the User actively monitors and manually adjusts all operations » [F4] | E2L : drawdown **statique** (ne suit pas), cohérence de 30 % sur tous les comptes **sauf** E2L (résumé des CGU [F4]) | **Vrai** pour l'absence de trailing et de cohérence ; **exclu pour un bot** |
| **MFFU Flex** | Oui (T-050, liste officielle) | **Semi-automatique seulement** selon des sources secondaires de 2026 [F5]. T-050 avait lu sur la page officielle « automated trading strategies tailored to their own specific settings ». **Contradiction, non vérifié** | Trailing de fin de journée de 2 000 USD, verrouillé à +100 ; cohérence de 50 % à l'évaluation. **Flex n'est plus vendu (« legacy ») depuis juillet 2026** (secondaire) [F5] | **Faux** comme option actuelle |
| **FundedNext Futures « Rapid »** | **Oui** : page officielle mise à jour le 2026-09-30, Canada absent des pays restreints ; « Canada (except Ontario) » éligible au compte Live ; Québec non mentionné [F6] | **Oui** : « FundedNext Futures allows the use of automated trading systems, including Expert Advisors (EAs) and trading bots » (officiel, 2026-04-09) ; VPS non mentionné [F7] | 50K : objectif 3 000, MLL de 2 000 en fin de journée, **pas de cohérence pendant le challenge**, **40 % une fois financé** ; partage 80 % ; reset 184 USD (secondaire) [F8] | **Vrai** (bots permis, Canada admis) ; « sans cohérence » vrai **seulement à l'évaluation** |
| **Lucid Flex** | Oui (T-050, officiel) | Oui (T-050, officiel) | Trailing de fin de journée verrouillé à +100 ; cohérence de 50 % à l'évaluation (H-R17). Lucid a modifié ses programmes en septembre 2026 (Live facultatif depuis le 2026-09-14, secondaire) [F9] | **Vrai** ; règles à relire avant tout achat |
| **FTMO Futures** (lancé en août-septembre 2026) | **Oui** : « available to clients globally », exclusions limitées aux pays sanctionnés et à certains États américains (officiel) [F10] | **Oui avec conditions** : algos et EA permis, mais pas l'automatisation manipulatrice, le HFT ou l'arbitrage de latence ; stratégie unique exigée, plafond de 400 000 USD par stratégie ; VPS permis (FAQ via extrait de recherche et secondaires) [F11] | Trailing de fin de journée verrouillé au solde initial ; cohérence de 40 % (Growth) ou 50 % (Pro) (secondaire) [F12] | **Plausible**, à relire sur la page officielle avant achat |
| Rappel T-050 : Topstep | Oui | Oui via l'API ProjectX, **depuis le PC personnel seulement (VPS interdit)** | MLL trailing de fin de journée, cohérence de 50 % | — |

**Conclusion.**
- **Aucune firme ne combine** « sans trailing » et « bot permis » : Phidias E2L est la seule sans trailing, et elle interdit les bots.
- Celles qui acceptent un bot sur VPS (FundedNext, FTMO Futures, selon les textes lus) ont toutes un trailing de fin de journée et une règle de cohérence à un moment du parcours.
- Changer de firme ne crée pas d'edge : le simulateur H-R17 montre qu'à edge nul, l'espérance est négative sous toutes ces formes de règles.

### 1.3 Momentum de la dernière demi-heure (Gao, Han, Li, Zhou 2018)

**Déjà testé** comme variante rapportée de l'Exp 64 : Sharpe net −1,37 (SP500) et −0,22 (NDX) sur P1. Non refait.

### 1.4 Compte personnel en E-nano (IBKR Canada)

- **Disponibilité chez IBKR : non vérifiée** (aucune page IBKR trouvée ; pages IBKR.ca en 403).
- **Marge :** un compte sur marge IBKR exige **2 000 USD** au minimum (T-004 ; non vérifié pour IB Canada), contre ≈ 360 USD pour 500 CAD. **Bloquant.** D'autres courtiers (MetroTrade, NinjaTrader, Ironbeam) annoncent une marge intrajournalière de ≈ 5-11 USD par E-nano, mais leur admissibilité pour un résident du Québec n'a pas été vérifiée.
- **Économie, même si c'était faisable :**
  - 1 NNQ vaut ≈ 5 800 USD, soit 16 fois le compte. Avec σ ≈ 1,2-1,5 %/jour, un jour typique fait ± 70-90 USD, ≈ 20-25 % du compte.
  - Un aller-retour coûte 1,42 USD, soit **0,4 % du compte**.
  - Viser 15 %/an, c'est ≈ 54 USD/an, l'équivalent de 38 allers-retours de frais.
  - Aucune règle testée ici n'a d'edge net positif au coût NNQ.
- **Verdict : infaisable à 500 CAD**, et sans intérêt tant qu'aucun edge n'existe au coût micro.

## 2. Méthode exploratoire (ne compte pas)

- **Fenêtre de découverte :**
  - NDX : 2012-02 → 2019-12, 1 699 jours ;
  - SP500 : 2013-06 → 2019-12, 1 404 jours (données lacunaires en 2012-2013, Exp 64 §2) ;
  - DOW30 : 2014-06 → 2019-12, 1 373 jours.
- **Éligibilité :** règle de l'Exp 64 §3.6, moteur importé sans modification, plus 14 jours d'historique.
- **Exécution :** signal sur la clôture d'une barre de 1 minute, entrée à l'ouverture de la barre suivante. Cibles et stops testés sur les clôtures 1 min, sortie à l'ouverture de la barre suivante, **jamais au niveau du stop**. Sortie forcée à l'ouverture de la barre 15:59. 1 contrat, une position à la fois.
- **Coûts en % du notionnel actuel :** MNQ 0,0038 %, MES 0,0097 %, MYM 0,0097 % (légèrement prudent, voir §1.1). Stress : +1 tick par côté.
- **Échelle en USD :** 1 micro au notionnel actuel (MNQ 60 000, MES 38 500, MYM 23 000). Le Sharpe porte sur le PnL quotidien de tous les jours éligibles (0 sans trade), × √252.
- **Écart avec les Exp 64/71 :** ces expériences utilisaient l'USD historique, ce qui pénalise les premières années (coût fixe par contrat). Ici, on mesure ce que la règle coûterait **aujourd'hui**.
- **Catégorie :** en échantillon, exploratoire. Volume CFD pour le VWAP (proxy), comme l'Exp 64.

## 3. Familles : littérature, chiffres exploratoires, adéquation funded

Chiffres : Sharpe net (NDX→MNQ / SP500→MES / DOW→MYM), brut et net en pb par trade sur NDX, trades/jour, taux de gain. Fichier complet : `outputs/families_discovery.csv`.

| # | Famille et règle testée | Preuves (académique / non académique) | Sharpe net MNQ / MES / MYM | NDX : brut / net (pb), t | Trades/j ; gain | Faiblesse | Adéquation funded |
|---|---|---|---|---|---|---|---|
| F1 | **Écart au VWAP** : entrée si \|P − VWAP\| > k·σ (σ = bruit sur 14 jours à la même minute, Zarattini et al.), sortie au retour au VWAP, stop à 2k·σ, entrées de 10:00 à 15:00 toutes les 5 min. k = 1,0 / 1,5 | Aucune preuve académique de retour au VWAP sur indices. **À l'inverse** : momentum VWAP sur QQQ 2018-2023 (Zarattini-Aziz 2023, SSRN, non évalué par les pairs), zone de bruit (2024), momentum intrajournalier sur 60 futures (Baltussen et al. 2021). Bandes VWAP : praticiens (**non académique**) | k = 1 : **−1,40 / −1,46 / −1,59** ; k = 1,5 : −0,50 / −0,62 / −0,73 | −1,52 / −1,90, t = −3,8 | 2,2 ; 45 % | Les jours de tendance : on vend la force, et elle continue | Profil voulu (petits gains, 2 trades/j), mais **edge brut négatif** |
| F2 | **Fade de l'échec d'ORB** : range 09:30-09:59 (ou 09:30-09:44) ; après une clôture 1 min hors du range puis une clôture de retour dedans (avant 13:30), entrée contre la cassure ; cible = milieu du range, stop = extrême depuis la cassure ; une entrée par côté et par jour | ORB **continuation** rentable sur le pétrole (Holmberg et al. 2013) et sur les « stocks in play » (Zarattini-Aziz 2023). Le fade de l'échec vient de Crabel (1990) et des praticiens (**non académique**). Chez nous, BI3 : continuation de l'ORB NDX négative en 2021-2024 | OR30 : **+0,68** / −0,88 / −1,44 ; OR15 : +0,56 / −0,80 / −1,15 ; **NDX OR45 : −0,01 ; OR60 : 0,00** | OR30 : +1,27 / +0,89, t = 1,75 | 1,1 ; 42 % (gain moyen 133 USD, perte moyenne 89 USD) | Un échec suivi d'une reprise de la tendance (stop) ; fortement dépendant de l'indice | Meilleure de H-R19 : σ = 135 USD/jour par MNQ (2,5 fois moins que la zone de bruit), 5 meilleurs jours = 33 % du net, pire jour −740 USD. Mais edge fragile (§4) |
| F3 | **Comblement de gap** : si 0,3 σ_jour ≤ \|gap\| ≤ 1,5 σ_jour et que le gap n'est pas comblé à 09:31, entrée vers la clôture de la veille ; cible = clôture de la veille ; stop = gap doublé ; sortie à 12:00 ou à 15:59 | Yu, Rentzler, Wolf (2005, JOIM) : sur les futures Nasdaq-100, « last night's return is predominately associated with reversals ». Grant, Wolf, Yu (2005, JBF) : renversements significatifs après de gros mouvements d'ouverture (1987-2002), **fortement réduits par un proxy du bid-ask**. Taux de comblement de ≈ 60 % (praticiens, **non académique**) | 12:00 : +0,14 / −0,52 / −0,26 ; 15:59 : 0,00 / −0,58 / −0,37 | +0,95 / +0,57, t = 0,4 | 0,6 ; **54-59 %** | Taux de réussite élevé, mais la perte moyenne dépasse le gain moyen : les gros gaps de tendance ne se comblent pas | Profil « gagne souvent » trompeur ; net ≈ 0 |
| F4 | **IBS sur 15 min** : IBS < 0,15 → achat, > 0,85 → vente, tenue de 15 ou 30 min | IBS **journalier** sur ETF (Pagonidis 2014, NAAIM, **non académique**) ; RSI(2) journalier (Connors, **non académique**). Rien d'académique en intrajournalier | hold 15 : −0,91 / −2,77 / −3,16 ; hold 30 : −1,25 / −1,74 / −2,21 | +0,05 / −0,33, t = −2,3 | **5-6** ; 46-49 % | Brut ≈ 0 : **les coûts tuent**, même au MNQ | Profil voulu, edge nul ; le coût à 6 trades/jour suffit à perdre |
| F5 | **Excès de début de séance** : si \|r(09:30→10:00)\| > 1,5 σ, contre-position de 10:00 à 12:00 ou à 15:59 | Grant-Wolf-Yu (2005) : renversement 1987-2002. Mais Gao et al. (2018) : la 1re demi-heure prédit **positivement** la dernière ; la zone de bruit est l'inverse exact | 12:00 : −0,68 / −1,15 / −1,14 ; 15:59 : −0,38 / −0,55 / −0,44 | **−4,4** / −4,8, t = −1,8 | 0,23 ; 47 % | Continuation de l'excès : c'est le momentum qui existe | Rejet net |
| F6 | **F1/F2/F4 seulement les jours de gamma élevé** (GEX J−1 dans le tiers supérieur de ses 252 valeurs précédentes, instantané SqueezeMetrics gelé H-R15) | Baltussen, Da, Lammers, Martens (2021, JFE) : couverture gamma → momentum si gamma négatif, renversement si positif ; Ni, Pearson, Poteshman, White (2021, RFS) au niveau des actions | VWAP k = 1 : **+0,12 / +0,10 / +0,30** (brut **positif sur les 3**) ; ORB OR30 : +1,38 / −0,77 / −0,86 ; IBS : −1,76 / −4,49 / −4,81 | VWAP : +0,52 / +0,14 | 1,5 sur ⅓ des jours | Signe conforme au mécanisme, **amplitude trop faible** (+0,1 à +0,24 pb net) | Sous le point mort funded (Sharpe ≈ 0,45-0,5). L'Exp 70 a montré que le GEX ne triait pas la zone de bruit sur H |
| F7 | **Dérive overnight après une vente de clôture** (02:00-03:00 ET, futures) | Boyarchenko, Larsen, Whelan (2023, RFS) : ≈ 3,7 %/an sur 1998-2020, expliqués par les déséquilibres de clôture. **Les mêmes auteurs (NY Fed, 2026-07-01) : « averaged close to zero » sur 2021-2025** (déséquilibres de clôture divisés par deux) | non calculé | — | 1/nuit | Disparue selon ses auteurs | Rejet sans calcul |
| — | Achat de creux type stratégie A, microstructure QQQ/SPY | Exp 32 (PF 0,58), C1/C2 | déjà rejetés | — | — | — | Non rouvert |

**Classement (meilleur d'abord) :**
1. **F2 (OR30, NDX seulement)** : seul net positif, mais 1 indice sur 3 et surface non lisse.
2. **F6-VWAP** : mécanisme confirmé en signe sur 3/3, mais l'edge est 4 à 10 fois trop petit.
3. **F3** : net ≈ 0, profil trompeur.
4. **F1**, **F4** et **F5** : edge brut négatif ou nul, rejetés.
5. **F7** : disparue selon ses auteurs.

**Pourquoi le retour à la moyenne intrajournalier échoue sur les indices américains.**
- Les flux de couverture (gamma négatif des teneurs de marché, ETF à levier) et l'exécution progressive des gros ordres poussent dans le sens du mouvement de la journée. La continuation est documentée sur 60 futures (Baltussen et al. 2021) et domine les horizons de 30 min à la clôture.
- Les fades gagnent souvent un peu, puis perdent beaucoup les jours de tendance. Ce sont exactement les jours qui font perdre un compte funded (MLL trailing).
- Le seul conditionnement qui inverse le signe (gamma positif) laisse un gain trop petit devant les coûts, même au MNQ.

## 4. Espérance funded du seul survivant (F2 OR30, MNQ) — exploratoire

`funded_orbfade.py` : fonction `run` du simulateur H-R17, **sans modification**. Bibliothèque quotidienne NDX 2012-2019 à l'échelle actuelle :
- moyenne +5,85 USD/jour par MNQ, σ = 135 ;
- pire latent intrajournalier approché par le cumul réalisé + la MAE de chaque trade.

Paramètres : bootstrap par blocs de 20 jours, 2 000 parcours par case, horizon 1 an. 84 cases au total, toutes dans `outputs/funded_orbfade.csv`.

| Scénario | Lucid Flex 50K, 3 MNQ, 5 tentatives | Topstep 50K, 5 MNQ, 5 tentatives | Lucid 50K, 1 MNQ, 1 tentative |
|---|---|---|---|
| Edge mesuré (Sharpe 0,68) | **+399 ± 32 USD (+54 pour 100 USD)**, P(≥ 1 payout) 0,66, P(perte) 0,55 | **+731 ± 58 (+111 pour 100)**, P(payout) 0,43, P(perte) 0,57 | −52 (−34) : trop lent (≈ 510 jours pour 3 000 USD) |
| Demi-edge | +53 ± 27 (+7) | +332 ± 41 (+53) | −98 (−66) |
| Edge brut nul | −356 (−48) | −108 (−20) | −142 (−94) |

**Lecture.**
- Le profil « petits gains, faible σ » oblige à **monter en taille** (3-5 micros) pour atteindre l'objectif dans un délai payable : le σ quotidien remonte alors à 400-670 USD.
- Le point mort se situe vers la moitié de l'edge mesuré, comme pour la zone de bruit.
- Le meilleur jour pèse 8,6 % du net total de la période : la règle de cohérence gêne peu ce profil, contrairement à la zone de bruit.
- Mais l'edge lui-même est le meilleur de 41 regards, sur 1 indice sur 3. Sous l'hypothèse nulle, le maximum attendu de 41 t-statistiques est ≈ 2,2 : **t = 1,75 n'est pas distinguable du hasard.**
- Les cases présentées sont **sélectionnées** parmi 84 : elles sont optimistes.

## 5. Compteur de regards et limites

| Bloc | Regards sur la découverte (≤ 2019) |
|---|---|
| `families.py` : 10 variantes (F1-F5 × 2) × 3 indices | 30 |
| `gamma_condition.py` : 3 variantes × 3 indices | 9 |
| `neighbors.py` : F2 OR45 et OR60 sur NDX | 2 |
| **Total** | **41** (+ 84 cases de simulation funded) |
| Fenêtre de décision (≥ 2020) | **0** |

**Limites :**
- Prix CFD Dukascopy (BID) à la place des futures ; VWAP sur le volume CFD.
- Le pire latent quotidien est approché, pas tiré de la trajectoire minute.
- Coût fixe de 1 tick par côté : aucun modèle de file d'attente. Des ordres limite pourraient réduire le coût de F2, mais avec une sélection adverse inconnue.
- MYM est valorisé à 23 000 USD au lieu de ≈ 26 700 (léger excès de prudence).
- Règles des firmes relues en partie sur des sources secondaires, et elles changent souvent (Lucid en septembre 2026, MFFU Flex retiré).

## 6. Préenregistrement proposé (non exécuté) — « R1 » : fade de l'échec de cassure du range d'ouverture de 30 min sur MNQ

**Pourquoi ce test, et pourquoi il est faible.**
- C'est le seul candidat de H-R19 avec un net positif et un profil adapté au funded : σ trois fois plus petit, 5 meilleurs jours = 33 % du net, cohérence peu gênante.
- Il a échoué sur MES et MYM dans la découverte, et ses voisins sont plats. **Probabilité a priori de PASS : ≈ 10 %.**
- Son intérêt principal est de **fermer proprement** la famille avec un regard bon marché : le moteur existe, le calcul prend quelques minutes.

**Fuites déclarées sur la fenêtre de décision.**
- (a) Les Exp 64 (P1 jusqu'au 2024-03-04) et 65 (H) ont vu NDX 2020-2026 pour la règle de **momentum** ; on sait que le momentum y a fonctionné, ce qui joue **contre** un fade.
- (b) BI3 a vu l'**ORB continuation** NDX du 2021-09-23 au 2024-03-05 (dérive négative, donc favorable au fade). **Cette période est exclue de la décision.**
- (c) Le Russell brut « inverse » de l'Exp 71 est connu : **M2K n'est pas utilisé pour décider.**

**Spécification.**
- **Hypothèse.** La règle F2 OR30 gelée (`H-R19_scripts/families.py`, fonction `f2_orb_fade(g, 30)`, commit a18cd02, **sans aucun changement**) donne un Sharpe net ≥ 0,6 sur MNQ dans la fenêtre de décision.
- **Instrument.** NASDAQ100 (Dukascopy) → **MNQ**, 1 contrat par signal pour les statistiques. **Pas le NNQ** (coût 6,4 fois plus élevé, §1.1).
- **Fenêtre de décision (jamais vue pour cette règle).** **D1 = 2020-01-02 → 2021-09-22 et D2 = 2024-03-05 → 2026-08-18** (fin du fichier), ≈ 1 050 séances.
  - La période BI3 (2021-09-23 → 2024-03-04) est calculée et rapportée **sans effet**.
  - Les 14 jours d'historique de σ peuvent venir de décembre 2019.
- **Règle exacte** (celle du code gelé) :
  - éligibilité de l'Exp 64 §3.6 plus σ et VWAP définis (masque `ok`) ;
  - ORH et ORL = plus haut et plus bas des barres 09:30-09:59 ;
  - balayage des clôtures 1 min de 10:00 à 13:29 : une clôture > ORH arme la cassure haussière, et l'extrême haut est suivi ensuite ;
  - si une clôture repasse < ORH, vente à l'ouverture de la barre suivante ;
  - cible : première clôture ≤ (ORH + ORL)/2. Stop : première clôture ≥ l'extrême au moment de l'entrée. Sortie à l'ouverture de la barre suivante ; sinon à l'ouverture de 15:59 ;
  - règle symétrique à la baisse ; au plus une entrée par côté et par jour ; pas de chevauchement de positions.
- **Coûts.** 2,22 USD aller-retour au notionnel actuel (60 000 USD par MNQ), soit 0,0037 % du rendement. Stress : +1 tick par côté (3,22 USD).
- **Mesures :**
  - Sharpe net quotidien (D1 ∪ D2, puis D1 et D2 séparément) ;
  - t par trade, taux de gain, gain et perte moyens ;
  - part du net venant des 5 meilleurs jours, MaxDD, pire jour, résultats par année ;
  - espérance funded avec `H-R19_scripts/funded_orbfade.library` appliquée à D1 ∪ D2 et `H-R17_scripts/funded_sim.run` inchangé, 3 000 parcours, graine 11 :
    - case **principale** : Lucid Flex 50K, `fixed:3`, 5 tentatives ;
    - case **secondaire** : Topstep 50K, `fixed:5`, 5 tentatives ;
    - scénarios « mesuré » et « demi-edge ».
- **PASS (toutes les conditions) :**
  - Sharpe net D1 ∪ D2 ≥ 0,6 ;
  - Sharpe net > 0 sur D1 **et** sur D2 ;
  - Sharpe stress ≥ 0,4 ;
  - 5 meilleurs jours ≤ 50 % du net ;
  - case principale, scénario mesuré : espérance > 2 erreurs types **et** > 0 pour 100 USD ;
  - case principale, demi-edge : espérance ≥ 0 (marge de sécurité) ;
  - au moins 600 trades.
- **REJET :** Sharpe net D1 ∪ D2 ≤ 0,2, **ou** espérance de la case principale (mesurée) ≤ 0. → **Fermer la piste « retour à la moyenne funded ».**
- **INCERTAIN :** tout le reste → aucun achat ; tout au plus un forward papier.
- **Puissance.** Sur ≈ 4,2 ans, l'erreur type du Sharpe est ≈ 0,49. Si le vrai Sharpe vaut 0,68, P(Sharpe observé ≥ 0,6) ≈ 0,55. Le test est donc peu puissant, mais un REJET reste très informatif.
- **Variantes : 1 décisionnelle.** Rapportées **sans effet** :
  - la période BI3 ;
  - MES et MYM sur 2020-2026 (dans la découverte, la règle y échouait) ;
  - M2K sur toute sa série (fuite c).
- **Compteur de la famille :** 41 regards exploratoires (H-R19) + R1.
- **Étape 0 (bloquante) :**
  - `grep` pour vérifier qu'aucun script n'a calculé F2 sur NDX après 2019 ;
  - tests unitaires du chargeur de fenêtre (fixtures dans `tmp_path`, jamais sur `data/`) ;
  - script et tests commités avant tout calcul.
- **Si PASS :** 3 mois de forward papier, sur l'infrastructure MNQ de l'Exp 67. Ensuite seulement, proposer à l'auteur **une** tentative Lucid Flex 50K ou FundedNext Rapid 50K (bots permis, Canada admis), achetée en promotion, à 3 micros.
- **Si REJET :** fermer la piste ; aucun achat.

**Pas de second préenregistrement.**
- F6-VWAP est le meilleur candidat « mécanisme », mais son net (+0,1 à +0,24 pb) est structurellement sous le point mort funded, même au MNQ.
- Pour qu'il compte, il faudrait un coût d'exécution ≈ 0 (ordres limite remplis sans sélection adverse), ce qu'on ne sait pas mesurer avec des barres CFD de 1 minute.

## 7. Verdict

- **Rien ne tient de façon convaincante.**
  - Le retour à la moyenne intrajournalier sur les futures d'indices américains est battu par la continuation, qu'elle soit documentée (Gao, Baltussen, Zarattini) ou mesurée ici : F1, F4 et F5 ont un edge brut négatif ou nul.
  - Le meilleur candidat (F2 OR30) est très probablement un artefact de sélection : NDX seulement, voisins plats, t = 1,75 parmi 41 regards.
- **Le texte collé :**
  - E-nano : spécifications vraies, mais coût relatif 5 à 10 fois celui des micros, aucune firme vérifiée, compte personnel infaisable ;
  - firmes : Phidias E2L est la seule sans trailing, et elle interdit les bots ; FundedNext Futures et FTMO Futures acceptent les bots, mais avec trailing et cohérence ;
  - Gao : déjà testé, négatif.
- **Recommandation :**
  - n'acheter aucun challenge ;
  - lancer R1 seulement si l'orchestrateur veut un regard de fermeture propre ; sinon, consigner la famille comme fermée au vu des 41 regards de découverte.

## 8. Sources (consultées le 2026-10-10)

E-nano :
- [N1] Communiqué CME, 2026-08-03 : https://www.cmegroup.com/media-room/press-releases/2026/8/03/cme_group_to_expandretailaccesstofourleadingbenchmarkswithe-nano.html (délai dépassé, lu via ses reprises) ; https://finviz.com/news/375979/cme-group-to-expand-retail-access-to-four-leading-benchmarks-with-e-nano-equity-index-futures-launch-on-august-24 ; https://smb.thepostsearchlight.com/article/CME-Group-to-Expand-Retail-Access-to-Four-Leading-Benchmarks-with-E-nano-Equity-Index-Futures-Launch-on-August-24/6a708aa10b3f8c6777521d24
- [N2] Finance Magnates, « CME shrinks its contracts again » : https://www.financemagnates.com/forex/analysis/cme-shrinks-its-contracts-again-will-that-pull-retail-away-from-cfds/
- [N3] CQG, « CME Offers E-nano Stock Index Futures » (2026-08) : https://news.cqg.com/workspaces/2026/08/cme-offers-e-nano-stock-index-futures
- [N4] Topstep Brokerage, « What are E-nano Equity Index Futures? » : https://help.topstepbrokerage.com/en/articles/16559695-what-are-e-nano-equity-index-futures
- [N5] NinjaTrader, E-nano : https://ninjatrader.com/futures/futures-contracts/e-nano/
- [N6] MetroTrade : https://www.metrotrade.com/what-are-e-nano-equity-index-futures/
- [N7] Ironbeam : https://www.ironbeam.com/what-are-e-nano-futures-explained/ et https://www.ironbeam.com/how-to-trade-e-nano-sp-500-futures/
- Pages CME (fiche, FAQ, spécifications) : https://www.cmegroup.com/markets/equities/nasdaq/e-nano-nasdaq-100.contractSpecs.html, https://www.cmegroup.com/articles/faqs/faq-e-nano-equity-index-futures.html (accès automatisé bloqué, non contourné)

Firmes :
- [F1] Topstep, produits permis (mise à jour le 2026-07-13) : https://intercom.help/topstep-llc/en/articles/8284206-when-and-what-products-can-i-trade
- [F2] TopstepX, commissions : https://help.topstep.com/en/articles/8284213-topstepx-commissions-and-fees
- [F3] Lucid, produits approuvés (secondaire, 2026-08-12) : https://proptradingvibes.com/blog/lucid-trading-approved-products
- [F4] Phidias, CGU officielles : https://phidiaspropfirm.com/tou (version française faisant foi : https://phidiaspropfirm.com/fr/cgu)
- [F5] MFFU, Flex et automatisation (secondaires) : https://www.fundedtrading.com/propfirm/my-funded-futures/ ; https://blog.traderspost.io/article/automate-my-funded-futures-with-traderspost ; T-050 pour la page officielle
- [F6] FundedNext Futures, pays restreints (officiel, 2026-09-30) : https://helpfutures.fundednext.com/en/articles/17228971-are-any-countries-restricted-on-fundednext-futures
- [F7] FundedNext Futures, bots (officiel, 2026-04-09) : https://helpfutures.fundednext.com/en/articles/14298560-is-the-usage-of-automated-trading-systems-eas-and-bots-allowed-in-fundednext-futures
- [F8] FundedNext Rapid (secondaire) : https://tradetanto.com/learn/fundednext-futures-rules-a-complete-breakdown ; https://pipback.com/blog/fundednext-futures-review
- [F9] Lucid, changements 2026 (secondaire) : https://proptradingvibes.com/blog/lucid-trading-payout-rules ; https://thedefiant.io/news/markets/lucid-trading-rolls-out-major-live-program-overhaul-and-launches-lucidmaxx
- [F10] FTMO Futures, « Who can join » (officiel) : https://ftmo.com/en/futures/faq/who-can-join-ftmo-futures/
- [F11] FTMO, stratégies permises (extrait de recherche) : https://ftmo.oanda.com/faq/which-simulated-instruments-can-i-trade-and-what-strategies-am-i-allowed-to-use/ ; https://thegodfunded.com/en/firms/ftmofutures/
- [F12] FTMO Futures, règles (secondaire) : https://tradetanto.com/learn/ftmo-futures-rules ; https://traderssecondbrain.com/guides/ftmo-futures-eod-trailing-drawdown
- Règles Topstep, Lucid, Tradeify, MFFU et Bulenox antérieures : `venues/FUNDED_FUTURES_2026-10-08.md` (T-050), `research/H-R17_funded_optimal.md` §1.

Littérature :
- Grant, Wolf, Yu (2005), « Intraday price reversals in the US stock index futures market: A 15-year study », JBF 29(5), 1311-1327 : https://ideas.repec.org/a/eee/jbfina/v29y2005i5p1311-1327.html ; résumé : https://researchwith.montclair.edu/en/publications/intraday-price-reversals-in-the-us-stock-index-futures-market-a-1/
- Yu, Rentzler, Wolf (2005), « NASDAQ-100 Index Futures: Intraday Momentum or Reversal? », JOIM 3(3) : https://joim.com/article/nasdaq-100-index-futures-intraday-momentum-or-reversal/
- Baltussen, Da, Lammers, Martens (2021), « Hedging demand and market intraday momentum », JFE : https://www3.nd.edu/~zda/intramom.pdf
- Ni, Pearson, Poteshman, White (2021), « Does option trading have a pervasive impact on underlying stock prices? », RFS 34(4) (non relu aujourd'hui)
- Gao, Han, Li, Zhou (2018), « Market intraday momentum », JFE 129(2) (lu pour l'Exp 64)
- Zarattini, Aziz, Barbon (2024), « Beat the Market », SSRN 4824172 : https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4824172
- Zarattini, Aziz (2023), « VWAP: The Holy Grail for Day Trading Systems » (SSRN, résumé) : https://concretumgroup.com/volume-weighted-average-price-vwap-the-holy-grail-for-day-trading-systems/ ; ORB sur « stocks in play » : https://www.cxoadvisory.com/individual-investing/intraday-trading-of-overactive-stocks-via-opening-range-breakout/
- Holmberg, Lönnbark, Lundström (2013), « Assessing the profitability of intraday opening range breakout strategies », Finance Research Letters 10(1), 27-33 : https://ideas.repec.org/a/eee/finlet/v10y2013i1p27-33.html
- Boyarchenko, Larsen, Whelan (2023), « The Overnight Drift », RFS 36(9) : https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr917.pdf ; « The Disappearing Overnight Drift », Liberty Street Economics, 2026-07-01 : https://libertystreeteconomics.newyorkfed.org/2026/07/the-disappearing-overnight-drift/
- Gap fill sur E-mini S&P 500 (mémoire de master, Nova SBE, **non évalué par les pairs**, non lu en entier) : https://run.unl.pt/handle/10362/145336
- Non académiques (non relus) : T. Crabel (1990), *Day Trading with Short Term Price Patterns and Opening Range Breakout* ; A. Pagonidis (2014), « The IBS Effect: Mean Reversion in Equity ETFs », NAAIM ; L. Connors, RSI(2).
