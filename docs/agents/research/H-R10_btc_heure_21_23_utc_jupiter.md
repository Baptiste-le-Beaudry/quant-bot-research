# H-R10 — Saisonnalité horaire du BTC (21:00-23:00 UTC) exécutée en cbBTC via Jupiter `/build`

- **Auteur** : agent Chercheur, tâche T-021, 2026-10-06
- **Levier** : (a) plus de trades sur la même plateforme à coût bas — une stratégie **autonome**, non corrélée au signal de creux, qui n'occupe le capital que 2 h par jour
- **Classement T-021** : 3/3 (gain possible moyen, probabilité faible à modérée, test très bon marché ; confirmation forward lente)
- **Statut** : non testée. Un calcul exploratoire hors période de publication a été fait (**exploratoire, ne compte pas**, détaillé plus bas).

## Mécanisme

Quantpedia (Vojtko et Javorská, 2022 ; données Gemini horaires 2015-10 → 2022-02) trouve que les
rendements du BTC des heures 22:00 et 23:00 UTC (barres qui **se terminent** à 22:00 et 23:00, donc
une position de 21:00 à 23:00) sont les seuls significatifs, statistiquement et économiquement.
Règle publiée : acheter à 21:00 UTC, vendre à 23:00 UTC ; ≈ +40 %/an brut, Calmar 1,79 ; vendredi
le meilleur jour. Leur explication : toutes les grandes places boursières sont fermées. Lien avec
la littérature actions (Lou, Polk et Skouras 2019) : une grande partie des primes de momentum se
gagne hors séance, quand les institutionnels ne tradent pas. Le mécanisme reste **faible** (pas de
modèle d'inventaire ou de flux identifié) : c'est surtout une régularité empirique.

**Non académique** : la même fenêtre circule chez les praticiens (scripts TradingView « BTC
seasonality », articles Quantpedia grand public). Risque : un effet très diffusé tend à disparaître.

## Contrôle exploratoire hors publication (ne compte pas)

Barres 1h Binance USDT-M (BTC, ETH : `data/*_1h_full.csv`) et 1m SOL rééchantillonnées, du
2022-02-04 au 2025-03-27 (après la fin de l'échantillon Quantpedia, avant le HOLDOUT crypto),
rendement log close-à-close, sans coût. Script : scratchpad de session `t021/btc_hour.py`,
`t021/sol_hour.py`.

| Symbole | Fenêtre 21-23 UTC, pb/jour | t | Par année (pb/jour) | Heure seule la plus forte |
|---|---|---|---|---|
| BTC | **+5,14** (n = 1 148) | **2,25** | 2022 −1,5 ; 2023 +6,2 ; 2024 +10,6 ; 2025 T1 +3,0 | barre 22-23 : +4,39 pb (1re de 24) |
| ETH | +4,84 | 1,62 | 2022 −5,7 ; 2023 +5,5 ; 2024 +14,5 | barre 22-23 : +4,43 pb (1re de 24) |
| SOL | +4,52 | 0,92 | — | barre 22-23 : +4,55 pb, mais 5 heures à ±4-8 pb |

Dérive moyenne de BTC sur la période ≈ 0,3 pb/heure : l'excès de la fenêtre ≈ +4,5 pb/jour.
Écart-type du rendement de la fenêtre ≈ 77 pb/jour (BTC). Compteur exploratoire : 3 symboles × 1
fenêtre (celle publiée, aucune autre essayée) + 3 tableaux horaires regardés.

## Prédiction chiffrée et testable

Règle figée (celle publiée, pas d'optimisation) : chaque jour, achat cbBTC à 21:00 UTC, revente à
23:00 UTC, 100 % du capital libre (non engagé par la stratégie de creux).

1. **Rejet en historique** sur la seule fenêtre jamais regardée pour cette hypothèse,
   **2025-04-01 → 2026-08-17** (barres Binance BTC 1m en cache ; cette fenêtre a été vue pour
   d'autres hypothèses, donc elle peut **rejeter**, pas confirmer) : moyenne brute de la fenêtre
   **≥ +2 pb/jour** et rendement net à 0,03 % AR **> 0**. Rejet si moyenne brute < 0.
2. **Forward** (enregistrement des cotations cbBTC `/build` à 21:00 et 23:00 UTC, sans argent) :
   coût AR médian réalisé ≤ 0,03 %, et moyenne nette > 0 après 6 mois. Avec σ ≈ 77 pb/jour, un
   excès de 4 pb demande ≈ 1 500 jours pour t = 2 : **la confirmation forward prendrait ~4 ans**,
   comme pour la stratégie de creux. Seul le coût se confirme vite.

## Pourquoi survivrait aux coûts réels

Brut ≈ +5 pb/jour hors publication ; coût cbBTC via `/build` coté ≈ 0,00-0,01 % AR (mesuré, H-R08),
plus ≈ 2 × 0,001-0,005 % de frais réseau à 116-350 USD : net attendu ≈ **+3 à +4 pb/jour**.
Avec `/order` (0,20 % AR), c'est 4 fois l'edge : **la stratégie n'existe que via `/build`**.

## Gain estimé

À 100 % du capital libre : 365 × 3,5 pb ≈ **+12 %/an** net, volatilité ≈ 15 %/an (Sharpe ≈ 0,8),
MaxDD probable −15 à −25 % (2022 aurait été ≈ −10 % net). En partage avec la stratégie de creux
(capital libre ≈ 70-90 % du temps à 21-23 UTC), ≈ **+8 à +10 %/an** en plus, en échantillon.
Après décote de diffusion (effet publié en 2022, largement copié) de 50 % : **+4 à +6 %/an**.
Probabilité a priori que l'effet persiste au niveau publié : **≈ 25 %**.

## Risque de doublon

- **Exp 12** (cellules volatilité × heure pour filtrer les creux) : conditionnement du signal de
  creux, ancien moteur ; pas une stratégie horaire autonome.
- **Strategy B** (momentum/breakout intraday, B1-B8) et **B_ROTATION** (rotation transversale
  journalière) : REJECT, mais aucune ne teste une fenêtre horaire fixe.
- **H-R06** (momentum de fin de séance ETF) : autre marché, autre mécanisme.
- Aucune trace de saisonnalité horaire crypto dans `docs/research_plan_status.md`, `REGISTRY.csv`
  ou `docs/strategy_b/` (recherche « hour », « seasonality », 2026-10-06).

## Sources (consultées le 2026-10-06)

- Quantpedia, *Are There Seasonal Intraday or Overnight Anomalies in Bitcoin?* : https://quantpedia.com/are-there-seasonal-intraday-or-overnight-anomalies-in-bitcoin/
- Quantpedia, fiche stratégie *Intraday Seasonality in Bitcoin* : https://quantpedia.com/strategies/intraday-seasonality-in-bitcoin
- D. Lou, C. Polk, S. Skouras (2019), *A tug of war: overnight versus intraday expected returns*, JFE : https://personal.lse.ac.uk/polk/research/TugOfWar.pdf
- Jupiter `/build` sans frais : https://developers.jup.ag/docs/swap ; frais `/order` : https://developers.jup.ag/docs/swap/fees
- Interne : `docs/agents/research/H-R08_univers_solana_cout_bas.md` (coût cbBTC mesuré).
