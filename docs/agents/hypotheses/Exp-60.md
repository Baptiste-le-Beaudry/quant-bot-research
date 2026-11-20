# Exp 60 — Régime de tendance journalière (H-R09) — PRÉENREGISTREMENT

- **ID :** Exp 60 / `A-JUP-REGIME-001`. Source : `research/H-R09_regime_tendance_journaliere.md`, prédiction reprise telle quelle. Figé par ce commit, avant tout calcul.
- **Variable (une seule) :** R = 1 si le close journalier UTC de la veille du symbole est au-dessus de la moyenne simple des 20 closes journaliers précédents (données entièrement antérieures), sinon 0.
- **Population :** identique à l'Exp 59 (SOL/BTC/ETH, P1 et P2 de l'Exp 57, règle déployée, coût `/build`).
- **PASS** si net/trade(R=1) − net/trade(R=0) ≥ **0,10 point** dans P1 (deux moitiés chronologiques de même signe) et de même signe dans P2, et si la **demi-taille quand R=0** réduit le MaxDD du compte 500 CAD d'au moins 5 points sans baisser le CAGR de plus de 20 % (relatif), dans P1 et P2. **REJET** si l'écart < 0,05 point ou change de signe entre moitiés ou dans P2. **INCERTAIN** sinon. Résultat inverse (R=0 meilleur ≥ 0,10) : rapporté, non exploité.
- **Variantes :** 1 décisionnelle (SMA20, demi-taille). Rapporté sans effet : par symbole, exclusion complète R=0.
- **Si PASS :** préinscrire la demi-taille en forward paper (nouvelle instance).
