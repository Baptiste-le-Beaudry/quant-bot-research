# Exp 56 — Momentum série-temporelle journalier long/cash sur BTC, ETH, SOL — PRÉENREGISTREMENT

- **ID :** Exp 56 / `B-TSMOM-D-001` (famille Strategy B, compteur B). Source : `docs/agents/research/H-R_MARKETS_strategies.md`, « Prédiction 1 » (Chercheur, T-021, Liu et Tsyvinski 2021). Préenregistré le 2026-10-07, figé par le commit qui ajoute ce fichier, avant tout calcul.
- **Règle (unique) :** chaque jour à 00:00 UTC, pour chaque actif, détenir 1/3 du capital si close(J−1)/close(J−8) − 1 > 0, sinon USDC. Closes journaliers 00:00 UTC construits depuis les barres 1m Binance en cache.
- **Coûts :** 0,05 % par aller-retour (principal) ; stress rapporté : 0,20 % AR pour BTC/ETH (cbBTC/WETH via `/order`).
- **Fenêtre de décision :** 2020-10-01 → 2025-03-27. La fenêtre 2025-04 → 2026-08 sert seulement à **rejeter** (rapportée séparément).
- **PASS** si : CAGR net ≥ +15 % ; MaxDD ≤ 0,6 × MaxDD du panier égal 1/3 détenu en continu ; Sharpe ≥ Sharpe du panier ; net > 0 dans chaque moitié chronologique.
- **REJET** si Sharpe < Sharpe du panier, ou si 2023-01 → 2025-03 rend < 50 % du panier. **INCERTAIN** sinon. Si la fenêtre 2025-04 → 2026-08 a un Sharpe < panier et un net < 0, un PASS devient INCERTAIN.
- **Variantes :** 1 décisionnelle (7 jours) ; rapportées sans effet : 14 et 28 jours.
- **Si PASS :** forward paper sur Jupiter (SOL, cbBTC/WETH via `/build`), préenregistré, et vérification de l'exécution réelle.
