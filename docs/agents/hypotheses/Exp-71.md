# Exp 71 — Réplication de la zone de bruit sur MYM (Dow) et M2K (Russell 2000) — PRÉENREGISTREMENT

- Exp F2 de `research/H-R17_funded_optimal.md` §7 (commit b59854c), reprise **sans modification**. Préenregistrée le 2026-10-10 par l'orchestrateur, figée par ce commit avant tout téléchargement des données. Juge : Validateur.

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

