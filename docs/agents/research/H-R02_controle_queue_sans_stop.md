# H-R02 — Contrôler la queue sans stop serré : taille par la queue conditionnelle + plafond d'exposition par rafale de marché

- **Auteur** : agent Chercheur, tâche T-010, 2026-10-06
- **Type** : gestion du risque (pas de nouveau signal) ; **matière première pour T-008 / Exp 51**
- **Classement** : 4/6 (révisé le 2026-10-06 après T-006/T-007 : nécessaire avant tout déploiement, mais les événements de queue sont rares, donc confirmable en forward seulement sur des années ; le rejet en échantillon reste rapide)
- **Statut** : non testée.

## Mécanisme

1. **Pourquoi pas de filtre « ne pas acheter pendant une cascade »** : la littérature et nos
   propres données disent que le rendement attendu de la fourniture de liquidité est **le plus
   élevé** pendant les épisodes de stress. Nagel (2012) montre que le rendement des stratégies de
   reversal (proxy du rendement de fourniture de liquidité) augmente fortement avec le VIX,
   parce que les fournisseurs contraints se retirent. Nos Exp 4 (vol élevée → PF bien meilleur) et
   Exp 41 (largeur de choc = 1,0 → PF 1,57 contre 1,13 ailleurs) vont dans le même sens. Un filtre
   coupe donc d'abord les meilleurs trades (c'est ce qui a tué l'Exp 40 : 56,7 % des trades exclus).
2. **Les cascades ne sont pas prévisibles trade par trade** : Garcia Seuma (2026), sur sept
   cascades BTC 2022-2025 (dont le 2025-10-10), ne trouve **aucun** indicateur d'alerte stable d'un
   événement à l'autre ; seule une compression de la variance du flux taker passe au niveau de la
   population, inutilisable comme alarme. Les chocs exogènes (droits de douane du 2025-10-10) ne
   préviennent pas.
3. **La queue vient de la simultanéité et de la taille, pas du signal** : le pire jour de l'Exp 50
   (−40,9 %, 10 % du notionnel par trade, 9 symboles) est un jour de positions concurrentes sur des
   altcoins avec des mèches profondes, cohérent avec la cascade du 2025-10-10 (BTC −14,5 %, certains
   altcoins −99 % en mèche sur Binance, en partie à cause de l'oracle interne de Binance et du
   dépeg USDe/wBETH/bnSOL). L'Exp 48 a laissé la piste : avec ≥ 3 autres pièces entrées à ±60 min,
   +0,003 %/trade (PF 1,00), contre +0,307 % (PF 1,88) pour les entrées isolées.

Conclusion de mécanisme : garder l'exposition aux rebonds de stress (c'est là qu'est l'espérance)
mais **plafonner la perte possible**, en dimensionnant chaque position sur sa queue conditionnelle et
en ne comptant qu'**une seule mise de risque par rafale de marché** (positions corrélées = un seul pari).

## Prédiction chiffrée et testable

Règle à fixer **avant** de regarder des résultats (paramètres tirés du budget, pas des données) :

- **Taille** : notionnel_i = min(33 % du compte, B / q_i), où B = 2 % du compte (perte tolérée par
  position dans le scénario de queue) et q_i = mouvement défavorable de 50 min au quantile 99,5 %
  estimé sur TRAIN, mis à l'échelle par realized_vol_30 au moment du signal.
- **Rafale** : si une position est ouverte et qu'un autre symbole signale dans les 60 min, la
  nouvelle position reçoit 0 (variante principale) ; budget de rafale = B.

Prédictions (pré-HOLDOUT + fenêtre Exp 50, rejet seulement ; sortie TIME50_NOSTOP, remplissage
intrabar réaliste, coût 0,05 % AR) :

1. Pire jour ≥ **−10 %** (contre −40,9 % pour 9 symboles à 10 %, −22,3 % pour SOL/BTC/ETH à 33 %).
2. Rendement net moyen par trade **conservé à ≥ 80 %** de la version sans plafond sur les trades
   gardés, et rendement annuel ≥ 50 % de la version sans plafond, avec un rapport rendement/MaxDD
   **supérieur**.
3. Rejet si le pire jour reste < −15 % ou si le rapport rendement/MaxDD ne s'améliore pas dans
   les deux moitiés chronologiques.

Pour le déploiement actuel « SOL seul », seule la règle de taille s'applique (un seul symbole).

## Pourquoi survivrait aux coûts réels à 500 CAD

Aucun coût ajouté : la règle supprime ou réduit des ordres, elle n'en crée pas. Limite : des tailles
plus petites rapprochent certains ordres du minimum pratique (frais fixes Solana, cf. H-R01 :
≈ 0,006 USD/swap, soit 0,03 % à 20 USD). Plancher proposé : ne pas trader une position < 20 USD.

## Comment tester

- **Rejet rapide (en échantillon)** : registre pré-HOLDOUT (2 549 trades) re-sorti en TIME50_NOSTOP
  + trades Exp 50 (`docs/experiment50_trades.csv`), harness unique (T-006), une seule variante
  principale préenregistrée, toutes variantes comptées. **Le Chercheur n'a calculé aucune variante
  de plafond** pour ne pas contaminer la préinscription d'Exp 51.
- **Mesurer la queue sur le prix du lieu d'exécution** : les mèches du 2025-10-10 sont en partie
  propres à Binance ; la queue sur Jupiter/Solana peut être différente (meilleure ou pire selon la
  liquidité des pools). Recouper avec T-012.
- **Confirmation** : forward paper sur le runner Jupiter avec la règle, après décision écrite.

## Anti-doublon

- Exp 40 (filtre choc BTC 15 min, REJECT), Exp 41 (filtre largeur de choc, REJECT au diagnostic) :
  ce sont des **filtres d'entrée** ; ici, **pas de filtre**, une taille et un plafond.
- Exp 48 (confirmation croisée, REJECT) : a testé un filtre de confirmation à W = 5 ; la piste
  W = 60 « plafonner l'exposition pendant les rafales » est **exactement** celle-ci, non testée.
- Exp 19, 26 (dimensionnement dynamique, risque par trade) : calibrés sur la distance de stop
  (3,6 % médiane), donc sur la convention de sortie non exécutable ; ici la taille vient de la queue
  sans stop.
- BACKLOG **T-008** (préenregistrer Exp 51) : cette fiche est une proposition pour T-008, pas un
  travail parallèle.

## Risques et limites

- Le quantile 99,5 % d'une queue estimé sur 3-4 ans contient 1 à 3 événements : erreur d'estimation
  énorme. Un plafond absolu (33 %) et un budget journalier restent nécessaires.
- Si les rebonds de stress portent l'essentiel de l'espérance (Nagel, Exp 41), le plafond de
  rafale peut couper une part disproportionnée du gain : c'est la prédiction 2 qui le dira.

## Sources (consultées le 2026-10-06)

- S. Nagel (2012), *Evaporating Liquidity*, Review of Financial Studies 25(7) : https://www.nber.org/papers/w17653
- R. M. Garcia Seuma (2026), *Where does the criticality live? Early-warning signals are event-heterogeneous across seven crypto-perpetual liquidation cascades*, arXiv:2607.27070 : https://arxiv.org/abs/2607.27070
- B. C. Lim (2026), *Two-Regime Liquidity Recovery After a Perpetual Futures Liquidation Cascade (Hyperliquid, 2025-10-10)* : https://journals.lincoln.ac.nz/index.php/JFDA/article/view/1395
- CoinGecko, *October 10 crypto crash explained* (chronologie, 19 G$ liquidés, BTC −14,5 %) : https://www.coingecko.com/learn/october-10-crypto-crash-explained
- Cointelegraph Research, *Order-book data on the USDe crash* (creux 21:20-21:21 UTC, dépeg après 21:36) : https://cointelegraph.com/research/exclusively-obtained-orderbook-data-reveals-details-about-usde-crash
- Amberdata, *How $3.21B vanished in 60 seconds* : https://blog.amberdata.io/how-3.21b-vanished-in-60-seconds-october-2025-crypto-crash-explained-through-7-charts
- A. Moreira, T. Muir (2017), *Volatility-Managed Portfolios*, Journal of Finance 72(4) (référence générale pour la taille inverse à la volatilité ; non consultée en ligne aujourd'hui, citée de mémoire).
- Internes : `docs/research_plan_status.md` Exp 4, 40, 41, 48, 50 ; `docs/agents/STATE.md` point 4.
