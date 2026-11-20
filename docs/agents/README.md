# docs/agents : expériences 49 à 82 (en français)

*English: preregistrations, results and independent reviews for experiments 49-82. Files are in French; the one-page overview is [../EXPERIMENTS.md](../EXPERIMENTS.md).*

À partir d'octobre 2026, la recherche a été menée par rôles séparés : chercheur, développeur, validateur. Chaque expérience suit le même chemin :

1. **Préenregistrement** ([hypotheses/](hypotheses/)) : hypothèse, données, critères PASS/REJET. Il est commité **avant** tout calcul ; son commit figure dans le registre.
2. **Calcul et rapport** ([results/](results/)) : chiffres et application mécanique des critères. Les fichiers `*_criteria.json` donnent les critères évalués.
3. **Revue indépendante** ([validation/](validation/)) : reproduction, recherche de fuite de données, DSR/PBO, nombre de variantes testées. Seul le validateur peut nuancer ou confirmer un verdict.

| Fichier | Contenu |
|---|---|
| [REGISTRY.csv](REGISTRY.csv) | Une ligne par expérience : date, commit de préenregistrement, variantes testées, données, verdict, lien |
| [hypotheses/](hypotheses/) | Préenregistrements Exp 51 à 82 |
| [results/](results/) | Rapports de résultats (et quelques tâches T-xxx : correctifs, harness, collecte) |
| [validation/](validation/) | Revues du validateur et analyses de puissance |
| [research/](research/) | Fiches de recherche H-R : littérature et idées, dont beaucoup ont été écartées avant tout backtest. [research/INDEX.md](research/INDEX.md) les résume. |

Les fichiers de trades, les données brutes et les sorties volumineuses (CSV, modèles) ne sont pas publiés. Les chemins qui y renvoient dans les rapports sont donc absents du dépôt.

**Règle d'interprétation :** il n'y avait plus de période de test jamais vue (HOLDOUT). Un résultat historique peut donc seulement **rejeter** une idée ; la confirmation devait venir du forward papier, et aucune n'a été obtenue.
