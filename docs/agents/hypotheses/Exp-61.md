# Exp 61 — Étendre le dip-buy Jupiter aux jetons Solana liquides — PRÉENREGISTREMENT

- **ID :** Exp 61 / `A-JUP-SOLTOKENS-001` (T-034, idée 2). Figé par ce commit, avant tout calcul. Juge : Validateur.
- **Univers (fixé a priori) :** JUP, JTO, PYTH, RAY, WIF, BONK — jetons natifs Solana listés en perpétuels USDT Binance (barres 1m via data.binance.vision ; BONK = 1000BONKUSDT), échangeables sur Jupiter contre USDC. Aucun ajout ni retrait après coup.
- **Étape 0 (coût) :** cotations Jupiter `/build` (sans signature) aller-retour à 116 USD, ≥ 20 cotations par jeton réparties sur ≥ 24 h. Jeton **exclu** si coût médian AR > 0,10 % (décidé avant le backtest).
- **Signal :** modèle REF de l'Exp 53 (walk-forward, BTC+ETH, label 10 min, seuil 0,70, filtres range/vol calibrés sur TRAIN comme pour SOL), appliqué aux features du jeton. Aucun réglage par jeton.
- **Exécution :** harness v1.2, entrée open suivant, sortie 50 barres sans stop, coût = coût médian mesuré à l'étape 0 + 0,01 USD/swap, une position par symbole.
- **Période :** du premier pli TEST où le jeton a ≥ 60 jours d'historique jusqu'au 2026-08-17 ; deux moitiés chronologiques par jeton.
- **Critères :** jeton **retenu** si net/trade > 0 dans les deux moitiés et ≥ 100 trades. **PASS** si ≥ 2 jetons retenus ET le CAGR du compte SOL+BTC+ETH+jetons retenus (500 CAD, 33 %/position, plafond 3 positions simultanées) > CAGR SOL+BTC+ETH sur la période commune, avec MaxDD ≥ −35 %. **REJET** si 0 jeton retenu. **INCERTAIN** sinon.
- **Variantes :** 1 décisionnelle. Rapporté sans effet : coût stress ×3, compte sans plafond de positions.
- **Si PASS :** nouvelle instance paper Jupiter avec les jetons retenus (préenregistrée).
