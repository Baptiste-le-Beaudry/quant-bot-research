# H-R17 — Réussir un funded futures puis toucher des payouts : mathématiques, pratique, stratégie optimale (T-061)

- **Agent :** Chercheur. **Date :** 2026-10-10. **Branche :** `research/funded-optimal` (depuis `agents/orchestration-20261006`, commit ff9caa9).
- **Statut :** recherche et calculs **exploratoires, ils ne comptent pas**. Aucun test décisionnel, aucun compte ouvert, aucun achat.
- **Scripts :** `docs/agents/research/H-R17_scripts/` (sorties CSV dans `outputs/`).
- **Données :** trades et séries quotidiennes de l'Exp 64 (P1) et de l'Exp 65 (H), plus le fichier Dukascopy USATECH 1 min en lecture seule pour reconstruire la trajectoire minute de chaque jour. Le HOLDOUT positionnel des indices est **déjà consommé** (Exp 65) : tout chiffre MNQ ci-dessous est **en échantillon** au sens strict (les deux fenêtres ont déjà été vues).
- **Sources** consultées le 2026-10-10 (§9). « Non vérifié » = lu seulement sur une source secondaire.

## Réponse courte

1. **L'argument « si personne ne réussissait, les funded ne seraient pas rentables » est vrai dans les faits, mais il ne prouve pas qu'il existe une compétence à acheter.**
   - Topstep publie pour 2025 : 16,8 % des Combines réussis, 51,8 % des participants passent au moins une fois, 33,3 % des financés touchent au moins un payout [S10]. FPFX (300 000 comptes) : 7 % des traders touchent un payout, en moyenne 4 % de la taille du compte, après ≈ 800 USD de frais [S11].
   - **Ce sont presque exactement les chiffres que donne le hasard** : la théorie de la barrière donne 22 % de passage à edge nul (exp(−T/D)), et notre simulation à edge nul donne 8-17 % de passage et 18-49 % de payout chez les financés.
   - Les firmes rendent ≈ **20 à 55 cents par dollar** de frais (FPFX, comptes FTMO).
2. **Mathématiques.**
   - Passer, c'est atteindre T avant un drawdown trailing D. La taille optimale maximise μ/σ² : **prudente si l'edge est positif, audacieuse s'il est négatif** (Pestien-Sudderth 1985).
   - **À edge nul, on perd**, quelle que soit la taille : −27 à −100 pour 100 USD avec la forme réelle des jours MNQ. Avec une forme symétrique, c'est ≈ 0 à +37 chez Topstep, non significatif.
   - La « convexité gratuite » du modèle gaussien existe sur le papier, mais les vraies queues et la **règle de cohérence** (qui vise les profils à queue droite comme la zone de bruit) la mangent.
3. **Zone de bruit MNQ (Exp 65), à l'échelle actuelle du Nasdaq :** sa meilleure configuration est **Lucid Flex 50K, 1 micro, sans stop journalier, achetée en promotion**.
   - Edge mesuré : **+161 USD pour 100 USD dépensés** sur 1 an (5 tentatives, P(≥ 1 payout) 0,41).
   - Demi-edge : **≈ 0** (+10 à +17).
   - Edge nul : **−61 à −65**.
   - Chez Topstep : 3 micros pendant l'évaluation, 1 micro une fois financé (+105 / +16 / −49 pour 100 USD).
   - **Un compte plus grand n'aide pas** (T/D = 2 et 300-465 jours à 1 micro).
   - **Un stop journalier détruit 76-92 % de l'edge.**
4. **Verdict : pas de marge de sécurité.** Le point mort est à la moitié de l'edge mesuré, et cet edge repose sur 5 jours et sur un HOLDOUT consommé.
   - Prévoir 4-5 tentatives sur 2 ans (≈ 360-450 USD avec remise) pour ≈ 70 % de chances d'au moins un payout, **si** l'edge est réel.
   - **Ne rien acheter maintenant.** Préenregistrement proposé (§7) : la même règle gelée sur le Dow (MYM) et le Russell 2000 (M2K), jamais chargés. Si elle échoue, fermer la piste.

## 0. Anti-doublon (lu avant de calculer)

| Travail existant | Ce qu'il a établi | Ce que H-R17 ajoute |
|---|---|---|
| T-050, `venues/FUNDED_FUTURES_2026-10-08.md` + `funded_futures_ev_sim.py` | Règles Topstep/Lucid/…, coût AR MNQ 2,22 USD ; modèle **gaussien** : edge nul ≈ +33 USD sur 3 essais Topstep 50K | Règles **relues le 2026-10-10** (Topstep a changé ses payouts le 2026-04-28 ; Lucid Flex détaillé) ; série **réelle** MNQ avec trajectoire minute ; théorie de la barrière ; politique de taille ; statistiques publiées |
| T-017 (`risk/t017`, `results/T-017_2026-10-06.md`) | Propr crypto : 0/352 cas positifs à 12 mois ; **le témoin à edge nul est négatif dans 176/176 cas** (la convexité ne paie pas les réessais) | La même conclusion est retrouvée sur les futures, et expliquée (§2.4) |
| Exp 64 / 65 / 70 | Zone de bruit MNQ : Sharpe net 0,97 (P1, en échantillon), 0,81 (H, HOLDOUT unique) ; MaxDD −3 949 USD ; 5 meilleurs jours > 100 % du net ; filtre GEX REJET | Effet de ce profil (queue droite) sur la règle de cohérence et sur la barrière ; compte plus grand ; stop journalier ; taille ciblée en volatilité |
| H-R15 (§3.2-3.3) / Exp 68-69 | Propr + tendance crypto : Exp 68 REJET, Exp 69 tombée | Rien de rouvert |
| H-R16 (§3.4, `mnq_stop_prob.py`) | MNQ sur capital propre : P(DD > 2 000 USD en 1 an) = 0,66 avec l'edge mesuré | Même série, mais sous les règles funded complètes, avec les frais |
| `research_plan_status.md` « Funded-account backtests » (2026-10-05) | Propr/Darwinex : chiffres invalides (sortie au stop) | Non repris |
| REPRISE §3 « rejeté » | « Exp 64-65 indices funded (MaxDD) », « levier/funded (T-017) » | **Risque de doublon : élevé.** H-R17 ne rouvre pas ces rejets sans raison nouvelle ; il chiffre ce qui reste possible et pourquoi |

Compteur de variantes de ce document : §8.

## 1. Règles retenues (lues le 2026-10-10)

| | Topstep 50K / 100K / 150K | Lucid Flex 50K / 100K / 150K |
|---|---|---|
| Prix | **49 / 99 / 149 USD par mois** (Standard) + activation **149 USD** au passage ; ou 95 / 149 / 229 USD par mois sans activation [S3, S4 non vérifié] ; API ProjectX 14,50 USD/mois [T-050] | **150 / 293 / 407 USD une fois** (catalogue), remises de 30-50 % fréquentes [S7, S8 non vérifié] ; pas d'activation ; API : **non vérifiée** (NinjaTrader/Rithmic) |
| Objectif / MLL | 3 000 / 6 000 / 9 000 ; MLL **trailing fin de journée** 2 000 / 3 000 / 4 500, contrôlé en temps réel, verrouillé au solde de départ [S2, T-050] | Idem, verrou à +100 USD [S6] |
| Cohérence (évaluation) | meilleur jour ≤ 50 % du profit total (sinon l'objectif monte) [S5] | 50 % [S6] |
| Jours minimum | 2 | 2 |
| Taille max | 50 / 100 / 150 micros | 40 / 60 / 100 micros |
| Compte financé | solde 0, MLL −D trailing verrouillé à 0 ; **après un payout, MLL = 0 pour toujours** [S1] | MLL −D trailing verrouillé à +100 ; après un payout, MLL verrouillé à +100 [S6] |
| Payout | 5 jours ≥ 150 USD ; 50 % du solde, plafond **2 000 / 3 000 / 5 000** (chemin Standard, depuis le 2026-04-28) ; min 125 ; 90 % [S1, S2] | 5 jours ≥ 150 / 200 / 250 USD ; 50 % du profit, plafond **2 000 / 2 500 / 3 000**, min 500 ; 90 % ; 5 payouts puis « live » [S6] |
| Comptes simultanés | 5 [S9 non vérifié] | 5 par foyer [S9 non vérifié] |
| Bots | permis via ProjectX, depuis le PC personnel seulement [T-050] | permis [T-050] |

Propr (crypto, 1-Step 10K, 110 USD) : objectif +10 %, DD **statique** 6 %, perte journalière 3 %, payout 80 % en balayant le profit (H-R15 §3.2). Non resimulé ici : T-017 l'a fait avec les trades réels (§0).

**Non modélisé :** la limite journalière optionnelle de Topstep (qui double les plafonds de payout), les comptes « live » (Topstep : 0,71 % des traders XFA y sont appelés [S1]), le plan de mise à l'échelle XFA (sans effet pour ≤ 20 micros), les promotions.

## 2. Les mathématiques du passage

### 2.1 Le problème de barrière (théorie)

- Avec un PnL brownien de dérive μ et de volatilité σ par jour, et un drawdown **trailing** D, le maximum atteint avant le premier drawdown de D suit une loi exponentielle (Taylor 1975 ; Lehoczky 1977). D'où :
  - **P(atteindre T avant le drawdown trailing D) = exp(−T / m)**, avec m = (e^{aD} − 1)/a et a = 2μ/σ² ;
  - **edge nul : P = exp(−T/D)**, quelle que soit la taille. Soit **22 %** pour T/D = 1,5 (tous les comptes 50K : 3 000/2 000) et **13,5 %** pour T/D = 2 (Topstep/Lucid 100K et 150K).
  - Un DD **statique** (Propr) donne D/(T+D) à edge nul : 37,5 % pour Propr 1-Step (6 % contre 10 %). Le trailing coûte donc beaucoup.
- **Quand on choisit la taille k**, dérive et variance deviennent kμ et k²σ². Pestien et Sudderth (1985) montrent que pour maximiser la probabilité d'atteindre un but, il faut maximiser μ/σ² à chaque instant. Ici μ/σ² = μ₁/(kσ₁²) :
  - **edge positif → jeu prudent** (la plus petite taille possible) ;
  - **edge négatif (coûts, edge nul net) → jeu audacieux** (la plus grande taille), comme le « bold play » de Dubins et Savage.
  - Avec une échéance ou un coût par mois, le jeu prudent devient trop lent : Browne (1999) montre que l'optimum à échéance fixe revient à acheter une option digitale, de plus en plus agressive à l'approche de l'échéance.
- **Ce qu'il faut pour « réussir souvent » :** l'exposant aD = 2 × (μ/σ) × (D/σ) doit être grand. Avec le MNQ remis au niveau actuel du Nasdaq (μ₁ = +19,35 USD/jour, σ₁ = 340 USD/jour, Exp 65 H), D/σ₁ = 5,9 sur un 50K à 1 contrat et aD = 0,67 seulement. Il faudrait un Sharpe journalier ≈ 0,25 (≈ 4 annualisé) pour que aD ≈ 3.

`theory_table.py` (brownien, trailing continu, sans verrou ni cohérence) :

| Compte (T/D) | k MNQ | P(edge mesuré) | P(demi-edge) | P(edge brut nul) | Jours attendus (edge mesuré) |
|---|---|---|---|---|---|
| 50K (3 000/2 000) | 1 | 0,35 | 0,28 | 0,21 | 155 |
| | 3 | 0,26 | 0,24 | 0,22 | 52 |
| | 10 | 0,23 | 0,23 | 0,22 | 16 |
| 100K (6 000/3 000) | 1 | 0,31 | 0,21 | 0,12 | 310 |
| 150K (9 000/4 500) | 1 | 0,42 | 0,26 | 0,12 | 465 |
| | 3 | 0,21 | 0,17 | 0,13 | 155 |

**Lecture :** même avec l'edge mesuré, la meilleure probabilité de passage est 35-42 %, et seulement à 1 contrat, en 7 à 22 mois. Le compte plus grand « absorbe » mieux le drawdown (D/σ₁ = 13 sur 150K), mais il faut 465 jours de bourse en moyenne pour gagner 9 000 USD à 1 MNQ : chez Topstep, c'est 22 mois × 149 USD.

Contrôle du moteur (`check_engine.py`, brownien, sans verrou ni cohérence) : simulé 0,247 / 0,402 / 0,296 / 0,207 contre 0,223 / 0,383 / 0,259 / 0,190 pour la formule. L'écart (+2 à +4 points) vient de ce que le MLL ne remonte qu'en **fin de journée** : c'est plus clément qu'un trailing continu. Direction et ordre de grandeur conformes.

## 3. Simulation sur la série réelle MNQ (`funded_sim.py`)

### 3.1 Méthode

- **Trajectoires.** `build_paths.py` reconstruit, pour chacun des 3 335 jours évalués (P1 : 2 735 jours, 2012-02 → 2024-03 ; H : 600 jours, 2024-03 → 2026-08), la trajectoire minute du PnL d'un contrat MNQ :
  - réalisé + latent marqué au close, et au pire prix de la barre (low si long, high si court) pour le contrôle du MLL en temps réel ;
  - à partir des trades Exp 64/65 (moteur gelé, entrées et sorties à l'ouverture de la barre suivante, jamais au stop) ;
  - contrôle : le PnL de fin de journée reproduit le `net_usd` de l'Exp 64/65 **au centime près** sur les 3 335 jours.
- **Mise à l'échelle.** Les PnL bruts sont remis au niveau actuel du Nasdaq 100 (≈ 30 000) en proportion du prix du jour ; le coût de 2,22 USD par trade reste fixe. À cette échelle, 1 MNQ donne :
  - H (hors échantillon unique) : **+19,35 USD/jour, σ = 340 USD/jour, Sharpe ≈ 0,90** ;
  - P1 (en échantillon de l'article et de l'Exp 64) : +22,05 USD/jour, σ = 289, Sharpe ≈ 1,21 ;
  - pire creux intrajournalier : −1 242 USD (H), −2 606 USD (P1).
- **Scénarios d'edge** (décalage de la moyenne sur les jours tradés, forme des jours conservée) : mesuré, demi-edge, **edge brut nul** (net = −coûts), P1, P1+H.
- **Bootstrap** par blocs de 20 séances, 3 000 parcours par case, **horizon 1 an de bourse** depuis le premier achat. Après un échec, ou après la mort du compte financé, on rachète une évaluation tant que le nombre de tentatives le permet (1 ou 5).
- **Taille.** Fixe (1, 2, 3, 5, 10 micros), ou « coussin » : k = ⌊(solde − MLL) / (c · σ₁)⌋ avec c = 4 ou 8, au moins 1 (version discrète de Grossman-Zhou : exposition proportionnelle à la distance à la barrière).
- **Payout Topstep :** on attend que le MLL soit verrouillé (solde ≥ D) avant de retirer (variante sans attente au §3.3).
- **Espérance** = payouts reçus (90 %) − tous les frais. « Pour 100 USD » = espérance / frais moyens × 100.

### 3.2 Résultats principaux (504 cases, toutes dans `outputs/grid_main.csv`)

Sélection : pour chaque scénario, le compte Lucid Flex 50K à 1 micro (la meilleure case robuste), la meilleure case Topstep, et les comptes plus grands. **Erreur type Monte Carlo : ± 10 à 60 USD** selon la case (colonne `ev_se`).

| Scénario (1 MNQ ≈) | Firme, compte, taille, tentatives | P(passer) par tentative | P(≥ 1 payout) | Frais moyens | Payouts moyens | **Espérance (USD)** | **Pour 100 USD** | P(perte) |
|---|---|---|---|---|---|---|---|---|
| **H mesuré** (Sharpe 0,90) | Lucid 50K, 1 micro, **1 tentative** | 0,37 | 0,22 | 150 | 376 | **+226** | **+150** | 0,78 |
| | Lucid 50K, 1 micro, 5 tentatives | 0,29 | 0,41 | 437 | 683 | +247 | +56 | 0,63 |
| | Lucid 50K, coussin c=4, 5 tentatives | 0,30 | 0,44 | 466 | 735 | +268 | +58 | 0,61 |
| | Topstep 50K, 1 micro, 1 tentative | 0,37 | 0,17 | 374 | 473 | +99 | +27 | 0,83 |
| | Topstep 50K, 5 micros, 5 tentatives | 0,15 | 0,14 | 498 | 927 | +429 ± 60 | +86 | 0,86 |
| | Topstep 150K, 10 micros, 5 tentatives | 0,14 | 0,13 | 1 090 | 1 717 | +627 ± 126 | +58 | 0,87 |
| | Lucid 100K / 150K, 1 micro | 0,28 / 0,19 | 0,16 / 0,04 | 293 / 407 | — | −79 / −344 | −27 / −85 | > 0,84 |
| **H demi-edge** (Sharpe 0,45) | Lucid 50K, 1 micro, 1 tentative | 0,20 | 0,09 | 150 | 137 | **−13** | −9 | 0,91 |
| | Lucid 50K, coussin c=4, 1 tentative | 0,21 | 0,10 | 150 | 149 | −1 | −1 | 0,90 |
| | Topstep 50K, 5 micros, 5 tentatives | 0,10 | 0,07 | 450 | 343 | −107 | −24 | 0,93 |
| **H edge brut nul** | Lucid 50K, 1 micro, 1 tentative | 0,08 | 0,03 | 150 | 33 | **−118** | −78 | 0,97 |
| | Topstep 50K, 3 micros, 5 tentatives | 0,09 | 0,07 | 462 | 158 | −305 | −66 | 0,93 |
| | meilleure case des 84 | — | — | — | — | −55 | −63 à −98 | ≥ 0,93 |
| **P1** (en échantillon, Sharpe 1,21) | Lucid 50K, 1 micro, 1 tentative | 0,58 | 0,43 | 150 | 708 | +558 | +372 | 0,57 |
| | Lucid 50K, 1 micro, 5 tentatives | 0,44 | 0,71 | 446 | 1 292 | +846 | +190 | 0,36 |
| | Topstep 50K, 3 micros, 5 tentatives | 0,33 | 0,40 | 725 | 2 277 | +1 552 | +214 | 0,61 |
| | Topstep 150K, 5 micros, 5 tentatives | 0,35 | 0,51 | 1 682 | 5 198 | +3 516 | +209 | 0,50 |

| **P1+H** (tout, Sharpe ≈ 1,1) | Lucid 50K, 1 micro, 1 / 5 tentatives | 0,53 / 0,40 | 0,37 / 0,63 | 150 / 439 | 672 / 1 164 | +522 / +725 | +348 / +165 | 0,63 / 0,43 |
| **P1+H edge brut nul** | Lucid 50K, 1 micro, 1 tentative | 0,17 | 0,08 | 150 | 100 | −50 | −33 | 0,92 |
| | meilleure case des 84 | — | — | — | — | −28 (Topstep 50K, 3 micros, 1 tentative) | −27 à −100 | ≥ 0,92 |

Résumé par scénario (`summarize.py`) :

| Scénario | Cases avec espérance > 2 erreurs types | Plage « pour 100 USD » |
|---|---|---|
| H mesuré | 20 / 84 | −93 à +159 |
| H demi-edge | **0 / 84** | −97 à −1 |
| H edge brut nul | **0 / 84** | −98 à −63 |
| P1 | 61 / 84 | −96 à +372 |
| P1+H | 58 / 84 | −94 à +352 |
| P1+H edge brut nul | **0 / 84** | −100 à −27 |

Validation contre les chiffres publiés (edge brut nul) : P(passer) par tentative 8-17 % selon la forme des jours (Topstep publie 16,8 %) ; P(au moins un payout | financé) 18-49 % selon la firme et la forme (Topstep publie 33,3 %). **Le modèle « edge nul » reproduit l'ordre de grandeur des statistiques officielles.**

### 3.3 Ce que disent ces chiffres

Variantes de `funded_extra.py` (`outputs/grid_extra.csv`, 192 cases) et de `vol_target.py` :

| Question | Résultat (série H sauf mention) |
|---|---|
| **A. La « convexité gratuite » existe-t-elle ?** Brownien à edge brut nul, même σ | **Oui en théorie chez Topstep** : +434 à +836 USD (+55 à +97 pour 100 USD) avec 3-10 micros et 5 tentatives sur 50K-150K. Lucid : −13 à +71 sur 50K, négatif au-delà |
| … et avec la vraie forme des jours MNQ à edge brut nul ? | **Non : négatif dans les 168 cases** (H et P1+H), −27 à −100 pour 100 USD |
| A2. Pourquoi ? (Lucid 50K, 1 micro, 1 tentative) | P(passer) brownien 0,24 ; réel sans règle de cohérence 0,14 ; réel avec cohérence 0,08. La **règle de cohérence** coûte ≈ 40 % des passages ; le reste vient de la forme des jours (queue droite, séries de pertes groupées) |
| **Témoin à forme symétrique** (`build_bh_paths.py`, `funded_bh.py`, `outputs/grid_bh.csv`, 160 cases) : 1 MNQ acheté, ou vendu, de 09:30 à 15:59 tous les jours, P1+H, ramené à edge brut nul (σ₁ = 621 USD) | **Topstep : ≈ 0 à légèrement positif**, +58 à +369 USD (+10 à +37 pour 100 USD, à 1-3 erreurs types) avec 1-2 micros sur 50K ou 3-5 sur 150K et 5 tentatives. Le brownien de même σ donne +421 à +989 (+84 à +100 pour 100 USD) : **les vraies queues mangent 60-90 % de la convexité**. Lucid : négatif partout (−22 à −83 pour 100 USD) |
| **B. « Évaluation audacieuse, financé prudent »** | **Topstep 50K, 3 micros puis 1 : +627** (3 puis 3 : +312 ; 1 puis 1 : −50). Demi-edge : +85 (contre −113). Edge nul : −233 (contre −305). **Lucid 50K : aucun gain** (+204 contre +247) : sans frais mensuels, la vitesse ne vaut rien |
| **C. Stop journalier intégré** (−250 / −400 / −600 USD par contrat, sortie à la barre suivante) | Il **détruit 76 à 92 % de l'edge** : +19,4 → +3,7 / +4,6 / +1,6 USD/jour. Lucid 50K, 5 tentatives : +247 → −213 à −281. Les gros jours de tendance commencent souvent par une perte |
| **Taille ciblée en volatilité** (l'article, en contrats entiers) | Sharpe inchangé (H 0,90 → 0,90 ; P1 1,21 → 1,18), MaxDD plus profond (−5 069 → −6 187 USD), espérance inchangée (+247 → +250) |
| **D. Horizon 2 ans** (Lucid 50K, 1 micro, 5 tentatives) | Mesuré : **+876**, P(≥ 1 payout) 0,70, **médiane +35** ; demi-edge : −1 ; edge nul : −486 |
| **E. Remise Lucid de 40 %** (50K, 1 micro, 5 tentatives) | Mesuré : **+421 (+161 pour 100 USD)** ; demi-edge : **+29 à +56 ± 18-20** (+10 à +17 pour 100 USD) ; edge nul : −233 |
| F. Topstep sans activation | Toujours pire que le parcours Standard (50K, 3 micros : +152 contre +312) |
| G. Payout Topstep sans attendre le verrou du MLL | Égal sur 50K (+316 contre +312), pire sur 150K (+72 contre +222) |

**Lecture :**
1. **Edge nul : on ne gagne pas d'argent qui compte.** Avec la forme « queue droite » de la zone de bruit, l'espérance est négative partout (−27 à −100 pour 100 USD). Avec une forme symétrique (achat ou vente sur la séance), elle est ≈ 0 à +37 pour 100 USD chez Topstep seulement, à 1-3 erreurs types, en échantillon, et P(perte) reste ≥ 75 %. La « convexité gratuite » du modèle gaussien de T-050 est réelle en théorie, mais les vraies queues en mangent 60-90 % et la règle de cohérence vise précisément les profils à queue droite. Il suffit d'un coût ou d'un comportement légèrement négatif (surtrading, revanche) pour passer sous zéro. C'est la même conclusion que T-017 pour Propr.
2. **Taille.** Chez Lucid (frais unique), le jeu prudent (1 micro, ou taille proportionnelle au coussin) est le meilleur par dollar, comme le prédit Pestien-Sudderth. Chez Topstep (frais mensuels), la lenteur coûte : il vaut mieux 3 micros pendant l'évaluation, puis 1 micro une fois financé. Au-delà de 5 micros sur 50K, c'est une loterie (P(payout) ≤ 14 %) **moins bonne que l'edge nul théorique**.
3. **Un compte plus grand n'aide pas.** 100K et 150K ont T/D = 2 au lieu de 1,5, coûtent 2-3 fois plus cher et demandent 300-465 jours à 1 micro. Même sur 2 ans, Lucid 150K (2 micros) rapporte +382 contre +876 pour le 50K.
4. **Réessais.** Ils augmentent P(≥ 1 payout) (Lucid 50K : 0,22 → 0,41 sur 1 an, 0,70 sur 2 ans) mais diminuent l'espérance par dollar (+150 → +56 pour 100 USD), car chaque nouvelle tentative a moins de temps devant elle.
5. **Tout dépend de l'edge réel.** Lucid 50K, 1 micro, une tentative : +558 (P1), +226 (H), −13 (demi-edge), −118 (edge nul). **Le point mort est à ≈ la moitié de l'edge mesuré en H, soit un Sharpe net ≈ 0,45-0,5** à l'échelle actuelle (≈ 0,4 avec une remise de 40 %). Or, sans ses 5 meilleurs jours, la série H a un Sharpe de −0,10.

## 4. Qui réussit, et comment ? (statistiques publiées, pratique, critique)

### 4.1 Les seuls chiffres vérifiables

| Source | Chiffre | Qualité |
|---|---|---|
| **Topstep, page officielle, année 2025** [S10] | 16,8 % des Combines lancés réussis ; **51,8 %** des participants passent au moins une fois ; **33,3 %** des participants financés reçoivent au moins un payout ; 0,71 % des traders XFA appelés en « live » ; 99,26 % des demandes de payout approuvées ; 1,5 G USD versés depuis l'origine, 750 000+ traders | officiel, mais dénominateurs différents (tentatives, personnes) |
| **FPFX Tech** (fournisseur de 10 firmes, 300 000 comptes, 100 000 traders), Finance Magnates, 2024-09-18 [S11] | 14 % passent ; 45 % d'entre eux touchent un payout, soit **7 % des traders** ; payout moyen ≈ **4 % de la taille du compte** ; **≈ 800 USD dépensés par trader sur ≈ 3 challenges** ; 2,2 firmes par trader | données de plateforme, mais citées par un journaliste ; firmes surtout CFD/forex |
| **FTMO** (comptes 2024, Finance Magnates) [S12] | chiffre d'affaires 329 M USD, bénéfice net 62,5 M USD ; récompenses ≈ 15 M USD/mois (sept. 2025) ; 450 M USD versés en 10 ans | officiel (comptes), pas de taux de réussite publié |
| The Funded Trader (PDG, Finance Magnates) [S13] | 5-10 % passent, 20 % des financés payés, 1-2 % des clients au total | déclaration, firme ensuite en défaut de paiement partiel |
| Chague, De-Losso, Giovannetti (2019), 19 646 day traders du mini-Ibovespa [S14] | parmi ceux qui ont persisté plus de 300 jours, **97 % ont perdu** ; 1,1 % ont gagné plus que le salaire minimum ; aucun apprentissage | académique, marché réel |
| Barber, Lee, Liu, Odean (2014), Taïwan [S15] | moins de 1 % des day traders sont rentables de façon prévisible après frais | académique (non relu aujourd'hui) |

**Calculs dérivés (approximatifs) :**
- Topstep : 0,518 × 0,333 ≈ **17 % des participants** touchent au moins un payout. Si chaque Combine réussit avec 16,8 %, 51,8 % de personnes « passées » correspond à ≈ 4 tentatives par personne en moyenne.
- FPFX : 7 % × 4 % × (50 000 à 100 000 USD) ≈ **140 à 280 USD de payouts attendus par trader, contre 800 USD dépensés**, soit **≈ 0,2 à 0,35 USD rendus par dollar**.
- FTMO : ≈ 180 M USD/an de récompenses pour un chiffre d'affaires de 330 M USD (2024) et plus en 2025 : **≈ 0,4 à 0,55 USD rendus par dollar**.

### 4.2 L'argument de l'auteur, vérifié

« Si personne ne réussissait, les funded ne seraient pas rentables. »

- **Vrai dans les faits :** une minorité touche des payouts (≈ 7 % chez FPFX, ≈ 17 % des participants chez Topstep), et ce sont parfois de vraies sommes (1,5 G USD versés par Topstep).
- **Faux comme preuve de compétence.** Les chiffres publiés sont **ceux que produit le hasard** :
  - à edge nul, la théorie donne 22 % de passage par tentative sur un 50K et 13,5 % sur 100K/150K. Topstep publie 16,8 %, au milieu ;
  - dans notre simulation à edge brut nul avec la vraie forme des jours MNQ (§3), **8 à 17 % des tentatives passent et 18 à 49 % des comptes financés touchent au moins un payout**. Topstep publie 16,8 % et 33,3 % ;
  - avec ≈ 4 tentatives, 1 − (1 − 0,17)⁴ ≈ 52 % des personnes passent au moins une fois. Topstep publie 51,8 %.

  Les chiffres officiels sont donc compatibles avec une population dont **l'edge moyen est à peu près nul**. Ils ne disent pas que les gagnants ont un edge ; ils ne disent pas non plus qu'aucun n'en a.
- **Pourquoi la firme gagne quand même avec des traders à edge nul :** la perte maximale de la firme par compte financé est bornée par le coussin D, et les règles en extraient une partie avant tout payout :
  - **identité de martingale** : à edge nul et à horizon infini, l'espérance des retraits bruts d'un compte financé vaut exactement l'espérance de −(solde à la mort du compte). Chez Topstep, ce solde vaut −D si le compte meurt avant de verrouiller son MLL, et 0 ensuite. Donc **E[retraits] ≤ D × P(mourir avant le verrou) ≈ 2 000 × (1 − e⁻¹) ≈ 1 260 USD** sur un 50K, avant la part de 90 %, les plafonds et l'horizon ;
  - multiplié par P(passer) ≈ 0,2, cela fait **≈ 230 USD de payouts attendus par tentative au mieux, contre 50 à 150 USD de frais par tentative** : le jeu à edge nul est à peu près équitable en théorie (T-050 : +33 USD) ;
  - en pratique, la règle de cohérence, les 5 jours gagnants, le retrait limité à 50 %, le MLL remis à 0 après un payout, les frais mensuels et les **coûts de transaction** font passer l'espérance sous zéro. C'est ce que mesure le §3 avec la vraie forme des jours MNQ.
  - Les comptes publiés le confirment : la firme rend **20 à 55 cents par dollar** encaissé.

### 4.3 Ce que font ceux qui touchent des payouts (pratique, à lire avec méfiance)

- **Aucune source publique ne compare les styles des gagnants et des perdants** avec des données (l'article FPFX le dit explicitement [S11]). Les études de cas des firmes (blog FTMO « Traders Analysis » [S16]) sont du marketing de survivants : un trader à 32 % de réussite et R/R 4,9, un autre à 42 % avec R/R 3,5. On ne peut pas en tirer de règle.
- **Ce que les règles favorisent mécaniquement** (déduit des règles, vérifiable dans notre simulateur) :
  - un profil à **gains fréquents et petits** : il satisfait la cohérence (meilleur jour ≤ 50 % du total) et accumule vite les 5 jours ≥ 150 USD ;
  - une **petite taille par rapport au coussin** une fois financé : le compte financé vaut par son coussin, qu'il ne faut pas brûler ;
  - un **profil à queue droite** (quelques gros jours, comme la zone de bruit MNQ) est **pénalisé deux fois** : la cohérence relève l'objectif après chaque gros jour, et les jours gagnants ≥ 150 USD sont rares.
- **Pratiques répandues sur Reddit et les forums** (non académique, non vérifié ; recherche web, les pages Reddit elles-mêmes refusent les robots) :
  1. **« Évaluation en loterie, compte financé prudent »** : grosse taille pour passer vite et payer peu de mois, puis 1-2 micros une fois financé. C'est cohérent avec la théorie du §2.1 (audacieux si l'edge est ≤ 0, prudent si on protège un actif). Testé au §3.3.
  2. **Acheter pendant les promotions** (−40 à −90 %) et **copier le même signal sur 5 comptes** : ne change pas l'espérance par dollar, sauf la remise, mais multiplie la variance.
  3. **Retirer le plus tôt possible.** Chez Topstep, c'est souvent une erreur depuis que le MLL passe à 0 après le premier payout (testé §3.3).
  4. **Couvrir un compte par un autre** (long chez une firme, court chez l'autre) : **interdit** par toutes les CGU lues (« hedging across accounts »). Je ne le propose pas.
- **Conclusion critique :** les « styles qui touchent des payouts » sont surtout ceux qui **survivent aux règles**, pas ceux qui ont un edge. Avec ≈ 17 % de participants payés chez Topstep et ≈ 7 % chez FPFX, on attend des milliers de gagnants par pur hasard. Les témoignages ne permettent pas de les distinguer des chanceux.

## 5. Stratégies candidates adaptées aux règles

Critère : gains réguliers, queue gauche contrôlée, coût faible, bot possible chez Topstep ou Lucid (CME, aplati avant 16:10-16:45 ET), données locales. Espérance « pour 100 USD » sur la meilleure configuration réaliste (Lucid 50K, 1 micro, 5 tentatives, ou Topstep 50K 3 → 1 micro), horizon 1 an.

| # | Candidate | Mécanisme et preuves | Déjà rejetée chez nous ? | Données locales | Espérance estimée (pour 100 USD) |
|---|---|---|---|---|---|
| K1 | **Zone de bruit MNQ, 1 micro, sans stop journalier** | Momentum intrajournalier (Zarattini-Aziz-Barbon 2024) ; Exp 65 : Sharpe net 0,81 sur le HOLDOUT unique (0,90 à l'échelle actuelle). Queue droite : sans les 5 meilleurs jours, Sharpe −0,10. Échec sur MES | Rejetée **comme compte funded sur un critère MaxDD déterministe** (Exp 65 : −3 949 > −2 000 USD). Le critère pertinent, l'espérance sous les règles, n'avait jamais été calculé. **Doublon partiel assumé** | USATECH 1 min, HOLDOUT consommé : plus aucun test propre sur ce fichier | edge mesuré : **+56 (Lucid prix catalogue) à +161 (Lucid −40 %)** ; demi-edge : −34 à +17 ; nul : −61 à −79 |
| K2 | K1 + **évaluation à 3 micros, financé à 1 micro** (Topstep) | Pestien-Sudderth avec un coût du temps ; pratique Reddit | Non | idem | mesuré **+105** ; demi-edge +16 ; nul −49 |
| K3 | K1 + **stop journalier** (−250 à −600 USD/contrat) | Couper la queue gauche du jour | Non, mais l'Exp 52 (queue crypto) et T-017 vont dans le même sens | idem | **pire que K1** : 76-92 % de l'edge perdu ; Lucid −43 à −53 |
| K4 | K1 + **taille ciblée en volatilité** (règle de l'article) | Volatilité constante en USD | Non | idem | identique à K1 (Sharpe inchangé, MaxDD plus profond) : **sans intérêt** |
| K5 | **Panier MNQ + MYM + M2K** (zone de bruit sur trois micros) | Diversifier la même règle : si les jambes sont peu corrélées, σ relatif au coussin baisse et aD monte (§2.1) | Jamais testé (Dow et Russell jamais chargés) ; **MES a échoué** à cause des coûts | Non : téléchargement Dukascopy nécessaire (§7) | inconnue ; **c'est le seul test qui peut faire bouger la décision** (§7) |
| K6 | **Loterie symétrique à edge nul** (achat ou vente sur la séance, 1-2 micros), Topstep | Convexité de l'option funded (§2, §4.2) | T-017 l'a rejetée pour Propr ; T-050 l'estimait ≈ 0 | USATECH (forme réelle) | **≈ 0 à +37** chez Topstep, non significatif, en échantillon ; négatif chez Lucid. **Je ne la recommande pas** : P(perte) ≥ 75 %, et un edge réel légèrement négatif suffit à la rendre perdante |
| K7 | **Retour à la moyenne intrajournalier à fort taux de réussite** (retour vers le VWAP dans la zone de bruit, comblement de gap) | Profil favorisé par la cohérence et par les 5 jours ≥ 150 USD | Proches parents rejetés : stratégie C (renversement QQQ/SPY de signe opposé), ORB BI1-BI3 plat, Gao −0,22 | SP500/USATECH (HOLDOUT consommé) | **aucune preuve d'edge**, donc espérance de l'edge nul (≈ −30 à −80). Non proposée |
| K8 | **Crypto Propr** (stratégie A, sortie au temps) | DD statique : P(passer) à edge nul = 37,5 % au lieu de 22 % | **Oui** : T-017, 0/352 cases positives à 12 mois ; Exp 68/69 pour la tendance | cache Binance | négative (T-017). Non rouverte |
| K9 | K1 combinée à une jambe « vendeuse de volatilité » pour lisser | Corrélation négative avec le MNQ convexe | Pas de jambe à edge positif disponible (puts : H-R16 ; pas d'options chez Topstep/Lucid) | — | non réalisable |

Combien coûte un plafond de perte intégré à la règle MNQ ? Mesuré sur H, à l'échelle actuelle (variante C, `grid_extra.csv`) :

| Plafond par contrat | Net moyen / jour | σ / jour | Part de l'edge perdue | Espérance Lucid 50K, 1 micro, 5 tentatives |
|---|---|---|---|---|
| aucun | +19,35 | 340 | — | +247 |
| −600 USD | +1,62 | 265 | 92 % | −281 |
| −400 USD | +4,56 | 255 | 76 % | −213 |
| −250 USD | +3,74 | 229 | 81 % | −219 |

## 6. Verdict

**1. Meilleure combinaison par dollar dépensé (si l'edge MNQ est réel) :** Lucid Flex 50K, zone de bruit MNQ à **1 micro** (ou taille proportionnelle au coussin, c = 4), **sans stop journalier**, achetée **avec une remise**, **une tentative à la fois**, sur un horizon de 1 à 2 ans.
- Edge mesuré (H) : **+421 USD sur 1 an pour ≈ 262 USD dépensés (+161 pour 100 USD)**. P(≥ 1 payout) = 0,41, P(perte) = 0,59.
- Sur 2 ans au prix catalogue : +876 USD, P(≥ 1 payout) = 0,70, médiane +35 USD.
- Chez Topstep, la meilleure option est **3 micros pendant l'évaluation, puis 1 micro une fois financé** : +627 USD sur 1 an pour ≈ 598 USD de frais (+105 pour 100 USD).
  - Elle résiste un peu mieux à un demi-edge : +85 USD, contre +29 à +56 USD pour Lucid avec remise.
  - Elle exige l'ordinateur personnel allumé à chaque séance (pas de VPS).

**2. Est-ce positif avec une marge de sécurité ? Non.**
- Le point mort est à **≈ la moitié de l'edge mesuré**, soit un Sharpe net ≈ 0,45-0,5 à l'échelle actuelle.
  - Au demi-edge, l'espérance est ≈ 0 : Lucid −40 % donne +10 à +17 pour 100 USD, Topstep 3 → 1 donne +16.
  - À edge nul : −49 à −65 pour 100 USD.
- L'estimation de l'edge est fragile :
  - elle repose sur **600 jours**, dont 5 jours font plus de 100 % du net ;
  - le HOLDOUT est consommé ;
  - la règle a échoué sur MES ;
  - les anomalies publiées perdent typiquement une partie de leur rendement après publication.
- **Pondération personnelle**, à titre d'illustration (non mesurée) : 30 % edge plein, 30 % demi-edge, 40 % edge nul.
  - Calcul : 0,3 × 421 + 0,3 × 42 + 0,4 × (−233) ≈ **+46 USD pour ≈ 300 USD dépensés sur un an, soit ≈ +15 pour 100 USD**, avec P(perte) ≈ 0,75.
  - C'est **mince et à l'intérieur de l'incertitude** : ce n'est pas une marge de sécurité.
- Risques non modélisés :
  - écart entre le CFD Dukascopy et le MNQ réel (VWAP sur volume CFD, base, remplissages) ;
  - latence du PC personnel ;
  - changement des règles des firmes : Topstep a changé ses payouts trois fois en 2026 ;
  - refus de payout ;
  - fiscalité (revenu d'entreprise probable).

**3. Combien de tentatives prévoir ?**
- Si l'edge est réel :
  - P(passer) ≈ 0,29-0,37 par tentative, et P(au moins un payout | financé) ≈ 0,6 ;
  - avec 5 tentatives : P(≥ 1 payout) ≈ 0,41 sur 1 an et **≈ 0,70 sur 2 ans**.
- Budget pour 4-5 tentatives :
  - avec 40 % de remise (Lucid 50K à 90 USD) : **360-450 USD, soit ≈ 510-640 CAD**, à peu près tout le budget de 500 CAD ;
  - au prix catalogue (150 USD) : 5 tentatives coûtent 750 USD, au-dessus du budget.
- Si l'edge est nul : ces 4-5 tentatives donnent ≈ 10-15 % de chances d'un payout, et on perd en moyenne ≈ 65 % des frais.

**4. Recommandation :**
- **Ne rien acheter maintenant.**
- Exécuter d'abord le préenregistrement **Exp F2** (§7). C'est un test peu coûteux, qui peut confirmer ou infirmer l'edge sur deux indices jamais vus.
- **Si F2 passe :**
  1. panier de trois micros ;
  2. 3 mois de forward papier ;
  3. puis **une** tentative Lucid Flex 50K achetée en promotion, sur décision de l'auteur.
- **Si F2 échoue :** fermer la piste funded futures. Aucune autre candidate n'a de preuve, et l'edge nul est perdant.

## 7. Préenregistrement proposé (non exécuté) — Exp F2 : réplication indépendante de la zone de bruit sur le Dow (MYM) et le Russell 2000 (M2K)

**Pourquoi ce test et pas un autre.** Toute l'espérance funded positive repose sur un seul chiffre : l'edge de la zone de bruit MNQ (§3, §6). Il a été mesuré sur 1 indice sur 2 (MES a échoué), et le HOLDOUT est consommé. Le forward Exp 67 ne peut pas trancher : à 1 contrat, 6 mois donnent une erreur type de ≈ 1,4 sur le Sharpe annualisé. Le test le moins cher qui puisse **faire bouger la décision** est donc la même règle, gelée, sur deux indices américains **jamais chargés dans ce projet** et négociables chez Topstep et Lucid. Si elle échoue sur les deux, le résultat MNQ est probablement de la chance (1 indice sur 4) et la piste funded futures se ferme. Si elle réussit, la crédibilité de l'edge MNQ augmente, et un panier de trois micros réduit la variance relative au coussin D (§2.1).

- **Hypothèse.** La règle « zone de bruit » de l'Exp 64, **lecture figée au commit 33b5a15, sans aucun changement**, donne un Sharpe net ≥ 0,5 sur USA30 → MYM et sur USSC2000 → M2K.
- **Données.**
  - Dukascopy, API JSON (mémoire `dukascopy_data_access`) : `USA30.IDX-USD` (minutes depuis le 2013-09-30) et `USSC2000.IDX-USD` (minutes depuis le 2018-08-08), jusqu'au 2026-10-09.
  - Fichiers neufs : `data/indices/DOW30_1m.csv`, `data/indices/RUSSELL2000_1m.csv`. Avant tout calcul, vérifier par `grep` qu'aucun script du dépôt ne les a lus.
  - **Toute la série est un test unique** : pas de découpage TRAIN/HOLDOUT, puisque rien n'est réglé. Aucun regard sur les données avant le commit du script et de ses tests.
- **Étape 0 (bloquante).**
  - Mêmes contrôles de données que l'Exp 64 §2 : fuseau, étiquetage des barres, complétude RTH, volume CFD. Les règles d'éligibilité §3.6 sont reprises telles quelles.
  - Spécifications CME à relire sur cmegroup.com : MYM = 0,50 USD × indice, tick 1 pt = 0,50 USD ; M2K = 5 USD × indice, tick 0,1 = 0,50 USD.
  - REJET technique si moins de 1 000 jours éligibles pour MYM ou 800 pour M2K.
- **Moteur.** `scripts/agents/exp64_noise_momentum.py` inchangé. Seul ajout permis : deux entrées dans `INSTRUMENTS`, avec un test unitaire.
- **Exécution et coûts.** Ceux de l'Exp 64 : décision HH:00/HH:30 de 10:00 à 15:30 ET, exécution à l'ouverture de la barre suivante (jamais au niveau du stop), sortie à l'ouverture de la barre 15:59, 1 contrat. Coût AR = 1,22 USD de commission + 1 tick par côté, soit **2,22 USD** pour MYM et pour M2K.
- **Mesures.**
  - Sharpe net sur le PnL USD quotidien de tous les jours éligibles (0 sans trade) × √252, sur toute la période et sur la sous-fenêtre post-publication (2024-11-27 → fin).
  - MaxDD, pire jour, part du net venant des 5 meilleurs jours, résultats par année.
  - Part du brut mangée par les coûts.
- **Critères (sur chaque indice, toute la période).**
  - **PASS :** Sharpe net ≥ 0,5 sur MYM **et** sur M2K ; Sharpe net post-publication > 0 sur les deux ; au moins 200 jours tradés chacun.
  - **REJET :** Sharpe net ≤ 0,2 sur l'un des deux, **ou** Sharpe post-publication ≤ 0 sur les deux.
  - **INCERTAIN :** tout le reste.
- **Variantes : aucune.** Compteur de la famille « zone de bruit » : Exp 64 (2 variantes × 2 indices), Exp 65, Exp 70, puis 2 indices ici.
- **Si PASS** (étapes déjà fixées, sans nouveau choix) :
  1. Rejouer le panier MNQ + MYM + M2K, 1 contrat chacun, jours alignés par date, dans `H-R17_scripts/funded_sim.py` : Lucid Flex 50K et 150K, Topstep 50K, politiques fixed:1 et fixed:2, 1 et 5 tentatives.
  2. Étendre le forward papier Exp 67 aux deux micros pendant 3 mois.
  3. Ensuite seulement, proposer à l'auteur **un** achat Lucid Flex (§6).
- **Si REJET :** fermer définitivement la piste funded futures (aucun achat). Le forward Exp 67 reste un contrôle d'implémentation.
- **Si INCERTAIN :** aucun achat ; forward seulement.
- **Probabilité a priori de PASS : ≈ 10-15 %.** MES a échoué avec un brut correct parce que les coûts mangeaient 78 % du brut, et MYM a le même rapport coût/notionnel que MES (≈ 0,0097 %). M2K est deux fois plus cher (≈ 0,019 %). C'est un test **peu coûteux** (≈ 1 h de téléchargement, moteur existant) dont l'issue la plus probable est la fermeture de la piste. Il évite d'acheter des challenges sur un edge peut-être fortuit.

## 8. Compteur de variantes et limites

| Bloc | Cases |
|---|---|
| `grid_main.csv` : 6 scénarios × 2 firmes × 3 comptes × 7 politiques × 2 nombres de tentatives | 504 |
| `grid_extra.csv` : brownien (60), diagnostic de cohérence (12), évaluation audacieuse (72), stop journalier (12), horizon 2 ans (15), remise (9), sans activation (6), payout immédiat (6) | 192 |
| `vol_target.csv` | 12 |
| `grid_bh.csv` (témoin achat/vente sur la séance, et brownien de même σ) | 160 |
| `theory_table.py` (analytique) / `check_engine.py` | 45 / 4 |

≈ 870 configurations simulées. Les « meilleures cases » citées sont **sélectionnées** parmi elles : les plus hautes sont optimistes par construction. Toutes les cases sont dans les CSV.

**Limites :**
- **En échantillon.** Les fenêtres P1 et H ont été vues. H est le seul hors échantillon d'origine, et il est consommé.
- **Bootstrap de 600 jours (H) :** l'incertitude sur l'edge n'est pas propagée. Les erreurs types ne mesurent que le bruit Monte Carlo ; les scénarios « demi-edge » et « edge nul » servent à cela.
- **Règles simplifiées :**
  - plan de taille XFA, limite journalière optionnelle de Topstep, comptes « live » et inactivité non modélisés ;
  - Lucid arrêté après 5 payouts ;
  - frais Topstep comptés par mois entamé de chaque évaluation (un reset réel peut coûter autrement) ;
  - API Lucid comptée à 0 (**non vérifiée**).
- **Données :** VWAP calculé sur le volume CFD Dukascopy ; prix CFD à la place des futures ; 1 tick de glissement par côté ; mise à l'échelle linéaire au Nasdaq 30 000.
- **Règles relues sur des sources secondaires** pour les prix Topstep/Lucid et les règles Lucid (la page lucidtrading.com renvoie une erreur 403). Elles changent souvent.
- Rien n'a été écrit dans `data/`. Le fichier `outputs/mnq_paths.npz` (et `bh_*.npz`) est exclu par `.gitignore` ; il se régénère avec `build_paths.py` (et `build_bh_paths.py`) en 1-2 minutes.

## 9. Sources (consultées le 2026-10-10)

Règles et prix :
- [S1] Topstep, payouts XFA : https://intercom.help/topstep-llc/en/articles/8284233
- [S2] Topstep, règles de payout 2026 (secondaire) : https://proptradingvibes.com/blog/topstep-payout-rules
- [S3] Prix Topstep Standard / sans activation (secondaire) : https://curvedtrading.com/articles/en/reviews/topstep-review/ et https://tradingfunder.com/firms/topstep/
- [S4] Topstep, paramètres du Combine : https://help.topstep.com/topstep-llc/en/articles/8284197-trading-combine-parameters
- [S5] Topstep, cohérence (extrait de recherche) : https://intercom.help/topstep-llc/en/articles/8284208
- [S6] Lucid Flex, règles par taille (secondaire, 2026-10-09) : https://proptradingvibes.com/blog/lucid-trading-lucidflex-account
- [S7] Prix Lucid Flex (secondaire) : https://damnpropfirms.com/account-plans/lucid-trading-flex-50000/ et https://proptradingvibes.com/blog/lucid-trading-discount
- [S8] Lucid, plateformes (secondaire) : https://phidiaspropfirm.com/education/lucid-trading-explained ; automatisation : https://crosstrade.io/learn/prop-firm-ai-trading/lucid-trading
- [S9] Comptes simultanés (secondaire) : https://intercom.help/topstep-llc/en/articles/8284218 et https://proptradingvibes.com/blog/lucid-trading-multiple-accounts
- Règles Topstep/Lucid/Propr antérieures : `venues/FUNDED_FUTURES_2026-10-08.md` (T-050), `research/H-R15_nouvelles_strategies.md` §3.2.

Statistiques :
- [S10] **Topstep, page officielle** (année 2025, paiements cumulés) : https://www.topstep.com/topstep-prop
- [S11] FPFX Tech, Finance Magnates, 2024-09-18 : https://www.financemagnates.com/forex/exclusive-only-7-of-300000-prop-trading-accounts-achieved-payouts/
- [S12] Comptes FTMO 2024 : https://www.financemagnates.com/forex/ftmos-parent-netted-over-62-million-on-329m-revenue-in-2024/ ; analyse : https://www.tradeinformer.com/prop-weekly/what-ftmo-tells-us-about-prop-firm-finances
- [S13] The Funded Trader : https://www.financemagnates.com/forex/only-1-in-20-traders-pass-prop-firm-challenges-reports-the-funded-trader/
- [S14] Chague, De-Losso, Giovannetti (2019), « Day Trading for a Living? », SSRN 3423101 : https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101
- [S15] Barber, Lee, Liu, Odean (2014), « The cross-section of speculator skill: Evidence from day trading », Journal of Financial Markets 18, 1-24 (non relu aujourd'hui)
- [S16] FTMO, « Traders Analysis » (2023-01-20, études de cas) : https://ftmo.com/en/blog/ftmo-traders-analysis-less-is-sometimes-more/
- Agrégateurs (non académiques, non vérifiés) : https://traderssecondbrain.com/guides/prop-firm-pass-rate ; https://tradecovex.com/guides/how-many-combines-passed-express-topstep-2025 ; https://delphicalpha.substack.com/p/prop-firm-math-what-the-rules-actually

Théorie :
- Taylor (1975), « A stopped Brownian motion formula », Annals of Probability 3(2), 234-246.
- Lehoczky (1977), « Formulas for stopped diffusion processes with stopping times based on the maximum », Annals of Probability 5(4), 601-607.
- Dubins, Savage (1965), *How to Gamble If You Must* (jeu audacieux en jeu défavorable).
- Pestien, Sudderth (1985), « Continuous-time red and black: how to control a diffusion to a goal », Mathematics of Operations Research 10(4), 599-611 : https://pubsonline.informs.org/doi/10.1287/moor.10.4.599
- Grossman, Zhou (1993), « Optimal investment strategies for controlling drawdowns », Mathematical Finance 3(3), 241-276.
- Browne (1999), « Reaching goals by a deadline: digital options and continuous-time active portfolio management », Advances in Applied Probability 31, 551-577 : https://doi.org/10.1239/aap/1029955147
- Angoshtari, Bayraktar, Young (2015), « Optimal investment to minimize the probability of drawdown », arXiv:1506.00166.
- Zarattini, Aziz, Barbon (2024), « Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY) », SSRN 4824172 (lu pour l'Exp 64).
