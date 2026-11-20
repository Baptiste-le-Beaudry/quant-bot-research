# H-R04 — Creux propre à la pièce (résiduel) vs creux de tout le marché

- **Auteur** : agent Chercheur, tâche T-010, 2026-10-06
- **Type** : information nouvelle pour le signal (feature ou multiplicateur de taille)
- **Classement** : 5/6 (gain attendu moyen ; probabilité faible à modérée, car nos données internes se contredisent ; test très peu coûteux, données en cache ; même problème de puissance forward que H-R03)
- **Statut** : non testée.

## Mécanisme

En actions, le reversal à court terme se concentre dans la part **non expliquée par le marché ou
les fondamentaux** : Da, Liu et Schaumburg (2014) montrent que seule la composante résiduelle est
significative et que le reversal côté acheteur rémunère des chocs de liquidité (stratégie
améliorée ≈ 4 fois le rendement ajusté du reversal standard) ; la littérature du « residual
reversal » (Blitz et al. 2013) va dans le même sens. Idée transposée : quand SOL chute seul (un gros
vendeur, une liquidation locale), le prix s'écarte de sa valeur relative et le rebond est un retour
vers le marché ; quand SOL chute **avec** BTC et tout le marché, le creux peut être une révision
d'information commune (macro, droits de douane du 2025-10-10) qui ne se retourne pas forcément en
50 min.

Notre modèle n'a **aucune** feature inter-actifs : toutes les features de `build.py` sont calculées
sur la série du symbole seul.

Ce que disent nos données (convention de sortie non exécutable, donc à revérifier) se contredit :

- Exp 48 : entrées en rafale (≥ 3 autres pièces à ±60 min) ≈ +0,003 %/trade, PF 1,00 ; entrées
  isolées +0,307 %, PF 1,88, positives dans les deux moitiés → **soutient** l'hypothèse.
- Exp 41 : largeur de choc maximale (toutes les pièces en baisse aiguë) PF 1,57 contre 1,13
  ailleurs → **contredit** l'hypothèse (et rejoint Nagel 2012 : le stress paie la liquidité).

Les deux mesures diffèrent : l'Exp 41 compte des pièces en baisse (un état de marché), l'Exp 48
compte des **signaux** simultanés (le modèle déclenche partout). Le résiduel de rendement est une
troisième mesure, continue, qui n'a jamais été testée.

## Prédiction chiffrée et testable

Variable : part résiduelle du creux, R = r_15(symbole) − β · r_15(marché), avec marché = moyenne
équipondérée des autres symboles listés (BTC seul pour SOL/ETH en variante rapportée), β estimé sur
TRAIN (fenêtre 30 jours, données 1 min), r_15 = rendement des 15 dernières minutes. Statistique :
S = R / r_15 (part du creux qui est propre à la pièce).

1. Parmi les entrées sélectionnées (TIME50_NOSTOP, remplissage réaliste), le tercile S le plus élevé
   a un rendement moyen à 50 min supérieur d'au moins **0,10 point** au tercile S le plus bas.
2. Le signe tient dans les deux moitiés chronologiques et sur ≥ 5/9 symboles (3/3 pour SOL/BTC/ETH).
3. Rejet sinon ; aucune recherche de fenêtre (15 min fixée ici).

Si le résultat est inverse (creux de marché meilleurs, comme l'Exp 41), cela confirme Nagel et
renforce H-R02 (garder les rebonds de stress, contrôler la taille) : le test est informatif dans les
deux sens.

## Pourquoi survivrait aux coûts réels à 500 CAD

Aucun ordre supplémentaire ; si vrai, on concentre le capital sur le meilleur tiers des signaux, ce
qui augmente le rendement par trade au-dessus du coût Jupiter (0,01-0,05 % AR, H-R01). Pour
l'univers Jupiter (SOL/BTC/ETH), le marché de référence est calculable en live avec les mêmes flux.

## Comment tester

- **Rejet rapide (en échantillon)** : données 1 min en cache (`data/*USDT_1m_*.csv`), registre
  pré-HOLDOUT re-sorti en TIME50_NOSTOP + entrées Exp 50 ; tableau par terciles, diagnostic seul.
  Coût : quelques heures de calcul, pas de téléchargement.
- **Confirmation** : enregistrer S à chaque signal du runner forward (sans filtrer) et lire les
  terciles forward.

## Anti-doublon

- Exp 40 (choc BTC absolu, filtre, REJECT), Exp 41 (largeur de choc, REJECT au diagnostic), Exp 48
  (co-occurrence de signaux, REJECT) : aucune n'utilise le **rendement résiduel** de la pièce.
- Exp 42 (contribution marginale des symboles) : sujet différent (univers, pas signal).
- Recouvrement possible avec H-R03 (un creux résiduel est souvent un déleveraging local) : tester
  les deux sur la même population, compter les deux variantes dans le compteur de tests multiples.

## Risques et limites

- Contradiction Exp 41/48 : la probabilité a priori que l'effet soit stable est faible.
- β instable pendant les crises (les corrélations montent à 1) : S devient bruité précisément dans
  les épisodes qui comptent.

## Sources (consultées le 2026-10-06)

- Z. Da, Q. Liu, E. Schaumburg (2014), *A Closer Look at the Short-Term Return Reversal*, Management Science 60(3) : https://ideas.repec.org/a/inm/ormnsc/v60y2014i3p658-674.html
- CXO Advisory, *Refined short-term reversal strategies* (synthèse de la littérature du reversal résiduel) : https://www.cxoadvisory.com/animal-spirits/refined-short-term-reversal-strategies
- D. Blitz, J. Huij, S. Lansdorp, M. Verbeek (2013), *Short-term residual reversal*, Journal of Financial Markets 16(3) (cité de mémoire, non consulté en ligne aujourd'hui).
- S. Nagel (2012), *Evaporating Liquidity*, RFS : https://www.nber.org/papers/w17653
- N. A. Kitron, J. M. Wengrowicz (2026), arXiv:2608.21888 : https://arxiv.org/abs/2608.21888
- Fairfield University, *Cryptocurrency return reversals* (reversal plus fort sur les petites capitalisations peu liquides) : https://fairfield.elsevierpure.com/en/publications/cryptocurrency-return-reversals/
- Internes : `docs/research_plan_status.md` Exp 40, 41, 48 ; `quant_bot/features/build.py`.
