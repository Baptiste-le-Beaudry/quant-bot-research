# T-007 — Analyse de puissance du forward Jupiter (2026-10-06)

- **Rôle :** validateur (red team). **Tâche :** `docs/agents/tasks/T-007.md`.
- **Code et sorties :** `docs/agents/validation/power_jupiter_2026-10-06_code/` (`build.py` → rendements par trade ; `stats.py` → statistiques ; `sim.py` → puissance par bootstrap ; `rule.py` → caractéristiques de la règle d'arrêt ; `power_*.csv`). Exécution : `py -3 -I build.py <dir>` puis les autres scripts depuis `<dir>`.
- **Anti-doublon :** `JOURNAL.md` ne contient que la création de T-007 ; `REGISTRY.csv` aucune analyse de puissance ; `research_plan_status.md` (Exp 50, suivi Jupiter, backtest Jupiter) donne des moyennes mais aucune analyse de puissance. Seul critère existant : « ≥ ~60 trades SOL, gain moyen > 0 » (`docs/JUPITER_PLAN_FR.md`), évalué ci-dessous.
- **Variantes comptées (multiple testing) :** aucune variante de stratégie testée. Cette analyse porte sur la règle déjà déployée. Seule la règle d'arrêt (§5) a été simulée, en une seule version, sans réglage sur les résultats.

## 0. Réponse courte

**Non : le forward Jupiter ne peut pas confirmer l'edge dans un délai raisonnable.** Sur la meilleure estimation hors échantillon (SOL, +0,114 %/trade net, écart-type 1,57 %), il faut **environ 1 170 trades SOL** pour atteindre 80 % de puissance. Cela donne **≈ 5,5 ans** avec un flux réparé (**mars 2032**) et **≈ 14 ans** avec le flux actuel à 38 % (**2041**). Si l'edge vrai ne vaut que la moitié, il faut ~4 700 trades, soit plusieurs décennies.

Le forward peut en revanche, en quelques semaines ou mois :

1. mesurer le **coût réel** (cotation Jupiter contre barre), avec une bonne précision dès ~20 trades ;
2. vérifier que la **fréquence des signaux** colle au backtest ;
3. détecter un **échec grossier** : un edge vrai ≤ −0,30 %/trade est rejeté dans ~97 % des cas vers 100 trades (mars 2027 si le flux est réparé, janvier 2028 au flux actuel).

Le critère actuel du plan (« ≥ 60 trades et moyenne > 0 ») **se déclare gagnant dans ~50 % des cas même si l'edge est nul**. Il ne doit pas servir de feu vert.

## 1. Distributions historiques aux coûts Jupiter réels

**Méthode (vérifié, recalculé indépendamment) :**
- Entrées : walk-forward TEST de SOL/BTC/ETH (registre pré-HOLDOUT 2021-11 → 2025-02, et Exp 49 réentraîné 2025-05 → 2026-05).
- Sortie : close Binance 1m à +50 barres, sans stop (`TIME50_NOSTOP`).
- **Règle du runner live appliquée :** une seule position par symbole ; un signal reçu pendant qu'une position est ouverte est ignoré (`jupiter_paper.py`, `SKIPPED_OPEN`).
- Coûts aller-retour : **SOL 0,06 %** (2 × 2 pb de frais de plateforme + ~2 pb d'écart de cotation + 2 × 0,01 $ de frais réseau) ; **BTC/ETH 0,22 %** (2 × 10 pb + ~2 pb).
- Contrôle : SOL OOS sans la règle d'une seule position = 271 trades, brut +0,226 %, identique à `experiment50_trades.csv`.

| Fenêtre | Univers | N | Trades/jour | Net moyen | Écart-type | Médiane | Asymétrie | Kurtosis | Pire trade | Gagnants | PF | t (grappes par jour) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **OOS Exp 50 (2025-05 → 2026-05)** | **SOL** | **217** | **0,58** | **+0,114 %** | **1,565 %** | +0,261 % | −1,68 | 8,0 | −9,8 % | 57,6 % | 1,23 | **1,08** |
| OOS | SOL+BTC+ETH | 392 | 1,05 | **−0,010 %** | 1,520 % | +0,146 % | −1,18 | 5,1 | −9,8 % | 54,3 % | 0,98 | −0,09 |
| OOS | BTC | 34 | 0,09 | +0,022 % | 1,51 % | | | | | | 1,04 | 0,07 |
| OOS | ETH | 141 | 0,38 | **−0,208 %** | 1,44 % | | | | | | 0,68 | −1,89 |
| Pré-HOLDOUT (en échantillon pour la sortie et l'univers) | SOL | 1 017 | 0,86 | +0,118 % | 2,444 % | +0,247 % | −0,44 | **20,2** | **−19,6 %** | 55,7 % | 1,16 | 1,75 |
| Pré-HOLDOUT | SOL+BTC+ETH | 1 471 | 1,24 | +0,098 % | 2,304 % | | | 19,1 | −19,6 % | | 1,14 | 1,81 |

**Catégorie :** en échantillon. La fenêtre OOS a déjà été vue (incident HOLDOUT, Exp 49/50) ; elle sert à rejeter, pas à confirmer.

Constats :
- **Même sur une année complète hors échantillon, l'edge SOL n'est pas significatif (t = 1,08).** Le forward partirait donc d'un prior faible.
- **Instance SOL+BTC+ETH : l'edge attendu est ≈ 0, voire négatif.** Aux frais de 10 pb par swap, ETH perd −0,21 %/trade et BTC ne gagne rien. Ses trades SOL sont les mêmes que ceux de l'instance SOL (le plafond de 3 × 33 % ne bloque jamais), donc elle **n'apporte aucune observation indépendante sur SOL**. Au mieux, elle sert de contrôle négatif pour BTC/ETH.
- **Écart entre le backtest et le runner (nouveau, vérifié) :** `jupiter_backtest.py` empile plusieurs positions sur le même symbole (seul le cash limite), alors que le runner live les refuse. Les signaux ignorés ont un brut moyen de +0,44 % (OOS) et +0,22 % (pré-HOLDOUT). Avec la règle live, le net SOL OOS tombe de +0,166 % à **+0,114 %** et la fréquence de 0,73 à 0,58 trade/jour. Le chiffre « SOL CAGR +14,1 % » du plan **ne correspond donc pas à la règle déployée**.
- Sensibilité au coût, SOL OOS avec la règle live : +0,134 % à 0,04 % AR ; +0,074 % à 0,10 % ; +0,024 % à 0,15 %. Le point mort se situe vers 0,17 % AR.
- La corrélation entre trades simultanés est faible pour SOL seul (effet de plan, ou DEFF, = 0,98 en OOS). Elle double la variance pour l'univers à 3 symboles (DEFF = 2,03). C'est une raison de plus de ne pas compter les deux instances comme des preuves séparées.

## 2. Trades nécessaires (α = 5 % unilatéral, puissance 80 %)

### 2a. Approximation normale

Formule : N = ((1,645 + 0,842) · σ / μ)².

| Base | Edge vrai | N trades SOL | Flux réparé (0,58/j) | Flux actuel (38 % → 0,22/j) |
|---|---|---|---|---|
| OOS (σ 1,565 %) | μ = 0,114 % | **1 165** | 5,5 ans (2032-03) | 14,4 ans (2041-03) |
| OOS | μ/2 = 0,057 % | 4 661 | 22 ans | 58 ans |
| OOS | μ/4 = 0,029 % | 18 643 | 88 ans | 231 ans |
| Pré-HOLDOUT (σ 2,444 %, 0,86/j) | μ = 0,118 % | 2 652 | 8,4 ans | 22 ans |
| Référence : sans la règle d'une seule position (OOS, μ 0,166 %) | μ | 574 | 2,2 ans | 5,7 ans |

### 2b. Bootstrap par blocs de 7 jours

Méthode :
- On rééchantillonne des jours calendaires entiers, jours sans trade compris, par blocs de 7 jours, ce qui conserve les grappes de trades et la persistance de la volatilité.
- Les rendements sont recentrés sur l'edge du scénario.
- Le flux actuel est simulé en gardant chaque trade avec une probabilité de 0,379.
- Test : z de la moyenne avec erreur-type groupée par jour UTC, unilatéral à 5 %.
- 2 000 tirages (OOS), 1 000 tirages (pré-HOLDOUT).

Puissance, distribution OOS de SOL :

| Horizon | N médian (réparé) | P(μ = 0,114) | P(μ/2) | P(μ/4) | Taille réelle si μ = 0 | N médian (actuel 38 %) | P(μ), actuel | Taille réelle, actuel |
|---|---|---|---|---|---|---|---|---|
| 3 mois | 51 | 0,21 | 0,13 | 0,10 | 0,076 | 19 | 0,18 | 0,098 |
| 6 mois | 105 | 0,21 | 0,11 | 0,08 | 0,052 | 40 | 0,18 | 0,084 |
| 1 an | 212 | 0,29 | 0,13 | 0,08 | 0,049 | 81 | 0,20 | 0,066 |
| 2 ans | 425 | 0,44 | 0,17 | 0,10 | 0,044 | 162 | 0,26 | 0,059 |
| 3 ans | 643 | 0,56 | 0,20 | 0,09 | 0,033 | 243 | 0,32 | 0,046 |
| 5 ans | 1 064 | **0,77** | 0,28 | 0,11 | 0,032 | 406 | 0,43 | 0,056 |

- Le bootstrap confirme l'approximation normale : 80 % de puissance demande ~5 ans de flux réparé pour l'edge OOS complet.
- **Queues épaisses :** avec moins de 100 trades, le test nominal à 5 % rejette en réalité 8 à 10 % du temps sous un edge nul (asymétrie négative). Avec la distribution pré-HOLDOUT (kurtosis 20), la taille réelle reste de **8 à 11 %** à tous les horizons. Un z ≥ 1,645 ne suffit donc pas ; la règle du §5 utilise des seuils plus stricts.
- Distribution pré-HOLDOUT (σ plus grand, mais 0,86 trade/jour) : puissance de 0,38 à 1 an et de 0,68 à 5 ans (flux réparé).

### 2c. Critère actuel du plan (« ≥ 60 trades SOL, moyenne > 0 »)

Probabilité de le remplir dans l'année (bootstrap OOS) :

| Edge vrai | Flux réparé | Flux actuel |
|---|---|---|
| μ = 0,114 % | 0,74 | 0,66 |
| μ/2 | 0,64 | 0,55 |
| μ/4 | 0,57 | 0,51 |
| **0** | **0,53** | **0,46** |

**Ce critère est un pile ou face. Il doit être retiré comme condition de passage à l'argent réel.**

## 3. Dates

- Départ : 2026-10-05 18:54. Taux SOL de référence : 0,58 trade/jour (OOS, avec la règle live).
- Ce taux suppose que les barres OKX produisent les mêmes signaux que les barres Binance d'entraînement, ce qui n'est pas vérifié (STATE #12).

| Jalon | Flux réparé | Flux actuel (38 %) |
|---|---|---|
| 20 trades (contrôle du coût réel) | ~2026-11-08 | ~2027-01-04 |
| 50 trades (1er regard) | ~2026-12-30 | ~2027-05-19 |
| 100 trades (détection d'un échec grossier) | ~2027-03-26 | ~2028-01-01 |
| 200 trades (contrôle de futilité) | ~2027-09-13 | ~2029-03-28 |
| 400 trades (fin de la règle, §5) | ~2028-08-21 | ~2031-09-19 |
| 1 165 trades (puissance 80 %, μ OOS) | ~2032-03-25 | ~2041-03-13 |

**Aucun signal dans les premières ~24 h : ce n'est pas anormal.** Les ~548 minutes éligibles donnent environ 0,22 signal SOL attendu, donc P(0) ≈ 0,80 pour SOL. Pour l'instance à 3 symboles, environ 0,50 signal attendu, donc P(0) ≈ 0,61.

**Biais du flux actuel :** les minutes exclues sont les 8 h qui suivent chaque micro-coupure. L'échantillon forward n'est donc pas aléatoire dans le temps. Les coupures WebSocket peuvent être plus fréquentes pendant les pics de volatilité, justement quand les signaux de « dip » apparaissent. Réparer le flux (rattrapage REST ou garde proportionnée au trou) compte autant pour la validité que pour la vitesse.

## 4. Ce que le forward peut mesurer vite (puissance élevée)

| Mesure | Pourquoi c'est rapide | Seuil proposé |
|---|---|---|
| Coût réel par trade = frais + (prix de la cotation Jupiter / close de la barre OKX − 1), à l'achat et à la vente | Variance de l'ordre du point de base, contre ~150 pb pour le rendement | Coût AR moyen > **0,15 %** après ≥ 20 trades → l'edge OOS est réduit à ≤ +0,02 % : arrêt pour futilité |
| Fréquence des signaux par minute éligible | Test de Poisson, contre 0,58/1 440 par minute éligible (SOL) | Hors de l'intervalle de Poisson à 99 % après ≥ 30 jours éligibles → décalage de distribution OKX/Binance, enquêter avant tout verdict |
| Échec grossier (edge vrai ≤ −0,30 %) | Rejeté à ~97 % vers 100 trades | Règle ÉCHEC du §5 |

Prérequis à corriger (Ops) : la vente ne garde ni la cotation brute, ni `priceImpactPct`, ni l'heure exacte de la cotation (rapport Ops §6). Le **coût à la vente** n'est donc pas mesurable aujourd'hui. Sans ce logging, le contrôle n°1 est impossible.

## 5. Règle d'arrêt proposée (à préenregistrer avant le 1er trade SOL)

- **Unité :** trade SOL fermé de l'instance `jupiter_paper_sol`. Le net est calculé avec les vraies cotations Jupiter, frais et réseau compris.
- **Statistique :** moyenne m du net, erreur-type s groupée par jour UTC.
- **Constante figée :** μ_ref = **+0,114 %** (Exp 50 SOL, règle live, 0,06 % AR).
- L'instance SOL+BTC+ETH est **descriptive seulement**. Elle n'entre pas dans le verdict.

**Regards** à N = 50, 100, 200 et 400 trades SOL. On ne regarde pas entre ces jalons.

1. **SUCCÈS** (edge > 0 confirmé en forward) : m/s ≥ **3,0** à un regard intermédiaire, ou m/s ≥ **2,0** à N = 400.
2. **ÉCHEC** (forward incompatible avec le backtest) : (m − μ_ref)/s ≤ **−2,33** à n'importe quel regard. La stratégie est rejetée pour Jupiter.
3. **FUTILITÉ** : m ≤ 0 à N = 200. On arrête, sans conclure qu'il y a un edge.
4. **Arrêts d'exécution**, à tout moment :
   - coût AR mesuré > 0,15 % en moyenne après ≥ 20 trades ;
   - drawdown du compte (marquage à la minute) ≤ **−25 %** ;
   - plus de 2 incidents techniques (cotation manquée, position bloquée).

   Le seuil de −25 % est un **arrêt de risque de queue, pas un test d'edge**. En simulation, les drawdowns sont presque les mêmes sous un edge nul et sous μ_ref : à 1 an et flux réparé, le 1er centile vaut −18 % (OOS) à −35 % (pré-HOLDOUT).
5. **INCONCLUSIF** si N = 400 est atteint sans décision. Pas d'argent réel sur cette base.

Changer un runner, le flux ou le modèle **remet le compteur à zéro**, ou exige une analyse séparée par période.

**Caractéristiques simulées** (bootstrap par blocs de 7 jours ; distribution OOS de SOL, entre parenthèses la distribution pré-HOLDOUT ; flux réparé) :

| Edge vrai | SUCCÈS | ÉCHEC | FUTILITÉ | INCONCLUSIF | Arrêt médian |
|---|---|---|---|---|---|
| μ = 0,114 % | 0,31 (0,36) | 0,03 (0,04) | 0,10 (0,16) | 0,56 (0,44) | 400 trades, ~655 j |
| μ/2 | 0,09 (0,18) | 0,08 (0,05) | 0,24 (0,28) | 0,59 (0,49) | 400 trades |
| μ/4 | 0,06 (0,11) | 0,11 (0,10) | 0,30 (0,31) | 0,54 (0,48) | 400 trades |
| **0** (faux succès) | **0,03 (0,07)** | 0,16 (0,15) | 0,34 (0,32) | 0,47 (0,46) | |
| −0,30 % | 0 | **0,97 (0,78)** | 0,03 (0,22) | 0 | **100 trades, ~155 j** |

Au flux actuel, les proportions sont les mêmes (SUCCÈS 0,32 sous μ ; ÉCHEC 0,96 sous −0,30 %), mais avec des durées ×2,6 : environ 1 740 jours pour 400 trades, et environ 426 jours pour détecter −0,30 %.

**Lecture :** le risque de faux succès est contenu (3 à 7 %). En contrepartie, sous l'edge OOS, **le succès n'arrive qu'une fois sur trois, et pas avant ~2 ans** même avec un flux réparé. La règle détecte surtout un échec : elle peut **rejeter**, pas **confirmer**, dans un délai utile.

## 6. Avis franc

1. **Le forward Jupiter actuel ne peut pas confirmer un edge dans un délai raisonnable** (moins d'un an), ni au flux actuel, ni au flux réparé. L'edge attendu (~0,11 %/trade) est environ 14 fois plus petit que l'écart-type d'un trade (~1,6 %), avec ~0,6 trade/jour sur un seul symbole. C'est arithmétique ; aucune amélioration du runner n'y change quoi que ce soit.
2. **Il reste utile à condition de changer son rôle.** C'est un test d'**exécution** (coût réel aller et retour, fréquence des signaux OKX contre backtest, incidents) et un **détecteur d'échec grossier**. Il faut le préenregistrer comme tel, avec la règle du §5, et :
   - retirer « ≥ 60 trades et moyenne > 0 » comme critère d'argent réel ;
   - réparer le flux (sinon tout est ralenti d'un facteur 2,6 et biaisé dans le temps) ;
   - logger les cotations de vente.
3. **Pour confirmer quelque chose, il faut un autre plan**, à décider par l'orchestrateur. Pistes, non testées :
   - (a) un critère moins bruité que le net à 50 min (par exemple le rendement à 10 min du label, ou le signe), préenregistré, en sachant que ce n'est pas la même hypothèse que la rentabilité ;
   - (b) davantage de trades indépendants, avec plus de symboles, mais sur Jupiter les autres symboles coûtent 10 pb par swap et perdent déjà en OOS ;
   - (c) accepter une décision bayésienne ou par la perte maximale tolérée (« on risque X CAD pour apprendre »), plutôt qu'une confirmation statistique.
4. **Le chiffre « SOL +14,1 %/an » du plan Jupiter est surévalué pour la règle déployée** : il empile des positions sur le même symbole, ce que le runner refuse. Avec la règle live, le net OOS par trade baisse d'environ un tiers (+0,166 → +0,114 %). À corriger dans `JUPITER_PLAN_FR.md` par son propriétaire.

## Limites

- Le coût AR de 0,06 % SOL repose sur les cotations du 2026-10-05, hors MEV et frais de priorité réels. Le coût BTC/ETH (0,22 %) suppose ~2 pb d'écart de cotation.
- La fréquence (0,58/j) vient des barres Binance avec des modèles walk-forward. Le modèle refit et les barres OKX peuvent donner une autre fréquence et une autre distribution.
- Le bootstrap rééchantillonne une seule année OOS : il ne couvre pas un changement de régime au-delà de ce qu'elle contient. La distribution pré-HOLDOUT, plus large, sert de contrôle de robustesse.
- Le flux actuel est modélisé par un amincissement aléatoire des trades (p = 0,379), alors que l'exclusion réelle est groupée dans le temps : la durée est correcte, mais le biais temporel n'est pas modélisé.
- Fichiers écrits : ce rapport, et `power_jupiter_2026-10-06_code/` (scripts et CSV). Rien d'autre n'a été modifié. Pas de commit, pas d'écriture dans `JOURNAL.md`.
