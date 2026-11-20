# Exp 66 — Effets d'heure en crypto (SOL/BTC/ETH), découverte P1 → confirmation P2 — PRÉENREGISTREMENT

- **ID :** Exp 66 / `T-HOUR-001` (T-048). Préenregistré le 2026-10-09 par l'orchestrateur, figé par ce commit, **avant tout calcul**. Juge : Validateur.
- **Mécanisme supposé :** certaines heures concentrent des flux récurrents et prévisibles : ouverture et clôture US (flux des ETF spot BTC/ETH), règlements de funding perp (00/08/16 UTC) et fixings. Un rendement moyen positif et stable sur une heure fixe serait capturable à faible coût sur Jupiter `/build` (≈ 0,02 % AR).
- **Indépendant de A :** aucune utilisation du modèle RF ni des signaux de A.

## Protocole

- **Données :** barres 1 min Binance SOLUSDT, BTCUSDT, ETHUSDT, rendements d'heure pleine en UTC (open de HH:00 → open de HH+1:00).
- **P1 (découverte) :** 2021-01-01 → 2024-12-31. **P2 (confirmation) :** 2025-01-01 → 2026-08-17. P2 a déjà été vu pour d'autres stratégies, mais jamais heure par heure. Il sert ici à rejeter.
- **Sélection, uniquement sur P1, mécanique :**
  1. Pour chacune des 24 heures UTC, calculer le rendement net moyen, regroupé sur les 3 symboles, avec un coût de 0,02 % AR + 0,01 USD par swap sur 116 USD.
  2. Retenir **les 2 heures** au rendement net moyen le plus élevé, à condition que chacune ait **t ≥ 2,5** en P1. Un t ≥ 2,5 plutôt que 2 tient compte des 24 heures testées.
  3. Si aucune heure ne satisfait la condition : **REJET**, sans regarder P2.
- **Règle de trading :** chaque jour, acheter SOL, BTC et ETH (33 % du compte chacun) à l'open de l'heure retenue, revendre à l'open de l'heure suivante. Pas de stop, aucune autre condition.

## Critères sur P2 (fixés)

- **PASS** si :
  - le net moyen par trade > 0 pour **chacune** des heures retenues ;
  - le t regroupé ≥ 2 ;
  - le net moyen est > 0 sur au moins 2 symboles sur 3 ;
  - le CAGR du compte 500 CAD ≥ 10 % ;
  - le MaxDD ≥ −25 %.
- **REJET** si le net moyen regroupé en P2 est ≤ 0.
- **INCERTAIN** sinon.
- **Rapporté sans effet :** tableau des 24 heures en P1 et en P2, avec rendement net et t ; stabilité par année ; heures de funding ; jours de semaine contre week-end ; coût `/order`.

## Variantes comptées

24 heures examinées en P1, soit **2 retenues mécaniquement** ; 1 seule règle décisionnelle en P2.

## Si PASS

Instance paper sur le serveur forward, préenregistrée, avec une règle d'arrêt de type D-05.
