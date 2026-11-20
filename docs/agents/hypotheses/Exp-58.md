# Exp 58 — Stabilité du seuil de probabilité (0,60 → 0,85) — PRÉENREGISTREMENT (diagnostic)

- **ID :** Exp 58 / `A-JUP-THRESH-001`. Demandé par l'auteur le 2026-10-07. Figé par ce commit, avant tout calcul. **Diagnostic : n'adopte aucun seuil.**
- **Modèle :** REF de l'Exp 53 (walk-forward, réentraîné par pli, label 10 min), réutilisé tel quel (`scripts/agents/exp53_label50.py`). Pas le modèle déployé (entraîné sur toute la période, donc en échantillon partout).
- **Exécution :** identique à l'Exp 53 (harness v1.1, SOL/BTC/ETH, entrée open suivant, sortie 50 barres sans stop, coût `/build`, une position par symbole). Filtres range/vol recalculés sur TRAIN pour chaque seuil, comme dans le code déployé.
- **Seuils :** 0,60 ; 0,65 ; 0,70 ; 0,75 ; 0,80 ; 0,85 (6 valeurs, aucune autre). P1 / P2 comme l'Exp 53 (frontière 2025-04-01).
- **Rapporté :** trades, PF, net/trade, % plis net > 0, par symbole, par année, CAGR/MaxDD du compte 500 CAD 33 %.
- **Lecture fixée :** **STABLE** si, dans P1 et P2, le net/trade à 0,65 et 0,75 est à ± 0,05 point de 0,70 et du même signe. **FRAGILE** si un seuil voisin change de signe ou s'écarte de > 0,10 point. Un seuil « meilleur » ne serait adopté qu'après une nouvelle préinscription et le forward.
