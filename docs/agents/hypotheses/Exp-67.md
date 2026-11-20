# Exp 67 — Forward papier de la règle « zone de bruit » sur MNQ (T-052) — PRÉENREGISTREMENT

- **ID :** Exp 67 / `F-NOISE-MOM-MNQ-FWD-001`. Demandé par l'auteur le 2026-10-09. Préenregistré par l'orchestrateur, figé par ce commit, avant le déploiement.
- **Origine :** Exp 65 INCERTAIN (HOLDOUT : Sharpe net 0,81, MaxDD −3 949 USD par contrat, gain concentré sur quelques jours).
- **But réaliste :** vérifier que la règle fonctionne correctement en direct (données, décisions, remplissages proches du backtest) et détecter un effondrement. **Ce forward ne peut pas prouver l'edge à court terme** : avec un Sharpe de 0,8, il faudrait environ 6 ans pour atteindre t ≥ 2.

## Règle

Identique à l'Exp 64/65 : moteur `scripts/agents/exp64_noise_momentum.py`, lecture de l'article figée au commit 33b5a15, 1 contrat MNQ **fictif**, coût de 2,22 USD aller-retour. Le prix de décision est le prix live disponible à HH:00/HH:30 ET. Le décalage entre le flux et l'heure de décision est enregistré à chaque décision.

## Données live

Flux de prix Nasdaq-100 à la minute, avec un délai maximal de 5 min. Il peut venir de Dukascopy USATECH, déjà utilisé par le forward Equity, ou d'une autre source gratuite documentée. Une décision dont la donnée est en retard de plus de 5 min est **sautée et journalisée**, jamais rattrapée.

## Ce qui est enregistré

Pour chaque décision : heure, prix, bornes, VWAP, position, latence. Pour chaque trade : entrée et sortie théoriques à l'open de la barre suivante, PnL net. Un rapport quotidien est produit.

## Règle d'arrêt et d'alerte (type D-05)

- **Alerte implémentation** si un des événements suivants se produit :
  - plus de 10 % des décisions sautées sur 20 jours ;
  - un écart de plus de 1 tick moyen entre le prix live et le prix Dukascopy rejoué le lendemain ;
  - un nombre de jours tradés hors de [30 %, 80 %] sur 40 jours ouvrables.
- **Alerte effondrement** si la perte cumulée du forward dépasse **−4 200 USD par contrat**, soit le 5e percentile du drawdown sur 1 an au bootstrap. Dans ce cas, la piste est fermée.
- **Revue :** à 3 mois, puis à 6 mois. Aucun argent réel n'est engagé sans un « go » explicite de l'auteur, et jamais avant 6 mois de forward sans alerte.
