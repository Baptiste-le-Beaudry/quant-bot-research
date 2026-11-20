# Exp 59 — Creux propre à l'actif vs creux de marché (H-R04) — PRÉENREGISTREMENT

- **ID :** Exp 59 / `A-JUP-RESID-001`. Source : `research/H-R04_creux_residuel_vs_marche.md`, prédiction reprise telle quelle, adaptée à l'univers Jupiter. Figé par ce commit, avant tout calcul.
- **Population :** trades de la règle déployée (sortie 50 barres sans stop, entrée open suivant, coût `/build`), SOL/BTC/ETH, populations P1 (pré-HOLDOUT 2021-11 → 2025-04) et P2 (entrées Exp 50) de l'Exp 57.
- **Variable :** R = r_15(symbole) − β·r_15(marché), marché = moyenne équipondérée des deux autres symboles, β estimé sur les 30 jours précédant le signal (données 1 min, strictement antérieures) ; r_15 = rendement des 15 min précédant le signal ; S = R / r_15. Variante rapportée sans effet : marché = BTC seul (pour SOL/ETH).
- **PASS** si le tercile S haut bat le tercile S bas d'au moins **0,10 point** de net/trade, même signe dans P1 et P2 et pour 3/3 symboles. **REJET** sinon. Résultat inverse (creux de marché meilleurs) : rapporté, non exploité sans nouvelle préinscription.
- **Variantes :** 1 décisionnelle (fenêtre 15 min, β 30 j, terciles). Aucune recherche de fenêtre.
- **Si PASS :** préinscrire un filtre (ou une taille ×2 / ×0,5 par tercile) en forward paper.
