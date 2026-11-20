# Exp 70 — Zone de bruit MNQ, à plat les jours de GEX élevé (H-R15-C) — PRÉENREGISTREMENT

- Préenregistré le 2026-10-09 par l'orchestrateur, repris **sans modification** de `research/H-R15_nouvelles_strategies.md` §5.3 (commit 2742076 ; instantané DIX.csv et sha256 au §3.3 de la fiche), figé par ce commit avant tout calcul sur H. Juge : Validateur.

- **Étape 0 (bloquante), contre la révision des données :**
  - comparer l'instantané gelé (sha256 ci-dessus) à au moins 2 copies archivées de DIX.csv (Wayback Machine, une en 2023 ou avant, une en 2025), sur toutes les dates communes ;
  - si plus de 1 % des valeurs de `gex` diffèrent de plus de 1 %, **REJET pour données révisées** (biais de prévision impossible à exclure) ;
  - si aucune archive n'est trouvable, le dire et passer en **forward seul**.
- **Règle :** moteur et lecture de l'Exp 64, inchangés (commit 33b5a15). Le jour J est **à plat** si pct(GEX de J−1) > 2/3, où pct = rang de GEX(J−1) parmi les 251 valeurs précédentes. Sinon, la règle s'applique sans changement.
- **Données de décision :** `docs/agents/results/Exp-65_2026-10-08_daily.csv`, fenêtre **H = 2024-03-05 → 2026-08-18**, MNQ (le HOLDOUT a été consommé par l'Exp 65, mais le découpage par GEX n'a jamais été regardé). P1 a déjà été vu par le Chercheur et n'est rapporté qu'à titre d'information.
- **Critères (H, MNQ) :**
  - **PASS** si les quatre conditions sont remplies : Sharpe net filtré ≥ 0,8 ; MaxDD filtré ≥ −2 000 USD ; part du net venant des 5 meilleurs jours ≤ 50 % ; Sharpe filtré ≥ Sharpe non filtré (0,81).
  - **REJET** si MaxDD filtré < −2 500 USD, ou Sharpe filtré < 0,5, ou Sharpe filtré < non filtré.
  - **INCERTAIN** sinon.
  - **Rapporté sans effet :** SP500 → MES (même filtre), seuil 1/2 au lieu de 2/3, pire jour, jours < −1 000 USD.
- **Variantes :** 1 décisionnelle (seuil 2/3 fixé ici). Les 4 regards exploratoires de P1 sont comptés.
- **Si PASS :**
  1. Ombre forward : appliquer le filtre aux décisions de l'Exp 67 à partir de DIX.csv téléchargé avant 09:30 ET chaque jour. **Aucun runner n'est modifié** : calcul hors ligne.
  2. Rejouer la série filtrée par bootstrap par blocs dans `funded_futures_ev_sim.py` (règles Lucid Flex et Topstep 50K).
  3. Demander un « go » pour un challenge seulement si la borne basse de l'EV est > 0.

---
