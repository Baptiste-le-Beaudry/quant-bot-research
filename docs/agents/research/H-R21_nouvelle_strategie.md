# H-R21 — Marchés les plus prometteurs sur 5 ans, et 15 idées « qui est de l'autre côté ? » (T-075, agent Chercheur, 2026-10-11)

- **Branche :** `agents/t075-hr21` (depuis `agents/orchestration-20261006`, commit 1301ed1).
- **Statut :** revue de littérature et de données publiques. **Aucun backtest.** Aucune série de rendements n'a été téléchargée pour les deux finalistes : leurs données de test restent vierges.
- **Seuls chiffres calculés ici :** deux identités arithmétiques (rendement du bénéfice CAPE moins taux réel ; bruit d'un rendement sur 5 ans). Elles sont marquées **« exploratoire, ne compte pas »**.
- **Profil visé :** l'auteur, Québec, ≈ 15 000 CAD, CELI et compte imposable possibles, accepte un MaxDD jusqu'à −50 %, veut le plus de rendement possible.
- **Sources :** toutes consultées le **2026-10-11** (§9). « Non académique » = gérant, émetteur de FNB, presse ou site de données.

## 0. Réponse courte

**Partie 1 : marchés sur 5 ans.**
- **Les actions américaines sont à un niveau de prix historique.** Le CAPE de Shiller du S&P 500 est à 41,9 (2026-10-09). Le record est 44,2 (décembre 1999).
- **En même temps, le placement sans risque paie beaucoup plus qu'avant.** Les obligations indexées américaines à 10 ans rapportent 2,91 % réel et les bons du Trésor américains 4,25 % (2026-10-09). Le rendement des bénéfices du S&P 500 (1/CAPE ≈ 2,4 %) est donc **plus bas** que le taux réel sans risque. C'est rare : la dernière fois, c'était vers 2000.
- **Les six grands gérants consultés voient tous les actions hors États-Unis devant les actions américaines.**
  - AQR : réel 4,9 % hors États-Unis contre 3,9 % aux États-Unis.
  - GMO : réel −1,5 % à +4,7 % selon les segments hors États-Unis, contre −7,4 % pour les grandes capitalisations américaines.
  - Research Affiliates : nominal 7,7 % contre 3,1 %.
  - Vanguard : nominal 4,5-6,5 % contre 4,2-6,2 %.
  - Les meilleures prévisions vont à la **valeur et aux petites capitalisations hors États-Unis** et à la **valeur des pays émergents**.
- **Mais ces prévisions expliquent peu ce qui arrive en 5 ans.**
  - Sur 10 ans, le CAPE explique ≈ 40 % des écarts de rendement aux États-Unis (Vanguard 2012).
  - Sur 5 ans, c'est moins. Sur un an, c'est presque rien.
  - Pour le **Canada**, le CAPE n'a presque rien prédit (R² ≈ 1 % selon Keimling, à vérifier).
  - Le bruit sur 5 ans (≈ ±7 %/an à un écart-type) est plus grand que les écarts entre marchés (2 à 6 points).
- **Classement prudent (§1.5) :**
  1. valeur et petites capitalisations hors États-Unis, valeur émergente ;
  2. actions développées hors États-Unis ;
  3. pays émergents et Canada (confiance faible) ;
  4. grandes capitalisations américaines en dernier.
- **Aucune prévision centrale n'approche 15 %/an.** Il faudrait du levier ou de la chance.

**Partie 2 : nouvelle stratégie.**
- 15 idées de « flux forcés », chacune avec un perdant identifiable (§2).
- **13 sont éliminées** : déjà connues ou arbitrées, non exécutables, ou sans données gratuites (§2.2).
- **2 finalistes**, toutes deux propres au Canada et sans trace dans la littérature que j'ai trouvée :
  - **F1 (I-01) — saison REER/CELI.** Les cotisations des comptes enregistrés sont concentrées de janvier à la date limite REER (≈ 1er mars). Elles devraient pousser la Bourse de Toronto au-dessus du S&P 500 pendant cette fenêtre. Prédiction supplémentaire obligatoire : le même effet en **mars au Royaume-Uni**, mais seulement depuis la création des PEP/ISA (1987).
  - **F2 (I-03) — rabais DRIP des banques canadiennes.** Quand une banque émet les actions du DRIP depuis le trésor avec un rabais de 2 % sur un prix moyen de 5 jours, l'action devrait baisser pendant ces 5 jours, puis remonter. Le test exploite les périodes où les banques ont activé puis retiré ce rabais (2022-2024 : RBC, CIBC, TD, BNS). Prédiction supplémentaire obligatoire : un volume anormal pendant la fenêtre.
- Brouillons de préenregistrement complets au §5 (proposés : **Exp 81** et **Exp 82**).
- **Attente honnête :**
  - même si elles passent, ce sont des **compléments de +0,5 à +2 %/an**, pas des stratégies à 15 % ;
  - probabilité a priori de PASS : **≈ 10-12 % pour F1** et **≈ 10 % pour F2**.
- **Compteur de tests multiples :** 80 essais au registre + 15 idées ici = **N = 95**. Le DSR de l'atelier T-073 utilisait 117 configurations ; la version prudente est donc **N = 132**.

---

# PARTIE 1 — Marchés les plus prometteurs sur 5 ans

## 1.1 Valorisations actuelles (CAPE par pays)

Source principale : Siblis Research, données au **2026-09-30** (indices MSCI ; méthode différente de celle de Shiller pour les États-Unis).

| Pays / région | CAPE | Lecture |
|---|---|---|
| Taïwan | 46,7 | très cher (semi-conducteurs, IA) |
| États-Unis (MSCI) | 35,9 | très cher. **Shiller S&P 500 : 41,87 au 2026-10-09** ; moyenne 1871 → : 17,4 ; record : 44,2 (1999-12) |
| Japon | 35,4 | cher selon ce calcul (bénéfices passés faibles ; AQR situe les pays développés hors US près de leur médiane) |
| Corée du Sud | 31,8 | cher |
| Inde | 28,7 | cher |
| **Canada** | **27,1** | au-dessus de la moyenne mondiale hors US |
| Suisse | 23,2 | moyen |
| Allemagne | 22,9 | moyen |
| Australie | 20,1 | moyen |
| Royaume-Uni | 19,6 | bon marché |
| France | 19,5 | bon marché |
| Mexique | 17,5 | bon marché |
| Chine | 17,1 | bon marché |
| Brésil | 14,9 | bon marché |
| Monde hors États-Unis | 21,0 (2026-06-30) | |
| Pays émergents | 19,4 (2026-06-30) | AQR : un CAPE de 23 fin 2025 = 98e centile depuis 2001 |

**Dispersion.** Le CAPE américain est ≈ 1,7 fois celui du monde hors États-Unis (35,9 / 21,0). AQR situe le CAPE américain au 96e centile depuis 1980. Les pays développés hors États-Unis sont près de leur médiane historique.

## 1.2 Taux réels, prime de risque, devise (vérifiés à la source le 2026-10-11)

| Mesure | Valeur | Date | Source |
|---|---|---|---|
| US 10 ans nominal | 5,24 % | 2026-10-09 | Trésor américain (CSV officiel) |
| US 3 mois | 4,25 % | 2026-10-09 | idem |
| **US TIPS 10 ans (réel)** | **2,91 %** | 2026-10-09 | idem (5 ans : 2,68 %) |
| Inflation implicite US 10 ans | ≈ 2,3 % | 2026-10-09 | 5,24 − 2,91 |
| Canada taux directeur | 2,25 % | 2026-10-08 | Banque du Canada (Valet) |
| Canada 5 ans / 10 ans | 3,60 % / 3,93 % | 2026-10-08 | idem |
| Canada obligations à rendement réel (longues) | 1,98 % réel | 2026-10-08 | idem (le Canada n'en émet plus depuis 2022) |
| USD/CAD | 1,427 | 2026-10-09 | idem |
| Prime de risque implicite S&P 500 (Damodaran) | 4,20 % au-dessus d'un T-bond de 5,29 % (3,70 % en version « rendement en liquidités ») | 2026-10-01 | Damodaran |

**Calcul exploratoire, ne compte pas.**
- Rendement des bénéfices CAPE du S&P 500 : 1/41,87 ≈ 2,39 %.
- Moins le TIPS 10 ans (2,91 %) : **≈ −0,5 point**.
- Les actions américaines rapportent donc moins en bénéfices lissés que l'obligation indexée sans risque. Ce n'était plus arrivé depuis environ 2000.
- La prime implicite de Damodaran (4,2 %) est plus favorable : elle suppose une croissance des bénéfices et compte les rachats d'actions.
- Contexte (presse, 2026-09-30 / 10-01) : taux longs au plus haut depuis 2002 après un choc pétrolier et une hausse de la Fed en septembre 2026.

## 1.3 Rendements attendus publiés par les gérants

| Gérant (date des données) | Horizon, unité | Actions US grandes cap. | US petites cap. | Développés hors US | Émergents | Obligations / liquidités |
|---|---|---|---|---|---|---|
| **AQR** (2025-12-31) | 5-10 ans, **réel**, devise locale | **3,9 %** | 5,1 % | 4,9 % (zone euro 5,0 ; R-U 4,9 ; Japon 4,9) | 5,1 % (hors Chine 4,8 ; Chine 5,8) | US 10 ans 2,4 % ; liquidités 1,3 % ; 60/40 mondial 3,4 % |
| **GMO** (2026-08-31) | 7 ans, **réel**, taux « normaux » | **−7,4 %** | −5,8 % ; valeur profonde US −0,7 % | grandes −1,5 % ; petites +0,8 % ; valeur profonde +3,0 % ; **Japon petites valeur +4,7 %** | −0,1 % ; **valeur émergente +3,3 %** | obligations US 2,7 % ; TIPS 2,7 % ; liquidités 1,5 % |
| **Research Affiliates** (2025-12-31, via Morningstar) | 10 ans, **nominal** | **3,1 %** | 7,1 % | 7,7 % | 7,5 % | obligations US 4,7 % |
| **Vanguard VCMM** (2026-06-30) | 10 ans, nominal (fourchette) | 4,2-6,2 % | 4,2-6,2 % | 4,5-6,5 % | 2-4 % (lu par résumé automatique ; à vérifier) | — |
| Vanguard (2025-10-31, via Morningstar) | 10 ans, nominal | 3,5-5,5 % ; croissance 2,3-4,3 % ; valeur 5,8-7,8 % | 5,1-7,1 % | 4,9-6,9 % (hors US total) | — | obligations US 3,8-4,8 % |
| **BlackRock** (2025-09-30, via Morningstar) | 10 ans, nominal | 5,2 % | — | 7,1 % (hors US) | — | obligations US 4,1 % |
| J.P. Morgan (2025-09-30, via Morningstar) | 10-15 ans, nominal | 6,7 % | — | 7,5 % | 7,8 % | obligations US 4,8 % |

Lecture :
- **Accord sur le classement :** les gérants mettent les actions hors États-Unis devant les actions américaines.
- **Désaccord sur le niveau :** pour les grandes capitalisations américaines, de −7,4 % réel (GMO, qui suppose un retour des marges et des valorisations à la normale) à +3,9 % réel (AQR, qui ne suppose **aucun** retour des valorisations).
- AQR (2026) : il y a **50 % de chances que le rendement réel sur 10 ans s'écarte de plus de 3 %/an** de sa prévision.
- Pour un investisseur canadien, ajouter l'effet de change USD/CAD (non prévu) et l'inflation canadienne.

## 1.4 Pouvoir prédictif à 5 ans : faible

| Constat | Source |
|---|---|
| CAPE contre rendement réel sur 10 ans, États-Unis 1926-2011 : R² = 0,43. « Environ 60 % de la variation reste inexpliquée. » À un an, le pouvoir est presque nul. | Vanguard (Davis et al., 2012), cité par Swedroe / Evidence Investor |
| Les R² sur 10 ans sont gonflés par le chevauchement : deux points mensuels consécutifs partagent 119 mois sur 120. Avec des points par décennie, la relation est « bien plus faible ». CAPE à 35 en janvier 2021, et pourtant +49 % réel jusqu'au 2025-11-30. | Dimensional (Crill, 2026-02-19) |
| Entre pays, CAPE contre rendement sur 10-15 ans : R² ≈ 0,48 en moyenne. Mais **Canada ≈ 1 %** (contre US 82 % depuis 1970 et 46 % depuis 1881). | Keimling (Star Capital, 2016), cité par Monevator ; chiffre canadien à vérifier sur la source primaire |
| Hors échantillon, les prédicteurs classiques (dividende/prix, etc.) ne battent pas la moyenne historique à un an. | Goyal et Welch (RFS 2008) |
| Prévisions de prix élevées → rendement plus faible, mais avec un délai inconnu. Le marché peut rester cher 5 ans de plus. | AQR 2026 ; GMO |

**Calcul exploratoire, ne compte pas.**
- Un indice d'actions a une volatilité de ≈ 16 %/an.
- Sur 5 ans, l'écart-type du rendement annualisé est donc ≈ 16 / √5 ≈ **7 %/an**.
- L'écart entre la meilleure et la pire prévision centrale (≈ 2 à 6 points selon le gérant) est **plus petit qu'un écart-type de bruit**.

## 1.5 Classement prudent sur 5 ans (réel, annualisé, avant frais)

« Central » = zone où tombent la plupart des prévisions ci-dessus, ramenées en réel quand elles sont nominales (inflation ≈ 2,3-2,5 %). « Fourchette 90 % » = central ± 1,65 × 7 %. C'est une **opinion prudente, pas une mesure**.

| Rang | Segment | Central (réel/an) | Fourchette 90 % (réel/an) | Confiance dans le rang | FNB accessibles au Québec (à vérifier chez le courtier) |
|---|---|---|---|---|---|
| 1 | Valeur et petites capitalisations hors US ; valeur émergente | +3 à +5 % | −8 à +16 % | faible-moyenne (GMO, AQR, RA, Vanguard d'accord sur le sens) | Canada : **CASV** (Avantis CIBC petites cap. valeur mondiales, 2026) ; **CADE** (Avantis CIBC international) ; US : AVDV, DFIS, AVES, DFEV (retenue US de 15 % perdue dans le CELI) |
| 2 | Actions développées hors US (Europe, R-U, Japon) | +2 à +5 % | −10 à +16 % | moyenne | XEF, ZEA, VIU (CAD) ; Japon : ZJPN (BMO, frais 0,39 %) |
| 3 | Pays émergents (indice large) | +1 à +5 % | −12 à +17 % | faible (Vanguard 2-4 % nominal contre AQR 5,1 % réel) | XEC, ZEM, VEE, XEM, QEE |
| 3 ex æquo | Canada (TSX) | +2 à +5 % | −10 à +16 % | **très faible** : pas de chiffre séparé chez AQR ; CAPE 27 ; le CAPE n'a rien prédit au Canada | XIC, VCN, ZCN, CACE |
| — | Obligations indexées (détenues jusqu'à l'échéance) | US TIPS : **2,7-2,9 %** ; obligations à rendement réel du Canada : ≈ 2,0 % | quasi certain en devise locale (le risque de change USD/CAD s'ajoute pour les TIPS non couverts) | élevée | ZRR, XRB (rendement réel canadien) ; TIPS : à vérifier |
| 5 | Grandes capitalisations américaines | ≈ +1 à +2 % (de −7 à +4 selon le gérant) | −13 à +14 % | moyenne pour le rang, faible pour le niveau | XUS, VFV, ZSP, XUU |

Ce que ça implique pour un Canadien (Québec), sans être un conseil :
1. **Les FNB « tout-en-un » (XEQT, VEQT) ont ≈ 45 % d'actions américaines.** Un portefeuille qui suit les prévisions aurait moins d'actions américaines et plus de développés hors US, de valeur et de petites capitalisations. Mais le pouvoir prédictif à 5 ans est faible : un écart modéré (par exemple 30 % US au lieu de 45 %) est plus défendable qu'un pari complet.
2. **Pour viser 15 %/an,** aucune prévision centrale ne suffit : il faut du levier (H-R20, Exp 74 : ≈ 12 %/an attendu pour S&P ×2 + MM200) et accepter un MaxDD de −40 à −60 %. Le levier sur un marché cher (US) est moins attrayant que le levier sur un marché moins cher. Aucun FNB à levier canadien sur les indices hors US n'a été vérifié ici (HEQL est mondial ×1,25 ; HSU est S&P ×2).
3. **Le taux réel sans risque est élevé** (TIPS 2,9 %, rendement réel canadien 2,0 %). Le coût d'emprunt du levier augmente d'autant. Le seuil de Sharpe de H-R20 §1 (0,63-0,73) a été calculé avec un taux sans risque de 3,5 % ; avec des bons du Trésor à 4,25 %, il change peu, car le Sharpe est déjà mesuré au-dessus du taux sans risque.
4. **Fiscalité :**
   - dans le CELI, la retenue étrangère est perdue (≈ 0,2-0,6 %/an selon la structure du FNB) ;
   - un FNB **canadien** qui détient directement des actions étrangères (XEF, XEC) perd une seule couche de retenue ;
   - un FNB **américain** qui détient des actions étrangères (AVDV) en perd deux ;
   - dans le compte imposable, le crédit pour impôt étranger récupère une partie de ces retenues.

---

# PARTIE 2 — Inventer une stratégie : 15 idées « qui est de l'autre côté ? »

## 2.0 Méthode et anti-doublon

- Chaque idée nomme un **perdant identifiable** : quelqu'un obligé d'acheter ou de vendre à cause d'une règle (mandat, fiscalité, indice, calendrier, couverture), et non par opinion sur le prix.
- **Prédiction supplémentaire :** ce qui doit aussi être vrai si le mécanisme est réel, et qui se teste séparément du gain.
- **Lu avant d'écrire :** `REPRISE.md` §3 (liste des rejets), `REGISTRY.csv` (Exp 49-80), `research/INDEX.md`, H-R20, `results/Exp-77-80_validation_2026-10-11.md`, `research/atelier/IDEES.md` (idées I1-I12, configurations C01-C20).
- Recherche dans `docs/research_plan_status.md`, `research/`, `hypotheses/` et `JOURNAL.md` des mots-clés DRIP, REER/RRSP, perte fiscale, USD/CAD, Hartzmark, Melvin, anges déchus, BCOM, TSX, StatCan : **aucun travail antérieur** sur ces mécanismes. Le TSX n'apparaît qu'en passant (H-R16, H-R18).
- Leçon de l'atelier D-09 (Exp 77-80) : quatre règles très positives sur 1990-2009 (ΔSharpe de +0,18 à +0,42) sont toutes devenues négatives après 2009 (de −0,03 à −0,28). D'où les deux choix suivants :
  - privilégier des mécanismes avec une **expérience naturelle** (une règle qui s'allume ou s'éteint à une date connue), plutôt qu'un paramètre ajusté sur l'historique ;
  - exiger une **prédiction supplémentaire** indépendante.

## 2.1 Les 15 idées

| # | Idée | Qui est de l'autre côté (perdant contraint) | Mécanisme | Prédiction supplémentaire (test séparé) |
|---|---|---|---|---|
| I-01 | **Saison REER/CELI** : surpondérer le TSX de fin décembre à la date limite REER | Épargnants canadiens qui doivent cotiser avant une date (CELI : droits remis le 1er janvier, depuis 2009 ; REER : 60e jour de l'année) ; ils achètent à prix gonflé par leurs propres flux ; biais domestique fort | Flux concentrés + marché peu élastique (Gabaix-Koijen) → pression d'achat sur les actions canadiennes en janvier-février | Même effet au **Royaume-Uni en mars** (date limite PEP/ISA le 5 avril), **seulement depuis 1987** (création des PEP), absent sur 1975-1986 |
| I-02 | Vente fiscale de décembre + règle de perte apparente (30 jours) | Particuliers imposables qui vendent leurs perdants avant le 31 décembre et ne peuvent pas racheter pendant 30 jours | Pression vendeuse en décembre, rebond en janvier | Effet absent au Canada avant 1972 (pas d'impôt sur les gains en capital) |
| I-03 | **Rabais DRIP des banques canadiennes** : acheter à la fin de la fenêtre de prix moyen | Actionnaires non participants (dilution à rabais) ; arbitragistes et participants qui vendent à découvert pendant les 5 jours de prix moyen pour figer le rabais | Émission du trésor à −2 % sur la moyenne des 5 jours avant le versement → ventes de couverture dans la fenêtre → baisse, puis reprise | **Volume anormal** dans la fenêtre seulement quand le rabais est actif ; la baisse augmente avec le nombre d'actions émises / volume quotidien |
| I-04 | Couverture de change mensuelle (USD/CAD) des fonds et FNB couverts | Gérants couverts obligés de réajuster leur couverture au fixing de 16 h (Londres) en fin de mois | Si les actions US ont monté dans le mois, les couvreurs canadiens vendent des USD → l'USD/CAD baisse avant le fixing | Effet proportionnel à la hausse des actions US dans le mois |
| I-05 | Rééquilibrage calendaire des caisses de retraite et fonds équilibrés (fin de mois et de trimestre) | Caisses à règle fixe (60/40) qui vendent les actions après une hausse | Ventes prévisibles → baisse avant le rééquilibrage, reprise après | Effet plus fort en fin de trimestre qu'en fin de mois |
| I-06 | Pression des versements de dividendes (TSX : banques et énergie paient en fin de mois) | Aucun perdant contraint : réinvestissement automatique (DRIP, FNB) | Achats prévisibles le jour du versement | Effet le jour du **versement**, pas le jour ex-dividende |
| I-07 | Retrait des indices « Aristocrates du dividende » après une baisse de dividende | FNB de dividendes (CDZ, SDY) obligés de vendre | Vente forcée → baisse excessive, reprise | Reprise malgré la dérive négative connue après une baisse de dividende |
| I-08 | Rééquilibrage de fin de séance des FNB à levier (BetaPro, FNB ×2 sur titres uniques) | FNB à levier obligés d'acheter après une hausse et de vendre après une baisse, au close | Momentum dans la dernière heure, retour le lendemain | Effet proportionnel aux actifs des FNB à levier |
| I-09 | Dérive avant les annonces de la Banque du Canada | — (pas de perdant contraint ; prime d'incertitude) | Hausse avant l'annonce, comme avant le FOMC | Effet sur le TSX et le CAD |
| I-10 | Allongement de la duration des indices obligataires en fin de mois (FTSE Canada Univers) | Fonds obligataires indiciels obligés d'acheter des obligations longues au dernier jour du mois | Achats prévisibles → obligations longues fortes en fin de mois | Effet plus fort les mois de grosses émissions |
| I-11 | Ventes forcées des « anges déchus » (obligations qui passent de « qualité » à « spéculatif ») | Fonds à mandat « qualité investissement » obligés de vendre | Décote temporaire, puis reprise | Reprise plus forte quand la part détenue par les fonds « qualité » est grande |
| I-12 | Offre d'options d'achat des FNB à options couvertes canadiens (banques, services publics) | Détenteurs de FNB à options couvertes qui vendent du potentiel de hausse à prix fixe, chaque mois | Offre forcée d'options → volatilité implicite déprimée → acheter des options bon marché | Écart volatilité implicite/réalisée plus faible sur les titres très « couverts » |
| I-13 | Repondération annuelle de l'indice des matières premières BCOM (janvier, jours 6-10) | Fonds indexés qui doivent acheter les matières premières dont le poids monte | Achats prévisibles pendant les jours de repondération | Effet proportionnel au flux en dollars / intérêt ouvert |
| I-14 | Plafonnement trimestriel des indices sectoriels plafonnés S&P/TSX (25 % ou 10 %) | FNB sectoriels obligés de vendre le plus gros titre au rééquilibrage | Ventes forcées → faiblesse avant, reprise après | Effet seulement quand le plafond est dépassé |
| I-15 | Retraits FERR de décembre + retraits CELI de décembre (pour récupérer le droit en janvier) | Retraités obligés de retirer un minimum (FERR) ; épargnants qui retirent du CELI en décembre | Ventes de décembre des titres canadiens à dividende détenus par les retraités | Faiblesse plus marquée sur les titres à fort dividende |

## 2.2 Vérification (connu ? exécutable ? doublon ?)

| # | Déjà connu / arbitré ? | Exécutable par l'auteur ? | Doublon projet ? | Verdict |
|---|---|---|---|---|
| I-01 | Saisonnalité canadienne étudiée (effet janvier, Athanassakos) ; **lien avec les cotisations REER/CELI : aucune étude trouvée** ; test UK/PEP-ISA non trouvé | oui : 2 bascules/an XIC ↔ FNB S&P en CAD (ZSP/VFV) dans le CELI, coût ≈ 0,02-0,05 %/ordre | même famille « calendrier » que Halloween (atelier C14) et tournant du mois (H-R18), mais mécanisme et marché différents | **FINALISTE F1** |
| I-02 | **connu** depuis les années 1980 (Berges, McConnell, Schlarbaum ; Athanassakos) ; effet janvier affaibli | oui | non | éliminé : connu |
| I-03 | Effet du jour de versement sur les DRIP **connu** (Berkman-Koch, JFQA 2017) ; ventes des souscripteurs pendant la fenêtre de prix des DRP **avec preneur ferme** en Australie connues (CMCRC 2014 : −5,5 % en moyenne), **mais pas pour les DRP sans preneur ferme**. Le cas canadien (rabais du trésor activé et retiré, 2022-2024) : aucune étude trouvée | oui : grandes banques liquides, ≤ 30 ordres/an | non (aucune action canadienne étudiée) | **FINALISTE F2** (prior baissé par le résultat australien sans preneur ferme) |
| I-04 | **connu et publié** (Melvin et Prins, J. Financial Markets 2015) ; les banques publient des estimations de flux de fin de mois | possible (forex IBKR), mais levier de change | non | éliminé : connu et suivi par les banques |
| I-05 | **connu** (Harvey, Mazzoleni, Melone, NBER w33554, 2025 : −17 pb le lendemain quand les actions sont surpondérées) | oui | proche de l'atelier (mélanges fixes) | éliminé : publié en 2025, sera arbitré |
| I-06 | **connu** (Hartzmark-Solomon, « Predictable Price Pressure », NBER w30688 ; effet international inclus) | oui | non | éliminé : connu, y compris hors États-Unis |
| I-07 | variante de l'effet de retrait d'indice **connu** (Chen-Noronha-Singal 2004 ; FNB NIXT de Research Affiliates) ; SDY ≈ 3 retraits/an seulement | oui | non | éliminé : connu et trop peu d'événements (puissance faible) |
| I-08 | **connu** (Cheng-Madhavan 2009 ; Baltussen et al. 2021) | oui | **doublon de H-R06** (momentum de fin de séance) | éliminé |
| I-09 | **contredit** par la littérature : aucune prime d'annonce pour les banques centrales autres que la Fed (Brusa, Savor, Wilson, Review of Finance 2020) | oui | non | éliminé : absent |
| I-10 | **connu** aux États-Unis (effet de fin de mois sur les Treasuries) ; gain ≈ quelques pb, inférieur aux coûts d'un FNB obligataire long | oui, mais coûts > gain | non | éliminé |
| I-11 | **connu** (Ambrose, Cai, Helwege) et **produit** (FNB FALN) | oui (FALN) | non | éliminé : déjà vendu sous forme de FNB |
| I-12 | mécanisme discuté par des gérants (T. Rowe Price 2025, J.P. Morgan) | **non** en pratique : options de la Bourse de Montréal à écarts larges ; historique de volatilité implicite payant | non | éliminé : coûts et données |
| I-13 | **connu** des praticiens (estimations publiées chaque année) ; 1 événement/an | partiel : FNB à une seule matière première coûteux (contango) | proche d'Exp 54 (métaux/énergie) | éliminé : puissance et coûts |
| I-14 | peu étudié | oui | non | éliminé : **pas de données gratuites** sur les poids historiques et les dates de plafonnement |
| I-15 | non trouvé | oui | non | éliminé : confondu avec I-02 (vente fiscale de décembre) et retraits FERR étalés dans l'année (souvent mensuels) ; reporté comme **contrôle** dans F1 (décembre) |

Conditions communes vérifiées pour F1 et F2 :
- instruments cotés au Canada, accessibles chez Questrade, IBKR ou Wealthsimple ;
- ≤ 50 ordres/an ;
- pas de VPN, pas de Polymarket ni de Kalshi ;
- pas de levier obligatoire.

## 3. Pourquoi ces deux finalistes, et ce qui pourrait les tuer

**F1 — saison REER/CELI (I-01)**
- *Pour :*
  - le perdant est clair et contraint par la loi (date limite) ;
  - les flux sont gros et mesurés (IFIC : plus de 9 G$ de ventes nettes pour les fonds communs et autant pour les FNB lors d'un mois de février récent ; année à confirmer sur le communiqué) ;
  - expérience naturelle à l'étranger : PEP/ISA au Royaume-Uni, avec une date limite différente (5 avril) et une date de création connue (1987) ;
  - données gratuites **jamais utilisées** par le projet : TSX mensuel StatCan depuis 1956, pays Ken French depuis 1975.
- *Contre :*
  - une grande partie des cotisations va aux obligations, aux fonds monétaires et aux actions étrangères ;
  - les cotisations s'étalent de plus en plus (prélèvements automatiques, Globe and Mail) ;
  - la saisonnalité de janvier (petites capitalisations) peut produire un faux positif. Le TSX et le S&P sont tous deux pondérés par la capitalisation, ce qui atténue ce risque sans le supprimer ;
  - puissance faible : une seule observation par an (≈ 70 ans).
- *Gain maximal plausible :* +0,5 à +1,5 %/an en complément.

**F2 — rabais DRIP (I-03)**
- *Pour :*
  - interrupteur exogène : les banques activent ou retirent le rabais pour des raisons de capital réglementaire, pas pour le prix (RBC : 2 % de 2022-11 à 2024-02, puis achats sur le marché ; CIBC : rabais retiré pour le dividende du 2024-07-29 ; TD : rabais de 2 % annoncé le 2022-05-26, statut actuel à vérifier) ;
  - comparaison possible avec la même action quand le rabais est éteint ;
  - données gratuites jamais utilisées : actions canadiennes quotidiennes (Yahoo `.TO`), communiqués, rapports trimestriels ;
  - autre pays : banques australiennes.
- *Contre :*
  - le gain d'arbitrage est petit (2 % du dividende ≈ 0,025 % de la position par trimestre), donc peu de vendeurs à découvert ;
  - le CMCRC ne trouve **pas** de ventes anormales dans les DRP australiens **sans** preneur ferme ;
  - effet attendu : petit (−0,1 à −0,5 % dans la fenêtre).
- *Gain maximal plausible :* +0,3 à +2 %/an en complément d'une détention de banques.

**Ce que ni F1 ni F2 ne feront :** atteindre 15 %/an seules. Ce sont des tests de **mécanisme**. S'ils passent, ils s'ajoutent à la piste « levier modéré » de H-R20/T-069.

## 4. Données jamais utilisées par le projet (vérifiées en existence, non téléchargées)

| Donnée | Couverture | Accès | Pour |
|---|---|---|---|
| StatCan, tableau 10-10-0125-01 « Toronto Stock Exchange statistics » : S&P/TSX composé, clôture mensuelle | **1956 →** (avant 1990 : jamais vu par le projet) | gratuit (CSV StatCan) | F1 |
| Indice S&P 500, clôture de fin de mois (pas la moyenne mensuelle de Shiller) | 1950 → (Yahoo ^GSPC mensuel) | gratuit | F1 |
| Ken French, « Country Portfolios formed on B/M… » (MSCI puis Bloomberg), rendements mensuels en USD par pays | **1975 →** | gratuit | F1 (Royaume-Uni, Canada, US) |
| IFIC, ventes nettes mensuelles des fonds communs et FNB (communiqués) | ≈ 2005 → | gratuit (communiqués) | F1 (rapporté) |
| Yahoo `.TO` quotidien (cours + volume) des 6 grandes banques et de ≈ 10 grands payeurs de dividendes à DRIP | ≈ 2000 → | gratuit | F2 |
| Communiqués de dividende (SEDAR+, sites des banques) : trésor ou marché, rabais, date de versement | ≈ 2000 → | gratuit, saisie manuelle | F2 |
| Rapports trimestriels : actions émises par le DRIP | ≈ 2005 → | gratuit | F2 (intensité) |
| Yahoo `.AX` quotidien des 4 grandes banques australiennes + annonces de prix DRP (ASX) | ≈ 2005 → | gratuit | F2 (autre pays) |
| Banque du Canada (Valet) : USD/CAD quotidien ; FRED EXCAUS mensuel 1971 → | 1971 → | gratuit | F1 (version CAD) |

---

## 5. Brouillons de préenregistrement

À relire et figer par l'orchestrateur **avant tout téléchargement**. Numéros proposés : prochain libre = Exp 81 (REPRISE §5).

### 5.1 Exp 81 (F1) — Saison REER/CELI : TSX contre S&P 500, de fin décembre à la date limite REER

**Hypothèse.** Pendant la saison des cotisations (du dernier jour de bourse de décembre à la date limite REER), le S&P/TSX composé fait mieux que le S&P 500, en devise locale, que pendant le reste de l'année. Le mécanisme est la pression d'achat des cotisations REER/CELI, avec un biais domestique.

**Données (gratuites ; dates de téléchargement à noter).**
- TSX : StatCan 10-10-0125-01, clôture mensuelle 1956-01 → dernier mois ; Yahoo ^GSPTSE quotidien (1979 →) pour la fenêtre exacte.
- S&P 500 : Yahoo ^GSPC, clôture de fin de mois (1950 →) et quotidien.
- Les deux sont des **indices de prix** : les écarts de dividende sont stables d'un mois à l'autre et n'affectent pas la comparaison saisonnière. La version rendement total est rapportée là où elle existe (^GSPTSE TR, SP500TR depuis 1988).
- Supplémentaire : Ken French Country Portfolios (Royaume-Uni, Canada, US, et marché « Developed » s'il est présent), mensuel en USD, 1975 →.
- Change : FRED EXCAUS (1971 →), pour la version en CAD seulement.

**Règle (figée).**
1. Fenêtre saison S(y) :
   - version mensuelle (décisionnelle, car elle couvre 1957 → sans trou) : de la clôture de fin décembre de y−1 à la clôture de fin février de y ;
   - version quotidienne (rapportée, 1980 →) : de la clôture du dernier jour de bourse de décembre à la clôture de la date limite REER (60e jour de l'année ; jour ouvrable suivant si férié).
2. Écart de saison : E_S(y) = rTSX(S) − rSPX(S) (rendements simples sur la fenêtre, devise locale).
3. Écart de référence : E_R(y) = [rTSX(mars-déc. de y) − rSPX(mars-déc. de y)] × 2/10, c'est-à-dire l'écart moyen de deux mois hors saison.
4. Statistique : D(y) = E_S(y) − E_R(y). Test : moyenne de D sur les années, t de Student (une observation par an, sans chevauchement).
5. Règle de portefeuille (pour le chiffre de rendement) :
   - 100 % FNB TSX pendant S(y), 100 % FNB S&P 500 en CAD le reste de l'année ;
   - signal connu d'avance (calendrier) ; décision à la clôture de j−1, exécution à la clôture de j (convention t+1 du projet) ;
   - coût **0,10 % par bascule** (vente + achat), soit 0,20 %/an.

**Référence (le vrai test).**
- Mélange constant : 1/6 TSX + 5/6 S&P (la même part de temps que la règle), rééquilibré chaque mois avec le même coût.
- Multiplié par L constant pour avoir la **même volatilité** que la règle sur la même période, avec un levier financé au T-bill + 1,8 %/an (convention atelier) si L > 1.

**Périodes.**
- Entière : 1957 → dernière année complète.
- Avant 1990 : 1957-1989 (**jamais vu par le projet**).
- 1990-2008.
- CELI : 2009 → fin (rapporté).

**Prédiction supplémentaire (obligatoire).**
- Royaume-Uni, Ken French en USD : U(y) = [rUK(mars) − rUS(mars)] − moyenne mensuelle de [rUK − rUS] sur les 11 autres mois.
- Exigé : moyenne de U sur **1987 → fin** > 0 avec t ≥ 1,5.
- Rapporté sans effet : moyenne de U sur 1975-1986 (avant les PEP), dont on prédit qu'elle est ≈ 0.

**Critères (fixés).** PASS si tout est vrai :
1. Moyenne de D sur la période entière ≥ +0,75 point par saison, avec t ≥ 2,0.
2. Même signe (D > 0) sur 1957-1989 **et** sur 1990 → fin.
3. Prédiction supplémentaire UK remplie (moyenne > 0, t ≥ 1,5 sur 1987 →).
4. Règle de portefeuille nette des coûts : ΔSharpe contre la référence > 0 sur la période entière, et surplus annualisé ≥ +0,4 %/an.
5. Robustesse fixée d'avance, chaque point avec D > 0 :
   - (a) version quotidienne jusqu'à la date limite REER (1980 →) ;
   - (b) fenêtre décalée « 1er janvier → fin février » (exclut le dernier jour de décembre) ;
   - (c) Canada contre US dans les données Ken French en USD (1975 →).

REJET si la moyenne de D est ≤ 0 sur la période entière, **ou** si la prédiction UK est ≤ 0 sur 1987 →. INCERTAIN sinon.

**Rapporté sans effet.**
- D par décennie ;
- part du total venant des 3 meilleures années ;
- janvier seul contre février seul ;
- décembre (contrôle I-15 : faiblesse prédite par les retraits) ;
- mars-avril (prédiction de « reflux » : D ≤ 0 attendu) ;
- après 2009 contre 1990-2008 (effet CELI) ;
- corrélation entre l'écart de saison et les ventes nettes IFIC de janvier-février (≈ 2005 →, puissance faible) ;
- version en CAD avec FNB réels (XIC/ZSP) depuis leur création ;
- DSR avec N = 95 et N = 132.

**Variantes comptées.** 1 décisionnelle (mensuelle, fin décembre → fin février). Les variantes (a), (b), (c) sont des contrôles obligatoires, pas des choix.

**Probabilité a priori de PASS : ≈ 10-12 %.**
- Le critère 3 (Royaume-Uni) est exigeant.
- Le biais domestique des cotisations est dilué : beaucoup d'argent va aux obligations et aux fonds mondiaux.

**Limites connues avant calcul.**
- Indices de prix ;
- une observation par an ;
- la date limite REER varie de 1 à 3 jours (version mensuelle approximative) ;
- les chiffres Ken French sont en USD (le bruit de la livre sterling s'ajoute) ;
- l'effet janvier des petites capitalisations peut contaminer (contrôle (b)).

**Si PASS.** Revue du Validateur → suivi papier d'une saison (janvier-mars 2027) avec le comparateur affiché → décision de l'auteur. Mise en œuvre : 2 ordres/an dans le CELI (risque Ahamed nul).

### 5.2 Exp 82 (F2) — Rabais DRIP émis du trésor : baisse dans la fenêtre de prix, reprise après

**Hypothèse.** Quand un émetteur canadien émet les actions de son DRIP depuis le trésor avec un rabais (≥ 1 %) sur un prix moyen calculé sur les jours précédant le versement, l'action fait moins bien que ses pairs pendant cette fenêtre, puis mieux dans les 5 jours suivants. Rien de tel n'arrive pour la même action quand le rabais est éteint.

**Étape 0 (à faire et commiter AVANT de charger un seul prix).** Table d'événements figée, construite **uniquement** à partir des communiqués de dividende et des circulaires de DRIP :
- Univers : 6 grandes banques (RY, TD, BNS, BMO, CM, NA) + émetteurs de l'indice S&P/TSX 60 qui, à une date quelconque depuis 2000, ont émis des actions de DRIP depuis le trésor avec rabais. Liste établie à partir des communiqués, sans regarder les cours.
- Pour chaque date de versement P de chaque émetteur :
  - indicateur rabais (oui/non, taux) ;
  - source (trésor ou marché) ;
  - définition de la fenêtre de prix moyen selon la circulaire de l'émetteur (TD : moyenne des prix moyens pondérés des **5 jours de bourse avant** la date de placement = date de versement) ;
  - URL de la source.
- Si moins de **40 événements avec rabais** : arrêt, verdict INCERTAIN (puissance insuffisante), sans calcul de rendement.

**Données.** Yahoo `.TO` quotidien (clôture ajustée + volume), 2000 → ; ^GSPTSE ; rapports trimestriels (actions émises par le DRIP). Autre pays : 4 banques australiennes (`.AX`) et leurs annonces de prix DRP (ASX), en suivant la même étape 0.

**Mesures (figées).**
- P = date de versement (jour de bourse suivant si férié).
- Fenêtre A (prix moyen) : rendements des jours P−5 à P−1, ou la fenêtre de la circulaire si elle diffère.
- Fenêtre B (reprise) : rendements des jours P à P+4.
- Rendement anormal :
  - banques : rendement de l'action moins la moyenne équipondérée des grandes banques **sans rabais actif** ce jour-là (^GSPTSE s'il n'y en a aucune) ;
  - autres émetteurs : rendement de l'action moins ^GSPTSE.
- CAR_A, CAR_B = sommes des rendements anormaux.
- Différence-de-différences : DiD_A = moyenne CAR_A(rabais) − moyenne CAR_A(sans rabais, mêmes émetteurs) ; idem DiD_B. Erreurs-types regroupées par date de versement.

**Règle de trading (pour le chiffre de rendement).**
- Détenir le panier des banques équipondéré (ZEB ou panier reconstruit).
- Pour chaque événement avec rabais : basculer la part de ce panier vers l'action concernée.
- Signal connu d'avance : décision à la clôture de P−2, achat à la clôture de P−1 (ordre au marché à la clôture), revente à la clôture de P+4.
- Coût : **0,20 % par événement** (4 ordres ≈ 0,05 % chacun : écart + commission IBKR/Questrade sur grandes capitalisations TSX).
- Nombre d'ordres attendu : 8-40/an selon le nombre d'émetteurs avec rabais actif.

**Référence.** Panier des banques équipondéré × L constant, à la **même volatilité** que la règle, avec le même coût de financement si L > 1.

**Prédiction supplémentaire (obligatoire).**
- Volume anormal dans la fenêtre A : log(volume / médiane des 20 jours avant P−5).
- Exigé : DiD du volume anormal (rabais − sans rabais) **> 0 avec t ≥ 2**.
- Si les ventes de couverture existent, le volume doit monter **seulement** quand le rabais est actif.

**Critères (fixés).** PASS si tout est vrai :
1. DiD_A ≤ −0,20 point avec t ≤ −2,0.
2. DiD_B ≥ +0,15 point avec t ≥ 1,5 (reprise), et règle nette > 0 par événement après 0,20 % de coût.
3. Prédiction supplémentaire sur le volume remplie.
4. Robustesse fixée d'avance (DiD_A < 0 dans chaque cas) :
   - (a) banques seules ;
   - (b) émetteurs non bancaires seuls ;
   - (c) épisode 2022-2024 seul (interrupteur le plus net) ;
   - (d) rendement anormal mesuré contre ^GSPTSE pour tous ;
   - (e) Australie : banques avec DRP à rabais sans preneur ferme, même signe pour DiD_A. Ce point est rapporté si moins de 20 événements.
5. ΔSharpe de la règle contre la référence > 0 sur la période entière.

REJET si DiD_A ≥ 0, **ou** si le volume anormal DiD ≤ 0. INCERTAIN sinon (dont : moins de 40 événements).

**Rapporté sans effet.**
- Pente de CAR_A sur l'intensité (actions émises / volume quotidien moyen) ;
- résultats par émetteur ;
- part des 5 meilleurs événements ;
- rabais 1 % contre 2 % contre ≥ 3 % ;
- événements « achat sur le marché » (prédiction inverse : pression d'achat le jour P, Berkman-Koch) ;
- version « éviter la fenêtre » pour un détenteur de banques (vendre en P−6, racheter en P−1) ;
- DSR avec N = 95 et N = 132.

**Variantes comptées.** 1 décisionnelle. (a)-(e) sont des contrôles obligatoires.

**Probabilité a priori de PASS : ≈ 10 %.** Le petit gain d'arbitrage et le résultat australien nul pour les DRP sans preneur ferme pèsent contre.

**Limites connues avant calcul.**
- Pas de VWAP gratuit (on utilise la clôture) ;
- les cours ajustés de Yahoo peuvent comporter des erreurs autour des dividendes (vérifier sur 10 événements contre les cours bruts) ;
- biais de survie limité (grandes banques), mais réel pour les autres émetteurs ;
- risque Ahamed si plus de ≈ 30 ordres/an dans le CELI : faire la stratégie dans le compte imposable.

**Si PASS.** Revue du Validateur → suivi papier des événements de 2027 (dates connues d'avance) → décision de l'auteur.

---

## 6. Compteur de tests multiples

- Registre : 80 essais (Exp 49 → Exp 80, avec les essais hors numérotation).
- Ce document : **15 idées générées**. Aucune n'est testée ici.
- **N total à utiliser dans les DSR d'Exp 81/82 : 95.** Version prudente (configurations de l'atelier T-073 comptées une à une, N = 117 dans l'Exp 77-80) : **132**. Les deux sont rapportées.

## 7. Questions ouvertes pour l'orchestrateur

1. Valider les numéros Exp 81 et Exp 82 et figer les brouillons tels quels, ou n'en lancer qu'un (ordre conseillé : **F1 d'abord**, car son étape de données est plus simple et elle ne demande aucune saisie manuelle d'événements).
2. F2 étape 0 : saisie manuelle de ≈ 200-400 communiqués. À confier à un agent Développeur avec la consigne de ne charger **aucun cours** avant le commit de la table.
3. Partie 1 : vérifier sur les sources primaires le R² canadien de Keimling (≈ 1 %) et la fourchette Vanguard émergents (2-4 %) avant de les montrer à l'auteur comme des chiffres sûrs.

## 8. Ce que je n'ai pas fait

- Aucun téléchargement de cours pour F1 ni F2 (données de test vierges).
- Aucune ouverture des fichiers JOURNAL, STATE ou REGISTRY en écriture.
- Je n'ai pas obtenu les chiffres pays de Research Affiliates (outil réservé aux comptes) ni les fichiers détaillés de BlackRock (Excel derrière une page dynamique). J'ai utilisé les résumés datés de Morningstar.

## 9. Sources (consultées le 2026-10-11)

**Valorisations et taux**
- Siblis Research, CAPE par pays (données au 2026-09-30) : https://siblisresearch.com/data/cape-ratios-by-country/ ; CAPE mondial hors US et émergents (2026-06-30) : https://siblisresearch.com/data/world-cape-ratio/
- Multpl, CAPE de Shiller (41,87 au 2026-10-09 ; moyenne 17,42 ; maximum 44,19 en 1999-12) : https://www.multpl.com/shiller-pe
- Trésor américain, courbes nominale et réelle quotidiennes 2026 (CSV) : https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_real_yield_curve&field_tdr_date_value=2026&page&_format=csv
- Banque du Canada, API Valet (taux directeur V39079, rendements de référence 5 et 10 ans, obligations à rendement réel, USD/CAD) : https://www.bankofcanada.ca/valet/observations/BD.CDN.10YR.DQ.YLD,BD.CDN.5YR.DQ.YLD,BD.CDN.RRB.DQ.YLD,V39079,FXUSDCAD/json?recent=3
- A. Damodaran, prime de risque implicite au 2026-10-01 : https://pages.stern.nyu.edu/~adamodar/New_Home_Page/home.htm
- Contexte des taux (presse) : https://www.wealthprofessional.ca/investments/fixed-income/us-long-bond-clears-56-for-the-first-time-since-2002/393658 ; https://tradingeconomics.com/canada/government-bond-yield/news/588843

**Rendements attendus**
- AQR, « 2026 Capital Market Assumptions for Major Asset Classes » (données au 2025-12-31 ; Exhibits 1 et 3 lus) : https://www.aqr.com/-/media/AQR/Documents/Alternative-Thinking/AQR-Alternative-Thinking---2026-Capital-Market-Assumptions.pdf
- GMO, « 7-Year Asset Class Real Return Forecasts » au 2026-08-31 (PDF lu) : https://www.gmo.com/globalassets/articles/gmo-7-year-asset-class-forecast/2026/gmo-7-year-asset-class-forecastaug26.pdf
- Vanguard, prévisions VCMM au 2026-06-30 : https://corporate.vanguard.com/content/corporatesite/us/en/corp/vemo/vemo-return-forecasts.html
- Morningstar (C. Benz, 2026-01-12), « Experts Forecast Stock and Bond Returns: 2026 Edition » (Research Affiliates, BlackRock, J.P. Morgan, Vanguard, GMO, Schwab) : https://www.morningstar.com/markets/experts-forecast-stock-bond-returns-2026-edition
- BlackRock, Capital Market Assumptions (page au 2026-06-30, chiffres non extraits) : https://www.blackrock.com/institutions/en-us/insights/thought-leadership/capital-market-assumptions

**Pouvoir prédictif**
- Vanguard 2012 (R² 0,43 sur 10 ans), résumé : https://www.evidenceinvestor.com/post/the-shiller-cape-10-how-to-use-it-not-abuse-it ; https://www.etf.com/sections/index-investor-corner/swedroe-using-valuation-metrics
- W. Crill (Dimensional, 2026-02-19), « InCAPEable » : https://www.dimensional.com/ca-en/insights/incapeable
- Keimling (Star Capital), cité par Monevator (R² par pays, Canada ≈ 1 %) : https://monevator.com/cape-ratio-by-country/
- A. Goyal, I. Welch (2008), « A Comprehensive Look at the Empirical Performance of Equity Premium Prediction », *RFS* 21(4) : https://academic.oup.com/rfs/article/21/4/1455/1565737
- R. Shiller, diapositives (R² par horizon) : https://jacobslevycenter.wharton.upenn.edu/wp-content/uploads/2018/09/Shiller-Slides-1.pdf

**FNB canadiens**
- BMO ZJPN : https://stockanalysis.com/quote/tsx/ZJPN/
- FNB Avantis CIBC (CADE, CASV, CAGE, CACE…), 2026 : https://etfmarket.cboe.com/canada/en/news/this-week-in-canada-etfs-march-9-march-13-2026 ; https://usegreenline.com/articles/avantis-cibc-etfs-canada

**Partie 2 — mécanismes et littérature**
- REER : date limite et flux de février (IFIC) : https://www.investmentexecutive.com/news/product/february-was-the-strongest-month-for-mutual-fund-sales-in-three-years-ific/ ; étalement des cotisations : https://theglobeandmail.com/investing/globe-advisor/advisor-news/article-why-rrsp-season-is-no-longer-a-scramble-to-the-deadline-for-many
- G. Athanassakos, saisonnalité canadienne et gérants institutionnels : https://www.ivey.uwo.ca/media/3776173/the_january_effect.pdf ; https://www.ivey.uwo.ca/cmsmedia/3775495/the_seasonal_impact_of_institutional_investors.pdf
- StatCan 10-10-0125-01 (TSX 1956 →) : https://donnees.iriu.ca/en/dataset/0e1e57aa-e664-41b5-a69f-d814d4407d62
- Ken French Data Library (Country Portfolios 1975 →) : https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html
- Circulaire DRIP de TD (définition du prix moyen : 5 jours avant la date de placement ; rabais jusqu'à 5 %) : https://www.td.com/content/dam/tdcom/canada/about-td/pdf/dividendes/td-investor-drip-eng.pdf
- CIBC retire le rabais de 2 % (2024-05-30) : https://cibc.mediaroom.com/2024-05-30-CIBC-Declares-Dividends-for-the-Quarter-Ending-July-31,-2024-and-announces-a-change-to-its-Shareholder-Investment-Plan
- RBC : rabais de 2 % (2022-11), puis achats sur le marché : https://www.theglobeandmail.com/investing/markets/inside-the-market/article-rbc-joins-other-banks-in-offering-investors-option-to-reinvest/ ; https://www.newswire.ca/news-releases/royal-bank-of-canada-declares-dividends-899978729.html
- TD : avis de rabais de 2 % (annoncé le 2022-05-26 selon la presse ; contenu de ce PDF non lu) : https://www.td.com/content/dam/tdcom/canada/about-td/pdf/dividendes/td-investor-cdn-notice-en.pdf
- H. Berkman, P. Koch (2017), « DRIPs and the Dividend Pay Date Effect », *JFQA* 52(4) : https://ideas.repec.org/a/cup/jfinqa/v52y2017i04p1765-1795_00.html
- CMCRC (2014), DRP australiens avec preneur ferme : −5,5 % pendant la fenêtre de prix, pas d'effet sans preneur ferme : https://mondovisione.com/media-and-resources/news/cmcrc-underwriting-of-dividend-re-investment-plans-pushes-stock-prices-downward-2014624/
- M. Scholes, M. Wolfson (1989), DRIP à rabais (NBER w3093) : https://www.nber.org/papers/w3093
- M. Melvin, J. Prins (2015), « Equity hedging and exchange rates at the London 4 p.m. fix », *J. Financial Markets* 22 : https://ideas.repec.org/a/eee/finmar/v22y2015icp50-72.html
- C. Harvey, M. Mazzoleni, A. Melone (2025), « The Unintended Consequences of Rebalancing », NBER w33554 : https://www.nber.org/papers/w33554
- S. Hartzmark, D. Solomon, « Predictable Price Pressure », NBER w30688 : https://www.nber.org/papers/w30688
- J. Brusa, P. Savor, M. Wilson (2020), « One Central Bank to Rule Them All », *Review of Finance* 24(2) : https://ideas.repec.org/a/oup/revfin/v24y2020i2p263-304..html
- Retrait d'indice des Aristocrates (CDZ 2011) et FNB des retraits (NIXT) : https://www.moneysense.ca/?p=9846 ; https://www.tradingview.com/chart/NIXT ; S&P High Yield Dividend Aristocrats (≈ 3 retraits en 2024) : https://www.indexologyblog.com/tag/sp-high-yield-dividend-aristocrats/
- FNB à options couvertes et volatilité implicite (praticiens) : https://www.troweprice.com/en/us/insights/exploiting-durable-inefficiencies-in-the-equity-options-market ; https://www.alphavalue.com/Blog/volatility-etf-mop-up-vix
- Repondération BCOM 2026 (9-15 janvier) : https://www.wisdomtree.com/dk/insights/blog/a-new-ingredient-in-the-bloomberg-commodity-index

**Documents internes :** `REPRISE.md` §3, `REGISTRY.csv`, `research/INDEX.md`, `research/H-R20_quinze_pour_cent.md`, `research/atelier/IDEES.md`, `results/Exp-77-80_validation_2026-10-11.md`.
