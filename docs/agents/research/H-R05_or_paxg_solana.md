# H-R05 — L'or accessible à 500 CAD : PAXG sur Solana/Jupiter comme lieu d'exécution (écart de base et creux intraday)

- **Auteur** : agent Chercheur, tâche T-010, 2026-10-06
- **Type** : nouveau marché accessible + mécanisme de retour à la valeur
- **Classement** : 2/6 (révisé le 2026-10-06 après T-007 : si l'écart de base existe, c'est un trade de faible variance, donc vérifiable en quelques semaines de cotations, sans argent ; probabilité faible, capacité minuscule)
- **Statut** : non testée. Cotations ci-dessous = **calcul exploratoire, ne compte pas**.

## Contexte

La sonde de faisabilité du 2026-10-05 (`docs/research_plan_status.md`, « Feasibility probe —
commodities ») conclut que l'or a une volatilité 1 min du niveau de BTC (ATR médian 0,044 %) et un
coût/ATR 3 à 9 fois meilleur que la crypto **sur Dukascopy**, mais il n'existe pas de lieu
d'exécution légal et bon marché pour un résident du Québec à 500 CAD : micro-or CME trop gros, CFD
offshore illégaux (AMF), `docs/BROKER_OPTIONS_QUEBEC.md`. Les jetons d'or adossés sur Solana
comblent ce trou : PAXG (Paxos, 1 once troy LBMA par jeton, intégré à Jupiter via Sunrise/Wormhole)
et XAUt0 (Tether Gold), négociables 24/7 sur le même circuit que le bot Jupiter.

Cotations Jupiter du 2026-10-06 (USDC→jeton→USDC, prix seul, hors frais) :

| Jeton | 120 USD | 1 000 USD | Liquidité indexée par Jupiter |
|---|---|---|---|
| PAXG | 0,009 % | 0,015 % | ≈ 222 k USD |
| XAUt0 | 0,041 % | 0,057 % | ≈ 241 k USD |
| SOL (référence) | ≈ 0 % | 0,000 % | ≈ 990 M USD |

Frais Jupiter : 10 pb par swap sur `/order` (catégorie « everything else »), 0 sur `/build`
(cf. H-R01). Avec `/build`, l'aller-retour PAXG ≈ 0,01-0,02 % à notre taille, soit un coût/ATR
1 min ≈ 0,3-0,5, comparable à Dukascopy.

## Mécanisme

**(a) Écart de base (principal)** : le pool PAXG sur Solana est mince (≈ 85 k USD de volume sur
une heure, très peu d'acheteurs « organiques » d'après les statistiques Jupiter). Un ordre de
quelques milliers de dollars déplace le prix du jeton par rapport à l'or au comptant ; l'arbitrage
inter-chaînes et CEX↔DEX est lent (pont Wormhole, rachat Paxos fermé aux Canadiens depuis 2023).
L'écart doit se refermer : c'est de la fourniture de liquidité pure, au sens de Nagel (2012), sur un
marché où les arbitrageurs sont contraints.

**(b) Creux intraday de l'or (secondaire)** : transposer la logique « creux en volatilité élevée »
à l'or. Base académique plus faible : le mécanisme crypto est un effet de sélection du modèle
(rapport de transférabilité) et l'Exp 32 (indices, CFD Dukascopy) a échoué ; l'or a moins de levier
de détail que la crypto, donc moins de cascades.

## Prédictions chiffrées et testables

(a) Sur un enregistrement forward (cotation Jupiter PAXG toutes les minutes vs prix XAU au comptant,
Pyth ou Dukascopy), en retirant la base médiane glissante sur 24 h :
1. Les écarts négatifs (jeton moins cher) au-delà de 2× l'écart absolu médian se referment d'au
   moins 50 % en 60 min dans **≥ 70 %** des cas.
2. Le gain moyen d'un achat à l'écart et d'une revente à 60 min (ou à la fermeture de l'écart) est
   **≥ 0,10 %** net du coût `/build` mesuré, avec **≥ 3 occurrences par semaine** de marché ouvert.
3. Rejet si l'une des deux échoue après 6 semaines d'enregistrement.

(b) Sur données Dukascopy XAU 1 min (rejet en échantillon seulement) : un modèle entraîné selon le
gabarit A-Equity donne un rendement brut à 50 min ≥ 0,05 %/trade dans les deux moitiés. Rejet sinon.

## Pourquoi survivrait aux coûts réels à 500 CAD

Pour (a), l'aller-retour à 116 USD (33 % du compte) est ≈ 0,01-0,02 % + frais Solana < 0,01 %,
donc un écart de 0,10 % laisse une marge. La capacité est minuscule (quelques centaines de dollars
avant de déplacer soi-même le pool) : c'est un avantage relatif d'un petit compte, pas un défaut.
Pendant le week-end (or fermé, PAXG ouvert), l'écart n'est pas mesurable : ne pas trader.

## Comment tester

- (a) Écrire un enregistreur sur le modèle de `hyperliquid_spread_logger.py` (cotations seulement,
  aucun ordre, aucune clé) dans un répertoire neuf. Coût : un processus léger. 6 semaines.
- (b) Seulement si l'utilisateur relance la piste « matières premières » : le spec préenregistré
  prévu par la sonde du 2026-10-05 s'applique, PAXG devenant le lieu d'exécution visé.

## Anti-doublon

- Aucune stratégie or/matières premières n'a été testée (sonde de faisabilité seulement,
  2026-10-05). Aucun travail sur des jetons d'actifs réels on-chain.
- Les jetons d'actions xStocks (Backed) ne sont **pas** accessibles aux résidents du Canada : écartés.

## Risques et limites

- Paxos a quitté le Canada en 2023 : un résident canadien ne peut pas faire racheter ses PAXG
  contre de l'or ou des USD chez Paxos ; la sortie passe par le marché (DEX, ou Wealthsimple/Kraken
  qui listent PAXG). Risque émetteur et pont (version Solana via Wormhole).
- La légalité d'utiliser un DEX depuis le Québec reste une inférence (rien ne l'interdit, cf.
  `BROKER_OPTIONS_QUEBEC.md`), à confirmer par T-004.
- Les bots d'arbitrage Solana sont rapides ; s'ils ferment l'écart en quelques blocs, la prédiction
  (a) échoue vite : c'est le scénario le plus probable.
- Fiscalité : chaque swap est une disposition imposable (comme le reste du circuit Jupiter).

## Sources (consultées le 2026-10-06)

- Crypto Briefing, *Jupiter integrates PAX Gold on Solana via Sunrise DeFi* : https://cryptobriefing.com/jupiter-pax-gold-solana-sunrise-defi/
- DexPaprika, pools PAXG/XAUt0 sur Solana (volumes de quelques k USD à 33 k USD/24 h) : https://dexpaprika.com/solana/pool/9xSuwrd6mVgcpW2G98MBPLCQUJic4RBxfgFauVayu1Rf
- Paxos, *Paxos withdrawal from Canada* : https://support.paxos.com/articles/3570242566-paxos-withdrawal-from-canada
- Wealthsimple, *What is Pax Gold?* (PAXG offert aux clients canadiens) : https://help.wealthsimple.com/hc/en-ca/articles/6956666645275
- Kraken, *Getting started with xStocks* (non disponible au Canada) : https://support.kraken.com/ca/articles/getting-started-with-xstocks ; Nansen, *xStocks explained* : https://nansen.ai/post/what-is-xstocks
- Jupiter, *Swap API fees* : https://developers.jup.ag/docs/swap/fees
- S. Nagel (2012), *Evaporating Liquidity* : https://www.nber.org/papers/w17653
- Cotations : `https://lite-api.jup.ag/swap/v1/quote`, `/tokens/v2/search` (PAXG mint `5GgRAEmv8ZxF2PR5hY72Qs5x1bnQ6UK2RbTPoqJ3wSwW`, XAUt0 mint `AymATz4TCL9sWNEEV9Kvyz45CHVhDZ6kUgjTJPzLpU9P`), 2026-10-06.
- Interne : `docs/research_plan_status.md` « Feasibility probe — commodities » et Exp 32.
