# Exp 68 — Tendance multi-horizons long/cash SOL/BTC/ETH (H-R15-A) — PRÉENREGISTREMENT

- Préenregistré le 2026-10-09 par l'orchestrateur, repris **sans modification** de la proposition du Chercheur (`research/H-R15_nouvelles_strategies.md` §5.1, commit 2742076), figé par ce commit avant tout calcul sur P2. Juge : Validateur.

- **Règle (unique, celle de Zarattini-Pagani-Barbon 2025, simplifiée et figée) :**
  - Closes journaliers à 00:00 UTC (Binance, cache 1 min).
  - Pour chaque actif i et chaque horizon n ∈ {5, 10, 20, 30, 60, 90, 150, 250, 360} : état = 1 si close > max(close des n jours précédents) ; retour à 0 si close < (max + min)/2 des n derniers closes (aujourd'hui inclus) ; sinon, l'état est conservé.
  - Signal_i = moyenne des 9 états.
  - Poids w_i = signal_i × min(1 ; 0,25/σ_i)/3, où σ_i = écart-type des rendements journaliers sur 60 jours × √365. Somme des poids ≤ 1 ; le reste en USDC.
  - Décision à la clôture J, détention sur J+1.
  - Code de référence : `docs/agents/research/H-R15_scripts/trend.py` (`run_spot`), à reprendre tel quel.
- **Coût :** 0,05 % AR sur la rotation (principal) ; stress à 0,20 % AR pour BTC/ETH, rapporté. **Rendement du cash = 0 pour la décision** ; avec la série USDC Kamino (T-029), rapporté.
- **Périodes :**
  - P1 = 2020-10-01 → 2025-03-27 : en échantillon, **déjà vu par le Chercheur** (§3.1), rapporté sans effet.
  - **P2 = 2025-03-28 → 2026-08-17 : décisionnelle.** C'est après publication pour l'article. Elle a été vue par l'Exp 56 pour une autre règle, et **le régime y est connu (panier −14 %/an)** : biais possible en faveur d'une règle long/cash, que les critères compensent en exigeant un Sharpe et pas seulement un « moins pire que le panier ».
- **Critères (P2) :**
  - **PASS** si les quatre conditions sont remplies : Sharpe net ≥ 0,5 ; MaxDD ≥ −15 % ; CAGR net > 0 ; Sharpe > celui du panier 1/3 détenu.
  - **REJET** si Sharpe net ≤ 0 ou MaxDD < −20 %.
  - **INCERTAIN** sinon.
  - **Rapporté sans effet :** par actif, par année, stress de coût, rendement du cash, rotation, nombre de swaps, pire jour.
- **Variantes :** **1 décisionnelle.** Compteur de la famille momentum série-temporelle crypto : Exp 56 (3) + exploratoires T-054 (6 configurations de tendance, 3 tv au comptant, 2 univers) + 1.
- **Si PASS :** forward papier 3 mois (contrôle d'implémentation, sans argent), cotations `/build` réelles à chaque rebalancement. Le « go » argent réel revient à l'auteur. **Si REJET :** famille fermée pour le capital propre, et H-R15-B tombe avec.

