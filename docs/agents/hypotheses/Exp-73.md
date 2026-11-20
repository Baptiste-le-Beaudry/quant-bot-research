# Exp 73 — MNQ zone de bruit contre des entrées au hasard — PRÉENREGISTREMENT

- **ID :** Exp 73 / `F-NOISE-MOM-MNQ-NULL-001` (T-067). Demandé par l'auteur le 2026-10-11, après la critique d'une autre IA (point 5 : « test contre le hasard »). Préenregistré le 2026-10-11 par l'orchestrateur, figé par ce commit, **avant tout calcul**. Juge : Validateur.
- **Nature :** diagnostic. Le HOLDOUT indices est déjà consommé (Exp 65). Ce test ne crée pas de nouvelle preuve hors échantillon. Il dit seulement si le gain de l'Exp 65 se distingue du hasard, à durées et à frais égaux.
- **Aucun effet sur le forward Exp 67 :** il continue tel quel, avec ses propres revues (D-07).

## Entrées

- Trades réels : `docs/agents/results/Exp-65_2026-10-08_trades.csv`, lignes `future == MNQ`, sur la fenêtre **H** (2024-03-05 → 2026-08-18) et sur **H-post** (≥ 2024-11-27). On ne relance pas la règle.
- Barres 1 min : `data/indices/NASDAQ100_1m.csv`, même lecture que `scripts/agents/exp64_noise_momentum.py`. Mêmes conventions : barre 0 = 09:30 ET, exécution à l'ouverture de la barre, multiplicateur 2, coût de 2,22 USD aller-retour par trade.
- Statistique : **PnL net total en USD** sur la fenêtre. Les jours sans trade comptent pour 0.
- Graine `20261011`, **10 000 tirages** par nul.

## Nuls

### Nul A (décisionnel) — direction au hasard

- Chaque trade réel garde son jour, sa barre d'entrée et sa barre de sortie, donc sa durée et son coût.
- Seule la direction est tirée au hasard : long avec une probabilité q, short sinon. q est la part de trades longs observée sur la fenêtre.
- PnL d'un trade tiré = côté × (prix de sortie − prix d'entrée) × 2 − 2,22. On utilise les mêmes prix d'entrée et de sortie que le CSV.
- Ce nul teste si le **signal de direction** apporte quelque chose au-delà de la tendance du marché et de la structure des sorties.

### Nul B (rapporté, critère secondaire) — moment et direction au hasard

- Le nombre de trades est conservé jour par jour.
- Chaque trade tiré reçoit :
  - une barre d'entrée tirée uniformément parmi les barres d'exécution possibles de la règle (ouverture de la barre suivant une décision HH:00/HH:30, de 10:00 à 15:30 ET) ;
  - une direction long avec une probabilité q ;
  - une durée tirée parmi les durées réelles (barre de sortie − barre d'entrée) de la fenêtre.
- La sortie se fait à l'ouverture de min(entrée + durée, barre 15:59). Coût : 2,22 USD.
- Les trades d'un même jour peuvent se chevaucher. C'est accepté et documenté.

## Critères (fixés)

On note p_A = (1 + nombre de tirages avec un PnL net ≥ le PnL réel) / (1 + 10 000) sur **H**. p_B se calcule de la même façon.

| Verdict | Condition |
|---|---|
| **SIGNAL** | p_A ≤ 0,05 **et** p_B ≤ 0,05 sur H, **et** p_A ≤ 0,10 sur H-post |
| **HASARD** | p_A > 0,20 sur H |
| **INCERTAIN** | sinon |

**Rapporté sans effet :**
- p_A et p_B sans le meilleur jour (2025-04-09) et sans les 5 meilleurs jours, calculés en retirant ces jours du réel **et** des tirages ;
- les mêmes nuls sur la période P1 (avant le HOLDOUT), à partir des trades de l'Exp 64 si le CSV existe, sinon non calculés ;
- les quantiles 50/95/99 % des distributions nulles.

## Conséquences

- **SIGNAL :** le gain MNQ n'est pas un artefact de la tendance ni des sorties. Le verdict reste INCERTAIN (MaxDD, Exp 71), mais la revue forward de janvier 2027 est maintenue sans changement.
- **HASARD :** la direction n'apporte rien. On le note dans STATE et dans le dossier MNQ. Le forward continue, puisqu'il est gratuit, mais aucune démarche funded ou réelle ne se fera sur la base de l'Exp 65.
- **INCERTAIN :** rien ne change.

## Variantes comptées

1 décisionnelle (nul A sur H). Nul B, H-post, les jours retirés et P1 sont rapportés.
