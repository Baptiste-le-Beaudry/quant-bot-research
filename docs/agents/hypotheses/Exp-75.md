# Exp 75 — S&P 500 à volatilité ciblée et levier plafonné — PRÉENREGISTREMENT

- **ID :** Exp 75 / `L-VOLTARGET-001` (T-070). Le 2026-10-11, l'auteur accepte jusqu'à −50 % de baisse et demande de continuer à chercher plus de rendement. Préenregistré le 2026-10-11 par l'orchestrateur, figé par ce commit, **avant tout calcul**. Juge : Validateur.

## Pourquoi cette piste

- T-069 a montré que le surplus de l'Exp 74 vient du levier, pas d'un avantage.
- Le ciblage de volatilité est documenté pour **améliorer le rapport rendement/risque** sur les actions : moins exposé quand le marché est agité, plus quand il est calme. Références : Moreira et Muir (2017), « Volatility-Managed Portfolios », JF ; Harvey et al. (2018), « The Impact of Volatility Targeting », JPM.
- Si c'est vrai, on obtient plus de rendement **à risque égal**. C'est la seule façon honnête de dépasser le levier simple.
- Ce test applique la recommandation de T-069 : il faut battre un levier constant **à volatilité égale**, avec une robustesse fixée à l'avance.
- Compteur global : 75e essai, N = 75 pour le Deflated Sharpe.

## Règle (fixée)

1. **Volatilité de référence :** σ_t est la volatilité réalisée annualisée des rendements quotidiens du S&P 500 TR sur les 21 séances jusqu'à t inclus (écart-type × √252).
2. **Exposition cible :** w_t = min(3, V / σ_t), avec **V = 25 %** (décisionnel).
3. **Exécution :** w_t prend effet à la clôture de t+1. On ne rééquilibre que si |w_t − w_courant| ≥ 0,25 (bande anti-frais).
4. **Rendement quotidien :** w·r_TR − max(w − 1, 0)·rf + min(1 − w, 1)⁺·rf − frais.
   - Si w < 1, la part non investie touche rf.
   - Si w > 1, la part empruntée paie rf.
   - Frais : 0,95 %/an × max(w − 1, 0). Ce sont les frais des FNB à levier, appliqués au levier excédentaire.
   - Formulation équivalente : w·r_TR + (1 − w)·rf − 0,95 %·max(w − 1, 0)/252.
5. **Coût de transaction :** 0,10 % × |Δw| à chaque rééquilibrage.
6. **Données :** le cache de l'Exp 74 (`data/exp74_yahoo/` : ^SP500TR, ^GSPC, ^IRX, ^NDX, ^RUT, ^GDAXI), en USD.

## Référence (le vrai test)

- **Levier constant à volatilité égale :** w constant = L, avec L choisi pour que la volatilité réalisée de la référence soit égale à celle de la règle **sur la même période**.
- Même formule de rendement, frais sur L − 1, rééquilibrage quotidien gratuit (avantage donné à la référence).

## Périodes

| Période | Dates |
|---|---|
| Pré | 1990-01 → 2016-02 |
| Post | 2016-03 → fin des données |
| Entière | 1990-01 → fin des données |

## Critères (fixés)

**PASS** si toutes les conditions sont réunies :

1. Le Sharpe de la règle dépasse celui de la référence de **+0,10 ou plus** sur la période entière, et il est **> 0** en Pré comme en Post.
2. **Robustesse fixée d'avance :** V = 20 % et V = 30 % battent aussi leur propre référence à volatilité égale sur la période entière. L'écart de Sharpe doit être > 0 pour chacun.
3. **Même signe ailleurs :** l'écart de Sharpe sur la période entière est > 0 sur au moins 2 des 3 indices NDX, RUT et DAX. Chaque indice utilise sa propre volatilité, avec la même V et la même référence. On utilise le prix seul des deux côtés s'il n'y a pas d'indice de rendement total.
4. CAGR net Post ≥ 15 % et MaxDD ≥ −50 % sur la période entière, avec V = 25 %.

**REJET** si l'une de ces conditions est vraie :
- l'écart de Sharpe sur la période entière est ≤ 0 pour V = 25 % ;
- il est ≤ 0 sur 2 des 3 indices de l'étape 3.

**INCERTAIN** dans tous les autres cas.

**Rapporté sans effet :**
- CAGR, MaxDD, vol, pire année et nombre de rééquilibrages par an, par période ;
- levier moyen et part du temps au-dessus de ×2 ;
- Deflated Sharpe avec N = 75 ;
- combinaison avec le filtre MM200 de l'Exp 74 (w = 0 sous la MM200) ;
- fenêtre de 63 séances ;
- résultats en CAD ;
- fenêtres glissantes de 10 ans ;
- part du surplus venant des 3 meilleures années.

## Si PASS

1. Revue du Validateur.
2. Fiche pratique CELI : réaliser w avec un mélange FNB ×1, FNB ×2 et encaisse ; nombre de transactions ; risque d'« entreprise » au sens d'Ahamed.
3. Suivi paper de 3 mois.
4. Décision de l'auteur.

## Variantes comptées

- 1 décisionnelle (V = 25 %, fenêtre de 21 séances, plafond ×3, bande de 0,25).
- V = 20 % et V = 30 % sont des contrôles de robustesse obligatoires, pas des choix.
