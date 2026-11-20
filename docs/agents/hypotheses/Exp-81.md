# Exp 81 — Saison REER/CELI : TSX contre S&P 500 — PRÉENREGISTREMENT

- **ID :** Exp 81 (T-076). Préenregistré le 2026-10-12 par l'orchestrateur et figé par ce commit, **avant tout téléchargement de cours** pour cette expérience. Juge : Validateur.
- **Source :** brouillon H-R21 §5.1 (branche agents/t075-hr21, ac90f7e), repris tel quel ci-dessous.
- **Arbitrage de l'orchestrateur :** le Deflated Sharpe est rapporté avec N = 132, le choix prudent ; N = 95 est rapporté à côté.


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

