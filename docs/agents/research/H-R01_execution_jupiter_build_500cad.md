# H-R01 — Exécution Jupiter sans frais de plateforme (`/build`) : le coût aller-retour réel à 500 CAD

- **Auteur** : agent Chercheur, tâche T-010, 2026-10-06
- **Type** : hypothèse d'exécution (coût), pas d'alpha nouveau
- **Classement** : 1/6 (gain attendu moyen, probabilité élevée, test peu coûteux)
- **Statut** : non testée. Chiffres de cette fiche = documentation officielle + **calcul exploratoire, ne compte pas**.

> **Mise à jour 2026-10-06 (après T-006 et T-007).** Le harness réaliste (branche `harness/v1`,
> `docs/agents/results/T-006_2026-10-06.md`, en échantillon, frais `/order`) donne pour la sortie
> à 50 barres : SOL +0,073 % brut → −0,007 % net (−0,024 % à 118,8 USD) ; BTC/ETH +0,136 % brut →
> −0,104 % net. Si « zéro frais sur `/build` » se confirme, on récupère ≈ 0,04 pt (SOL) et
> ≈ 0,20 pt (cbBTC/WETH) par aller-retour : BTC/ETH ≈ +0,1 %/trade, SOL ≈ +0,03 %, **en
> échantillon**. **Cela ne règle pas le problème de puissance** (T-007 : σ ≈ 1,6 %/trade, donc
> ~1 170 trades pour confirmer 0,11 %/trade). Ce qui compte : l'hypothèse se **vérifie vite et
> précisément** (T-007 : coût mesurable avec une bonne précision dès ~20 trades) et sert à toute
> stratégie exécutée sur Jupiter, H-R05 comprise.

## Mécanisme

Le backtest Jupiter (`docs/research_plan_status.md`, « Jupiter multi-year backtest ») applique les
frais de plateforme de Jupiter **Swap v2 `/order`** : 2 pb par swap SOL↔stable, 10 pb pour
cbBTC/WETH. La documentation développeur indique que ces frais sont prélevés sur `/order`
(chemin « managé » : Jupiter construit et envoie la transaction), mais que **Jupiter ne prend
aucun frais de protocole sur le chemin `/build`** (ex-Metis), où l'intégrateur construit, signe et
envoie la transaction lui-même (frais intégrateur `platformFeeBps` = 0 par défaut). En contrepartie,
le bot gère alors lui-même les frais de priorité, la simulation des compute units, l'atterrissage
et la protection MEV.

Le coût n'est pas un détail ici : dans le backtest Jupiter (en échantillon, sortie et univers
choisis après coup), le CAGR SOL+BTC+ETH passe de +21,9 % à 0,05 % AR fixe à +12,5 % à 0,10 %, et
tombe à +9,0 % avec les frais réels `/order` ; chaque 5 pb d'aller-retour ≈ 9 points de CAGR.
L'edge brut hors échantillon (Exp 50, sous-ensemble Jupiter) est ≈ 0,18 %/trade : les frais
`/order` sur cbBTC/WETH (0,20 % AR) en mangent plus que la totalité.

## Prédiction chiffrée et testable

À 500 CAD (≈ 351 USD au 2026-10-06 ; 33 % par position ≈ 116 USD) :

1. **Coût aller-retour réalisé via `/build`** (impact de prix vs prix mi-marché au signal +
   frais de base + priorité + écart entre cotation et exécution) **≤ 0,04 % pour SOL/USDC** et
   **≤ 0,08 % pour cbBTC/USDC et WETH/USDC**, en médiane, p90 ≤ 2× la médiane, hors jours de crise.
2. Le coût fixe par swap reste **< 0,01 % du notionnel** : frais de base 5 000 lamports
   (≈ 0,0006 USD à SOL = 120,4 USD) + priorité 0,00002-0,00005 SOL (≈ 0,002-0,006 USD) ⇒
   ≈ 0,002-0,006 % de 116 USD par swap. **Calcul exploratoire, ne compte pas.** Sur
   ~2 trades/jour (4 swaps), ≈ 3-10 USD/an, soit ≈ 1-3 % du capital/an : non négligeable,
   mais 5 à 20 fois moins que les frais `/order` sur cbBTC/WETH.
3. Rejet si : coût médian SOL > 0,08 % AR, ou taux d'échec/expiration de transactions > 5 %,
   ou glissement réalisé vs cotation > 0,05 % en médiane.

## Pourquoi survivrait aux coûts réels à 500 CAD

C'est précisément une réduction de coût. Cotations mesurées le 2026-10-06 (API publique,
**exploratoire, ne compte pas**) : USDC→SOL→USDC à 120 USD ≈ −0,01 % (bruit de cotation),
à 1 000 USD ≈ 0,00 % ; cohérent avec les mesures du 2026-10-05 (0,00-0,04 %). Le frais de
réseau Solana médian début 2026 est ≈ 0,0008 USD/transaction, moyenne ≈ 0,017 USD (tirée par une
minorité qui paie de grosses priorités).

## Comment tester

- **Rejet rapide (sans argent)** : enregistrer à chaque signal du runner Jupiter paper la
  cotation `/build` (entrée et sortie) en plus de `/order`, et un frais de priorité estimé
  (`getRecentPrioritizationFees`, p50/p75). Comparer au prix OKX/Binance du signal (lien avec
  T-012). 2 semaines suffisent pour la prédiction 1 sur la composante prix.
- **Confirmation (argent réel, nécessite une décision écrite)** : 20-40 micro-swaps réels de
  10-20 USD depuis un serveur hors États-Unis (conditions Jupiter ; cf. STATE point 7), mesure
  de l'atterrissage, du glissement réalisé et des frais payés. Le Chercheur ne le lance pas.
- Livrer les coûts mesurés au harness d'exécution (T-006) comme paramètres par plateforme.

## Anti-doublon

- `docs/BROKER_OPTIONS_QUEBEC.md` (2026-10-05) et STATE point 5 ne connaissent que les frais
  `/order` (2/10 pb). Aucune mesure `/build` ni de frais de priorité n'existe dans
  `docs/research_plan_status.md` ni dans `REGISTRY.csv`. Recoupe T-004 (Plateformes : « frais
  officiels à reconfirmer ») et T-006 (harness) : à transmettre, pas à dupliquer.

## Risques et limites

- Sans le chemin managé, risque MEV (sandwich) et transactions qui n'atterrissent pas en
  congestion, justement pendant les cascades où le bot achète. Le coût de crise doit être
  mesuré séparément (le 2025-10-10, l'écart de prix médian sur Hyperliquid a atteint 9,4 pb,
  p95 87,5 pb).
- La documentation dit que l'API Metis v1 est dépréciée au profit de `/build` v2 ; la règle
  « zéro frais » doit être reconfirmée sur la page en vigueur au moment du déploiement.
- Réduire le coût n'ajoute pas d'edge : la sortie au temps garde son risque de queue (H-R02).

## Sources (consultées le 2026-10-06)

- Jupiter, *Swap API fees* (`/order` : 2/5/10 pb selon la paire) : https://developers.jup.ag/docs/swap/fees
- Jupiter, *Add fees to swap* (« By default, there are zero protocol fees on Jupiter Swap », chemin construit par l'intégrateur) : https://developers.jup.ag/docs/swap/add-fees-to-swap
- Jupiter, *Metis to /build migration* (l'intégrateur construit, simule, signe, gère priorité et MEV) : https://developers.jup.ag/docs/swap/migration/metis-to-build
- Jupiter, *Limit orders* (Trigger V2 : 0,03 % stable / 0,10 % autres + routage 0-0,5 % → plus cher qu'un swap `/build`) : https://docs.jup.ag/user-docs/trade/spot/limit-orders
- Sanctum, *Solana fees explained* et synthèses 2026 (médiane ≈ 0,0008 USD, moyenne ≈ 0,017 USD) : https://sanctum.so/blog/solana-transaction-fees-explained-why-so-low ; https://data80hd.substack.com/p/do-you-care-about-transaction-fees
- B. C. Lim (2026), *Two-Regime Liquidity Recovery After a Perpetual Futures Liquidation Cascade*, J. of Financial Data Analytics : https://journals.lincoln.ac.nz/index.php/JFDA/article/view/1395
- Cotations : `https://lite-api.jup.ag/swap/v1/quote` et `/price/v3`, 2026-10-06 (script exploratoire dans le scratchpad de session, non versionné).
