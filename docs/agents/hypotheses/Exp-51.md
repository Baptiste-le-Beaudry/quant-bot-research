# Exp 51 — Creux de déleveraging (OI en baisse) vs nouveaux shorts (OI en hausse) — PRÉENREGISTREMENT

- **ID :** Exp 51 / `A-CRYPTO-OI-DELEVER-001`. Source : fiche `docs/agents/research/H-R03_creux_deleveraging_open_interest.md` (Chercheur, T-010).
- **Préenregistré :** 2026-10-06 par l'orchestrateur, figé par le commit qui ajoute ce fichier, **avant tout calcul d'OI sur des trades**. Juge : Validateur.
- **Nature :** diagnostic **en échantillon**, qui ne peut que **rejeter**. Un PASS ne vaut pas confirmation : il ouvre seulement un forward où ΔOI est enregistré à chaque signal.

## Hypothèse et mécanisme

Parmi les creux que le modèle sélectionne, ceux qui s'accompagnent d'une baisse de l'open interest (ventes forcées, déleveraging, flux non informationnel) rebondissent davantage que ceux où l'OI monte (ouverture de shorts, flux potentiellement informé).

## Variable (fixée)

ΔOI_15 = `sum_open_interest(t_ref) / sum_open_interest(t_ref − 15 min) − 1`, Binance USDT-M, archive `data.binance.vision` (`futures/um/daily/metrics`), où t_ref = dernière valeur dont l'horodatage de **disponibilité** est ≤ heure du signal (`merge_asof` backward). La sémantique de `create_time` et la latence de publication sont établies **avant** le calcul ; si elles restent incertaines, on applique une garde supplémentaire de 5 min (conservateur). Fenêtres 5 et 60 min : **rapportées seulement**, sans pouvoir changer le verdict.

## Populations et exécution

1. **Principale :** registre pré-HOLDOUT de la référence (`docs/multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv`, 2 549 entrées, 2021-11-30 → 2025-04-07).
2. **Secondaire :** entrées walk-forward de l'Exp 50 (`docs/experiment50_trades.csv`, fenêtre HOLDOUT déjà vue).

Sortie : **au temps, 50 barres, sans stop**, via le harness v1 (`quant_bot/execution_harness`, branche `harness/v1`), entrée à l'open de la barre suivante. Métrique : rendement brut moyen par trade (le coût est identique entre terciles et ne change pas l'écart). Terciles calculés **par symbole** (bornes sur la population du symbole), puis regroupés.

## Critères (fixés)

- **C1 :** moyenne(tercile ΔOI le plus négatif) − moyenne(tercile le plus positif) ≥ **+0,15 pt**, population principale.
- **C2 :** écart de même signe dans les **deux moitiés chronologiques** de la population principale.
- **C3 :** écart de même signe pour **≥ 5/9 symboles** et pour **SOL, BTC et ETH**.
- **PASS** = C1 et C2 et C3. **REJET** = sinon. La population secondaire est rapportée ; si son écart est de signe opposé, le PASS est rétrogradé en **INCERTAIN**.
- Rapporté sans effet sur le verdict : bootstrap par blocs de jours de l'écart (IC 90 %), part des trades < −5 % par tercile (lien H-R02).

## Variantes comptées

1 variante décisionnelle (ΔOI_15) + 2 rapportées (ΔOI_5, ΔOI_60) = **3** au compteur.

## Si PASS

Enregistrer ΔOI (Binance et OKX) à chaque signal dans le forward, **sans filtrer**, et préenregistrer un test forward séparé (avec analyse de puissance : un écart ≥ 0,4 pt est nécessaire pour un verdict en moins d'un an, cf. T-007).
