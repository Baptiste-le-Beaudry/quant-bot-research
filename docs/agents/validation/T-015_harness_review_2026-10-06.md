# T-015 — Revue adversariale du harness d'exécution v1.0.0 (2026-10-06)

- **Rôle :** validateur (red team). **Objet :** branche `harness/v1` (commits `fe48944`, `cfdfa3a`), worktree `.claude\worktrees\agent-a696aab9414ff3872`. Le worktree n'a pas été modifié (`git status` propre après la revue ; pytest lancé sans cache ni bytecode).
- **Code de la revue :** `docs/agents/validation/T-015_code/` (`run_reconcile.py`, `check_time50.py`, `indep_sim_and_edges.py`, `indep_account.py`, `decompose_jupiter14.py`, `corrected_time50_tables.py`, `nan_audit.py`). Tables corrigées : `T-015_code/T-015_time50_nostop_platform_table.csv` et `T-015_code/T-015_time50_nostop_account_table.csv`.
- **Anti-doublon :** `JOURNAL.md` contient seulement le lancement de T-015 (19:15) et le résultat T-006 (17:00). `REGISTRY.csv` ne contient aucune revue du harness. Cette revue reprend `power_jupiter_2026-10-06.md` (T-007) pour l'écart avec le +14 %/an.
- **Catégorie des chiffres :** la réconciliation et le code sont **vérifiés**. Tous les rendements sont **en échantillon** : entrées du ledger pré-HOLDOUT (2021-11-30 → 2025-04-07), et en plus Exp 49 (fenêtre HOLDOUT déjà vue) dans la §6. Sauf mention contraire : entrée à l'ouverture de la barre suivante, stops intrabar avec gestion des gaps, coûts du harness v1.

## 0. Verdict

**APPROUVÉ AVEC RÉSERVES** pour le moteur de remplissage et le niveau compte. **REFUSÉ** pour les tableaux « sortie au temps » de `T-006_2026-10-06.md` et de `T-006_platform_table.csv` / `T-006_account_table.csv` (correction C1).

- Le moteur est correct. Je l'ai réimplémenté indépendamment, en espace de prix : écart maximal 1,7e-16 sur les 2 549 trades, 0 raison de sortie et 0 barre de sortie différentes. La réconciliation est exacte. Je n'ai trouvé aucune convention optimiste dans les remplissages.
- **Défaut bloquant (C1) :** la règle « TIME50 sans stop » de T-006 avait en réalité **le stop par trade actif**. Les chiffres publiés pour la règle déployée sur Jupiter sont donc faux, et dans le sens pessimiste. À corriger avant tout usage décisionnel de cette règle.
- Le modèle de coûts est cohérent avec T-004 : il est plutôt conservateur par trade, mais **optimiste sur la rampe CAD** (≈ 1 % modélisé contre ≈ 2,8-3 % selon T-004). Les étiquettes `verified` sont à corriger pour Propr.

## 1. Réconciliation (VÉRIFIÉ)

`py -3 -m quant_bot.execution_harness.reconcile` relancé via `run_reconcile.py` (sortie redirigée hors du worktree). Population : 2 549 trades, 0,14 % AR, règle stop par trade + trailing 0,63 %/0,8 % + 50 barres.

| Mode | n | PF | Net/trade | Brut/trade |
|---|---|---|---|---|
| Référence `exit_realism_check.csv` (intrabar) | 2 549 | **0,951070** | −0,02534 % | +0,1147 % |
| Harness `signal_close` | 2 549 | **0,951070** | −0,02534 % | +0,1147 % (2 549/2 549 appariés, écart max 1,0e-16) |
| Harness `next_open` | 2 549 | 0,943228 | −0,02974 % | +0,1103 % |
| **Ma réimplémentation indépendante** `next_open` | 2 549 | 0,943228 | −0,02974 % | +0,1103 % (écart max 1,7e-16) |

Décomposition de l'écart `next_open` (−0,0044 pt) : −0,0015 pt dû au prix d'entrée, −0,0029 pt dû aux changements de trajectoire. Je confirme les deux.

Sensibilité à la latence d'entrée (non publiée dans T-006, règle de référence) : 1 barre → −0,0354 %/trade, PF 0,930 ; 2 barres → −0,0514 %, PF 0,901.

Les 14 tests unitaires passent.

## 2. Conventions optimistes : audit

| Convention interdite ou optimiste | Statut v1 | Preuve |
|---|---|---|
| Sortie au prix exact du stop sur un franchissement au close | **absente** | `fills.py` : test sur le low/high, remplissage `min(niveau, open)` ; cas E2 (gap short → open) et E13 |
| Peak incluant la barre courante | **absent** : le peak est mis à jour après le test, et l'armement du trailing ne s'applique qu'à t+1 | cas E1 (sortie à la barre t+1, pas à t), E1b |
| Entrée au close du signal hors réconciliation | défaut = `next_open` ; `signal_close` refuse la latence | `fills.py` ; **réserve R5** : le mode reste appelable sans avertissement |
| MTM sur les closes | **non** : MTM sur les lows (long), barre de stop marquée à son remplissage, PnL réalisé compté à la minute suivante | `indep_account.py` : reproduction exacte (final 454,891 USD, MaxDD −23,608 %, pire jour −11,738 %) |
| MTM sans frais de sortie | **présent, mineur** : une position ouverte n'est pas marquée net des frais de sortie | E10 : −0,26 % vs −0,53 % sur Kraken taker à plat ; effet nul sur Jupiter (MaxDD −23,608 → −23,607) |
| Stop rempli au niveau exact au toucher (aucun glissement) | présent ; le glissement passe seulement par `slippage_pct` (0 sauf Propr) | E13. **Réserve R2** : Jupiter n'a pas d'ordre stop au repos côté serveur (à vérifier). Un stop y serait détecté par le bot puis exécuté par swap, ce qui est plus lent et plus cher. Sans objet pour la règle déployée (sans stop) |
| Latence sur les sorties | non paramétrable (entrée seulement) | réserve R3 |

Cas limites indépendants (`indep_sim_and_edges.py`, 15 cas, fixtures en mémoire). Signalés (FLAG) :

- **E7 (bloquant, = C1) :** `ExitRule(max_bars=50)` sans `stop_distance` n'est pas une règle sans stop si la table de candidats contient une colonne `stop_distance` : la valeur par trade l'emporte silencieusement (`harness.py`, `sd = ... r.stop_distance`, puis `fills.py` `stop_distance if not None else rule.stop_distance`).
- **E4 :** un low NaN fait sauter le test du stop sur cette barre, sans drapeau. **E4b :** un close NaN sur la barre de sortie donne `gross_ret = NaN` avec `status="ok"` ; `summarize` compte le trade mais l'exclut de la moyenne et du PF. L'audit du cache (`nan_audit.py`) ne trouve aucun NaN, aucun doublon et 1 seul trou (BTC) sur les 9 symboles : sans effet aujourd'hui, mais à bloquer pour les barres OKX/forward.
- **E5 :** un trou d'horodatage dans la fenêtre est signalé (`gap_in_window`), mais le trade reste `ok` avec, par exemple, 5 h de détention au lieu de 50 min.
- **E6 :** les trades `end_of_data` comptent dans le PF.

Cas conformes : E1, E1b, E2, E3 (short, trailing), E8 (4e position à 33 % refusée par le plafond), E9 (une entrée sur la barre de sortie est refusée, la barre suivante est acceptée), E11 (frais fixes 0,0556 % à 36 USD), E12 (horodatages en double → erreur), E13.

## 3. Correction C1 : la « sortie au temps » de T-006 avait un stop

`reconcile.py` passe les candidats avec `stop_distance` (issue du ledger) à `TIME50 = ExitRule(max_bars=50)` : 141 des 1 287 trades SOL sortent sur stop (`check_time50.py`). Chiffres corrigés, vraiment sans stop (`corrected_time50_tables.py`, en échantillon, pré-HOLDOUT, entrée à l'open suivant) :

| Plateforme | n | Brut | Net/trade (T-006 publié) | **Net/trade corrigé** | PF corrigé | Net à 33 % de 500 CAD |
|---|---|---|---|---|---|---|
| research_0p14 (9 symboles) | 2 549 | +0,352 % | +0,035 % | **+0,212 %** | 1,280 | +0,212 % |
| jupiter_sol | 1 287 | +0,187 % | −0,007 % | **+0,107 %** | 1,148 | +0,090 % |
| jupiter_cbbtc_weth | 544 | +0,228 % | −0,104 % | **−0,012 %** | 0,983 | −0,028 % |
| propr | 2 549 | +0,352 % | −0,003 % | **+0,174 %** | 1,226 | +0,174 % |
| kraken_ca_maker | 2 549 | +0,352 % | −0,625 % | −0,448 % | 0,590 | — |
| kraken_ca_taker | 2 549 | +0,352 % | −1,425 % | −1,248 % | 0,234 | — |

Niveau compte, 500 CAD, une position par symbole, rampe 0,5 %/sens, MTM minute sur les lows :

| Plateforme | Taille | Trades pris | Rendement CAD sur 3,24-3,35 ans (T-006 publié) | **Corrigé** | MaxDD | Pire jour | Creux intrajournalier | Pire semaine |
|---|---|---|---|---|---|---|---|---|
| jupiter_sol | 33 % | 1 017 (270 refus « symbole occupé ») | −14,9 % | **+25,7 %** (≈ +7,3 %/an) | −23,6 % | −11,7 % (2022-11-09) | −17,2 % | −14,7 % |
| jupiter_sol | 10 % | 1 017 | — | +2,9 % | −8,1 % | −3,6 % | −5,5 % | −4,6 % |
| research_0p14 | 33 % | 1 756 (384 refus pour exposition) | — | +35,8 % | −30,5 % | −13,9 % (2022-05-11) | −17,5 % | −19,9 % |
| propr (comme capital propre) | 33 % | 1 755 | — | +11,3 % | −37,3 % | −14,1 % | −17,7 % | −20,5 % |

Lecture :
- Ces chiffres sont en échantillon : la sortie et l'univers ont été choisis sur ces données (Exp 50), ils ne servent qu'à rejeter.
- À 10 %, la rampe CAD (1 %) et les frais fixes absorbent presque tout le gain sur Jupiter.
- Les tableaux pré-HOLDOUT **ne contiennent pas le krach du 2025-10-10**, source du pire jour à −40,9 % d'Exp 50. Le risque de queue de ces tableaux est donc sous-estimé.

## 4. Coûts : chaque valeur contre T-004 (`VENUES_500CAD_2026-10-06.md`, `venues_costs_2026-10-06.csv`)

| Paramètre harness | Valeur v1 | T-004 (2026-10-06) | Écart / sens |
|---|---|---|---|
| jupiter_sol frais + demi-écart | 0,02 % + 0,02 %/côté = **0,08 % AR** | `/order` mesuré **0,037-0,041 % AR, frais de 2 pb inclus** (« fee included in the quote ») | double comptage des frais dans l'écart : **conservateur d'environ 0,04 pt AR** |
| Route `/build` (Metis, sans frais) | absente | 0,01-0,03 % AR, MEV et atterrissage à notre charge | plateforme manquante (optionnelle) |
| Frais réseau/priorité | 0,01 USD/ordre | base ≈ 0,0006 USD ; priorité p90 0,003-0,006 USD ; parfois gratuit (JupiterZ) | conservateur en temps normal ; **non modélisé en krach** (pics de priorité, échecs) |
| Taille min. Jupiter | 0 | aucune ; route gasless ≈ 10 USD min | OK à 35-116 USD |
| Impact Jupiter | 0 jusqu'à 10 K USD | cotations plates 50-165 USD (3 instantanés le même jour) | OK, non représentatif des krachs |
| jupiter_cbbtc_weth | 0,10 % + 0,02 %/côté = 0,24 % AR | ≥ 0,20 % (10 pb/swap) ; écart non mesuré le 2026-10-06 | cohérent |
| **Rampe CAD↔USDC** | **0,5 %/sens (≈ 1 % au total)**, `usd_per_cad` 0,72 | **≈ 2,8-3 % de 500 CAD au total** : 0,8-1,0 % de frais de change crypto + **retrait Interac 10 CAD** + frais de retrait réseau non vérifiés ; ou FX Wealthsimple 1,5 % ; USDC-CAD = 1,42075 → **0,7038** | **optimiste d'environ 1,8-2 pts sur le rendement CAD** ; frais fixe de 10 CAD absent ; taux 0,72 périmé |
| Propr frais | 0,075 %/côté, `verified=True` | 0,075 % n'est qu'un **exemple** dans l'OpenAPI ; le règlement §20 dit Hyperliquid au coût (0,045 % taker) → contradiction | **mauvaise étiquette** : `verified=False`, garder 0,075 % et ajouter la variante 0,045 % |
| Propr funding, levier, règles de challenge | absents | perte journalière 5 %, DD trailing 8 % sur l'équité latente, prix 50 USD | le compte « propr » n'évalue **pas** la voie B (aucune simulation de violation) |
| Kraken 0,40/0,80 % | 0,40 / 0,80 % | 0,40 / 0,80 % (vérifié) | conforme ; écart CAD et taille min. non modélisés (optimiste, sans conséquence : la plateforme est perdante) |

Non modélisé, dans les deux sens : écart entre le signal OKX/Binance et le prix spot Jupiter (T-012), MEV, transactions échouées, fiscalité.

## 5. Niveau compte (`simulate_account`)

- **Chevauchement :** `one_position_per_symbol=True` par défaut, comme le runner live (`SKIPPED_OPEN`). Une entrée est refusée si elle tombe sur la barre de sortie de la position précédente (E9). Le plafond d'exposition brute est calculé sur l'équité réalisée, ce qui équivaut à la contrainte de cash en spot (E8). Les refus sont comptés par motif.
- **Taille min. :** le refus fonctionne, mais toutes les valeurs min. sont à 0 (inconnues) : il ne se déclenche jamais.
- **Pire jour / pire semaine :** calculés sur la courbe minute marquée aux lows (fin de jour UTC, semaine W-SUN), plus le creux intrajournalier. Ma réplique indépendante reproduit le rendement, le MaxDD et le pire jour à 1e-3 près.
- **Réserve :** pas de CAGR en sortie (seulement le total et `years`) ; pas de garde HOLDOUT, et le cache s'étend jusqu'au 2026-08-20.

## 6. Pourquoi +14,1 %/an (`JUPITER_PLAN_FR.md`) ne correspond pas au harness

J'ai reproduit +14,1 % de façon indépendante (`decompose_jupiter14.py`) : `jupiter_backtest.py`, SOL seul, entrées pré-HOLDOUT + Exp 49 (2021-11 → 2026-05, 4,47 ans), **0,07 % AR** (le « vrai frais » utilisé équivaut à 0,07 % AR), entrée au close du signal, 33 %, **positions empilées**. Résultat : CAGR **+14,11 %**.

| Étape (même population, SOL, 50 barres sans stop) | CAGR |
|---|---|
| A0 configuration du plan (empilement, close, 0,07 %) | **+14,1 %** |
| A1 + une seule position par symbole (règle du runner live ; 1 558 → 1 234 trades) | **+9,4 %** (−4,7 pts) |
| A2 + entrée à l'open suivant | +9,7 % (+0,3) |
| A3 + coût harness 0,08 % AR | +8,7 % (−1,0) |
| A4 + 2 × 0,01 USD à l'échelle 500 CAD | +7,2 % (−1,5) |
| Harness complet (+ rampe 1 %) : rendement CAD | **+6,5 %/an** (+32,8 % sur 4,48 ans), MaxDD −23,6 %, pire jour −11,7 % |
| Idem, rampe T-004 (≈ 3 %) au lieu de 1 % | ≈ +6,0 %/an (estimation) |

Contrôle de période :
- Le plan restreint au pré-HOLDOUT donne +15,1 %. La fenêtre HOLDOUT n'explique donc **pas** le chiffre élevé.
- Exp 49 seul, une position, 33 % : +4,3 % CAD en 0,98 an.

Le principal facteur est **l'empilement** de positions sur SOL, confirmé (T-007 l'avait signalé : les signaux ignorés ont un brut moyen de +0,22 à +0,44 %). Viennent ensuite les frais fixes à 500 CAD et le coût par trade. Le −12,9 % / −14,9 % publié par T-006 s'explique en plus par le défaut C1.

Rappel : tout ceci reste en échantillon (sortie et univers choisis après coup) ; T-007 montre que l'edge OOS SOL n'est pas significatif (t = 1,08).

## 7. Corrections requises

**Bloquant avant tout usage décisionnel :**
- **C1.** `run_trades` : le stop par trade ne doit s'appliquer que si la règle le demande explicitement (par ex. `ExitRule(use_candidate_stop=True)`), ou bien lever une erreur s'il y a ambiguïté. Ajouter le test E7. Relancer `reconcile.py` et republier les tableaux TIME50 et les tableaux compte de T-006 (valeurs attendues en §3). Corriger le résumé du JOURNAL (« jupiter_sol ~0 %/trade, compte −12,9 % ») : c'était la règle de référence ; la règle déployée donne +0,107 %/trade et +25,7 % en échantillon.

**À faire en v1.1 :**
- **C2.** Rampe CAD selon T-004 : frais fixe de retrait de 10 CAD, ≈ 0,8-1,0 % de change (ou FX 1,5 %), `usd_per_cad` = 0,704 avec date et source.
- **C3.** Jupiter SOL : ne pas compter à la fois les frais et un demi-écart qui les inclut déjà. Utiliser l'AR mesuré `/order` (≈ 0,04 %) et garder 0,08 % comme scénario de stress. Ajouter `jupiter_sol_build` (0 frais, + allocation MEV).
- **C4.** Propr : `verified=False` sur 0,075 %, variante à 0,045 %, et avertissement explicite : le compte n'évalue pas les règles de challenge.
- **C5.** Données : rejeter (`status`) ou signaler les trades avec un OHLC NaN dans la fenêtre, un trou d'horodatage (`gap_in_window`) ou `end_of_data`. Les exclure du PF par défaut.
- **C6.** Plateformes sans ordre stop au repos (Jupiter) : un stop doit être modélisé « détecté puis swap » (open de la barre suivante + latence). Ajouter `exit_latency_bars`.
- **C7.** Avertissement (ou drapeau obligatoire) pour `entry_mode="signal_close"` ; option pour marquer les positions ouvertes net des frais de sortie ; CAGR en sortie ; drapeau HOLDOUT selon la période des entrées.
- **C8.** Publier la sensibilité à la latence (1-2 barres) avec chaque tableau.

## 8. Compteur de multiple testing (cette revue)

Aucun paramètre n'a été choisi ni optimisé. Configurations calculées, toutes rapportées :
- réconciliation relancée : les 24 configurations de T-006 ;
- latence 1 et 2 barres × 2 règles = 4 ;
- TIME50 corrigé : 6 plateformes, plus 12 configurations compte ;
- décomposition du +14 % : 3 coûts + 8 étapes, plus 9 configurations compte du harness, plus 1 contrôle du défaut ;
- 15 cas synthétiques.

Aucune hypothèse n'est VALIDÉE ou REJETÉE par cette revue : elle porte sur un outil de mesure.

## Fichiers

Écrits : ce rapport et `docs/agents/validation/T-015_code/` (scripts et 2 CSV). Rien d'autre n'a été modifié : branche `harness/v1` intacte, pas de commit, pas d'écriture dans `JOURNAL.md`, aucun fichier Codex touché. Sortie de la réconciliation relancée : scratchpad de session (non versionné).
