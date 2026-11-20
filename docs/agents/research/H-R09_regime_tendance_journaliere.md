# H-R09 — Régime de tendance journalière : ne pas (ou moins) acheter les creux intraday quand la tendance de plusieurs jours est baissière

- **Auteur** : agent Chercheur, tâche T-021, 2026-10-06
- **Levier** : (b) plus d'edge par trade, et surtout moins de queue (ce qui libère du levier c, traité par T-017)
- **Classement T-021** : 2/3
- **Statut** : non testée. Aucun calcul sur le registre de trades (volontaire, pour ne pas contaminer la préinscription).

## Mécanisme

- **Pour un filtre de tendance.** En crypto, la tendance à l'échelle du jour et de la semaine est
  le prédicteur le mieux documenté : Liu et Tsyvinski (2021, RFS) trouvent un momentum
  série-temporelle significatif aux fréquences journalière et hebdomadaire sur BTC, ETH et XRP
  (rendement moyen de la semaine suivante 11,2 % pour le quintile haut de la semaine passée contre
  2,6 % pour le bas, BTC). Padysak et Vojtko (2022) : acheter le BTC près de ses plus bas sur 10-50
  jours est « hasardeux » (drawdowns > 80 %), alors qu'il y a du momentum après les plus hauts. Un
  creux intraday pendant une tendance baissière de plusieurs jours est plus souvent le début d'une
  continuation que de la liquidité temporaire. Côté praticiens (**non académique**) : la règle
  « n'acheter les creux qu'au-dessus de la moyenne mobile 200 » de Connors/Alvarez est la
  modification la plus répandue des stratégies de mean-reversion (TradingView, Quantpedia).
- **Contre.** Nagel (2012) : le rendement du reversal (fourniture de liquidité) est le plus élevé
  en période de stress, qui coïncide souvent avec une tendance baissière. Exp 4 (volatilité élevée
  → meilleur PF) et Exp 41 vont dans ce sens. Le test doit donc pouvoir trancher **dans les deux
  sens**.
- **Pourquoi c'est une information nouvelle pour le modèle.** Les 23 features
  (`quant_bot/features/build.py`) regardent au plus 240 barres (4 h) : `dist_ema200_atr` est une
  EMA de 200 **minutes**, `hurst_120` 2 h. Aucune ne voit la tendance de plusieurs jours. L'Exp 24
  (tendance/range par `hurst_120`) n'est donc pas un doublon : elle mesurait la persistance sur
  2 h, pas la direction sur des jours.

## Prédiction chiffrée et testable

Variable fixée a priori (une seule, pas de grille) : **R = 1 si le close journalier UTC de la veille
est au-dessus de la moyenne simple des 20 closes journaliers précédents** (calculée à 00:00 UTC
avec des données entièrement antérieures, sur le symbole lui-même), sinon R = 0.

Population : trades du harness T-006 v1.1, règle déployée (sortie au temps 50 min sans stop),
SOL (puis BTC, ETH si H-R08 étape 1 passe), coût `jupiter_sol` mesuré, pré-HOLDOUT 2021-11 → 2025-04.

1. **Hypothèse principale** : net/trade(R = 0) < net/trade(R = 1) d'au moins **0,10 point**, même
   signe dans les deux moitiés chronologiques et sur la fenêtre Exp 50 (déjà vue : sert à rejeter).
2. **Conséquence chiffrée attendue si vrai** : avec R = 0 environ 40-50 % des trades (part de jours
   sous SMA20 sur la période, à mesurer), passer à **demi-taille quand R = 0** fait monter le
   net moyen pondéré de +0,107 % vers ≈ +0,13-0,15 %/trade et réduit le MaxDD du compte d'au moins
   **5 points** (−23,6 % → ≤ −18,6 %), le pire jour de 2022 et du 2025-10-10 tombant en R = 0.
3. **Rejet** si l'écart est < 0,05 point ou change de signe entre moitiés. **Résultat inverse**
   (R = 0 meilleur de ≥ 0,10 point, sens Nagel) : rapporté, pas exploité sans nouvelle
   préinscription.

Puissance : avec σ ≈ 1,6 %/trade (T-007) et ≈ 640 trades par groupe en échantillon, l'erreur
type d'un écart entre groupes ≈ 0,09 point ; une différence de 0,10 point n'est donc qu'à ~1,1 σ.
**Ce test peut rejeter, pas confirmer.** La valeur principale attendue est la baisse du MaxDD
(mesurable sur peu d'événements, mais ce sont ceux qui comptent).

## Pourquoi survivrait aux coûts réels

Le filtre ne crée aucun trade et n'ajoute aucun coût. Il change seulement la taille (ou supprime
des trades), donc il ne peut perdre que l'edge des trades retirés.

## Gain estimé

En compte (SOL seul, 33 %) : **+0 à +2 points/an** directement (moins de trades à pleine taille,
mais de meilleure qualité), et surtout **−5 à −8 points de MaxDD** si la prédiction 2 tient. C'est
ce qui permettrait à T-017 de justifier une taille supérieure à 33 % (levier c). Probabilité a
priori : **≈ 30 %** (littérature favorable sur la tendance journalière, mais Nagel, Exp 4 et Exp 24
indiquent que les creux en stress sont les meilleurs).

## Risque de doublon

- **Exp 24** (tendance/range `hurst_120` × volatilité) : REJECT comme filtre, aucune cellule
  négative ; échelle 2 h, ancien moteur (sortie au stop). Pas la même variable.
- **Exp 12, 19** (EV volatilité × heure ; taille par cellule) : autre conditionnement, ancien moteur.
- **H-R03 / Exp 51** (OI) et **H-R04** (creux résiduel) : autres variables ; à mettre dans le
  **même compteur de tests multiples** sur la même population.
- **Strategy B** (momentum/breakout intraday, REJECT) : signal autonome intraday ; ici la tendance
  sert seulement de conditionnement.
- Compteur : 1 variante (SMA20 journalière, demi-taille). Aucune autre longueur ne doit être
  essayée si celle-ci échoue.

## Pistes (b) examinées et non retenues en fiche

| Modification | Déjà testée ici ? | Raison de ne pas en faire une fiche |
|---|---|---|
| Sortie dépendante de la volatilité / durée adaptative | Exp 11 (trailing ATR), 43/43b (fenêtre), 45 (vol à l'entrée ne prédit pas le rendement : ρ ≈ 0,02), 46/46b (extension sélective, REJECT), + 16 variantes de sortie avant Exp 50 | Doublon et coût de tests multiples déjà élevé ; Leung et Li (2015) : le stop serré baisse la valeur d'une stratégie de retour à la moyenne, ce qui confirme seulement le choix « sans stop » déjà fait |
| Entrée échelonnée (ajouter si le prix baisse encore) | Exp 16 (entrées limit −0,10/−0,20/−0,30 % : pires sur BTC et ETH, sélection adverse) | Les trades qui retracent sont les moins bons : renforcer sur eux augmente la queue |
| Heure du jour / jour de semaine | Exp 12 (EV vol × heure : INVESTIGATE, ancien moteur) | Exploratoire (ne compte pas) : rendement horaire SOL 2022-02 → 2025-03 très bruité (±6 pb selon l'heure, t < 1 pour la fenêtre 21-23 UTC) ; gain attendu faible ; garder pour H-R10 en stratégie autonome sur BTC |
| Funding / basis au moment du creux | Exp 18/20/21 (funding_ma_3 en feature : INVESTIGATE, BTC mieux, ETH mitigé), B_FUNDING REJECT, Exp 51 (OI : INCERTAIN) | À enregistrer en forward avec T-023 (ΔOI) plutôt qu'à retester sur l'historique déjà fouillé |
| Taille selon la profondeur du creux | Exp 4 (vol élevée : PF bien meilleur mais n = 5-12), Exp 19 (taille par cellule EV : mitigé) | Recoupe H-R02 (taille par la queue) et T-017 |
| Aligner le label (10 min) sur la sortie réelle (50 min) | Prévu : Exp 53 (T-009) | Déjà en file ; c'est probablement le levier (b) le plus direct, à ne pas dupliquer |

## Sources (consultées le 2026-10-06)

- Y. Liu, A. Tsyvinski (2021), *Risks and Returns of Cryptocurrency*, Review of Financial Studies (NBER w24877) : https://www.nber.org/papers/w24877
- M. Padysak, R. Vojtko (2022), *Seasonality, Trend-following, and Mean Reversion in Bitcoin* (résumé Quantpedia) : https://quantpedia.com/trend-following-and-mean-reversion-in-bitcoin/
- S. Nagel (2012), *Evaporating Liquidity* : https://www.nber.org/papers/w17653
- T. Leung, X. Li (2015), *Optimal Mean Reversion Trading with Transaction Costs and Stop-Loss Exit* : https://arxiv.org/abs/1411.5062
- **Non académique** : filtre « moyenne mobile 200 » pour l'achat de creux (scripts TradingView, guides praticiens) : https://tradingstrategy.ai/docs/learn/mean-reversion.html ; https://pl.tradingview.com/script/khGKr44X-Hophop-Reversion-Strategy
- Internes : `quant_bot/features/build.py` ; `docs/research_plan_status.md` Exp 4, 11, 12, 16, 18-21, 24, 43-46, 50 ; `docs/agents/validation/power_jupiter_2026-10-06.md`.
