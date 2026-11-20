# Exp 57 — Ajouter cbBTC/WETH (Jupiter /build) au dip-buy SOL à sortie au temps — PRÉENREGISTREMENT

- **ID :** Exp 57 / `A-JUP-UNIVERSE-001`. Source : `docs/agents/research/H-R08_univers_solana_cout_bas.md` (T-021). Préenregistré le 2026-10-07, figé par ce commit, avant tout calcul. Prérequis : harness v1.1 (correction C1 de la revue T-015).
- **Règle testée :** entrées du modèle existant pour BTC et ETH (mêmes populations que SOL), sortie au temps 50 barres **sans stop**, entrée open suivant, une position par symbole, 33 % du capital par position, compte 500 CAD.
- **Coûts :** route `/build` = quote mesurée ≈ 0,02 % AR + 0,01 USD fixe par swap (principal) ; stress `/order` 0,20 % AR rapporté.
- **Populations :** P1 pré-HOLDOUT (registre 2021-11 → 2025-04) ; P2 entrées Exp 50 (fenêtre déjà vue). Les deux servent à rejeter.
- **PASS** si, dans P1 **et** P2 : (a) net moyen par trade > 0 pour BTC et pour ETH au coût principal ; (b) CAGR du compte SOL+BTC+ETH > CAGR SOL seul ; (c) MaxDD du compte combiné ≥ −35 %. **REJET** si (a) échoue pour BTC et ETH dans P1 ou P2, ou si (b) échoue dans les deux. **INCERTAIN** sinon.
- **Variantes :** 1 décisionnelle ; stress `/order` rapporté.
- **Si PASS :** ajouter cbBTC/WETH via `/build` au forward Jupiter (nouvelle instance, préenregistrée), après vérification du risque MEV de `/build` dans les cotations enregistrées.
