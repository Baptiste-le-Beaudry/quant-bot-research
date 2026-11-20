# Exp 76 — Actions US ×1 + tendance (TSMOM) ×1 empilées, contre levier constant à volatilité égale — PRÉENREGISTREMENT

- **ID :** Exp 76 / `L-STACK-TREND-001` (T-072). Préenregistré le 2026-10-11 par l'orchestrateur, figé par ce commit **avant tout téléchargement de séries de rendements**. Juge : Validateur.
- **Source :** brouillon de H-R20 §5 (piste n° 1, branche agents/t071-hr20, 5e91caa). Il est repris tel quel ci-dessous ; les seules modifications sont l'en-tête et la précision sur les données.
- Compteur global : N = 76.

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

