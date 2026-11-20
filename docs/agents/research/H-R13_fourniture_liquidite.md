# H-R13 — Fournir la liquidité au lieu de la prendre (JLP, CLMM, carnets on-chain) — T-041

**Agent :** Chercheur. **Date :** 2026-10-08. **Branche :** `research/jlp`.
Recherche web et calculs légers seulement. Aucun compte, aucune transaction, aucune signature. Les seuls appels réseau sont des lectures publiques : DefiLlama (prix, TVL, frais, rendements), API publique Jupiter Perps (`perps-api.jup.ag`), cotation Jupiter `lite-api` (lecture), RPC Solana public, API publique Orca, historique public du funding Hyperliquid.
**Tous les calculs de cette fiche sont exploratoires et ne comptent pas.** Ce sont des séries **en échantillon** (2024-01 → 2026-10-07), sans confirmation forward. Les scripts sont dans `docs/agents/research/H-R13_scripts/` ; les données téléchargées ne sont pas commitées.
Change utilisée : 500 CAD ≈ **353 USD** (même taux implicite que T-029, ≈ 1,417 CAD/USD).

## Anti-doublon

- `INDEX.md`, « Pistes écartées a priori » : la **liquidité concentrée** (Loesch et al. 2021 ; Milionis et al.) et l'**arbitrage de funding** (perps non accessibles, ≈ 5 %/an) y sont déjà écartés. Ici, je ne fais que **chiffrer** le CLMM sur Solana avec des données on-chain de 2026 ; je ne rouvre pas la piste funding.
- `venues/IDLE_YIELD_2026-10-07.md` (T-029) : Jupiter Lend USDC ≈ **4,1 %/an**, gain central ≈ 19 CAD/an. C'est le **plancher** auquel chaque option est comparée. Drift y est déjà exclu (exploit du 2026-04-01).
- `venues/VENUES_500CAD_2026-10-06.md` : CGU Jupiter (Canada non exclu, É.-U. exclus, VPN interdit, serveur au Canada obligatoire) ; **Hyperliquid exclu pour le capital propre**.
- `research_plan_status.md`, `JOURNAL.md` : aucun travail antérieur sur JLP. Exp 16 (entrées limit −0,10/−0,20/−0,30 % moins bonnes, sélection adverse) sert de référence interne pour l'option 3. Le JOURNAL du 2026-10-07 22:00 (T-041 retenu, arbitrage de funding sur perps CEX écarté) est respecté.

## Résumé en une phrase

JLP n'est pas un « edge de fourniture de liquidité » exploitable aujourd'hui. Non couvert, c'est un panier crypto à ≈ 0,6 de bêta, avec un portage qui a fondu (≈ 52 %/an en 2024, ≈ 18 % en 2025, **≈ 8-9 %/an en 2026**). Couvert avec les seuls perps à peu près accessibles (Jupiter Perps), le net de 2026 retombe à **≈ 1-3 %/an**, sous Jupiter Lend. Les pools concentrés SOL/USDC perdent face au rééquilibrage. **Aucune option ne justifie un test avec argent réel.** Je propose seulement une veille sans argent, avec un déclencheur.

## 1. Tableau des options (500 CAD ≈ 353 USD)

| Option | Net estimé USD/an pour 353 USD (catégorie) | Pire drawdown | Risques principaux | Accès Québec |
|---|---|---|---|---|
| **Réf. : Jupiter Lend USDC (T-029)** | ≈ +14 USD (4,1 %) ; vérifié (taux API) | ≈ 0 (hors exploit) | contrat intelligent, perte totale si exploit | CGU Jupiter OK (serveur au Canada) |
| **JLP non couvert** | 2025-01 → 2026-10 réalisé : **+7,8 %/an ≈ +28 USD** ; 12 derniers mois : **−20 % ≈ −71 USD** ; en échantillon | **−46,3 %** (2025-10-06 → 2026-06-06) ; −35,8 % en 2026 | bêta crypto ≈ 0,6 (corrélé à notre stratégie d'achat de creux), contrepartie des traders, contrat, oracle | Achat de JLP = swap Jupiter : mêmes CGU que nos swaps. Coût AR mesuré ≈ 0,01 % |
| **JLP couvert par shorts Jupiter Perps** | 2026 YTD : **+2,9 %/an ≈ +10 USD** ; 2025-26 : +9,2 %/an (optimiste : taux d'emprunt de 2026 appliqué à 2025) ; en échantillon | −4,7 % (2025-26), pire jour −2,5 % | tout ce qui précède, + liquidation des shorts sur une hausse rapide, rééquilibrage quotidien, centaines d'événements fiscaux par an | CGU Jupiter sans clause propre aux perps. Mais c'est du **trading de dérivés** sur une plateforme non inscrite : **légalité au Québec non vérifiée**, même objection que pour Hyperliquid |
| JLP couvert par shorts Hyperliquid | 2026 YTD : +7,6 %/an ; 2025-26 : +14,9 %/an ; en échantillon | −4,5 % | idem + plateforme étrangère + deux protocoles | **Exclu** par la règle projet (VENUES §2) |
| Coffres « JLP delta-neutre » clés en main | — | **perte totale possible** : le coffre JLP-DN de Drift a été vidé lors de l'exploit du 2026-04-01 | protocole tiers, clé admin | Coffre Jupiter JLP-DN fermé (« reduce-only ») ; Drift exclu |
| **CLMM SOL/USDC passif** (Orca, Raydium, Meteora), plage ±10 % | **négatif** : frais ≈ 4,7 %/an par dollar de liquidité virtuelle, contre une LVR de 5,7-8,9 %/an ⇒ ≈ −1 à −4 % par dollar virtuel, soit **≈ −20 à −80 %/an sur le capital** en plage ±10 % ; exploratoire | sans plancher sur une tendance (le LP finit 100 % SOL dans une baisse) | LVR, flux toxique (les prop AMM captent le flux non informé), rééquilibrage | Accès technique OK (DEX) ; non pertinent |
| CLMM avec bot de rééquilibrage | ≤ passif : les frais Solana (≈ 0,001-0,006 USD/tx, loyer remboursable) ne sont pas l'obstacle, c'est l'absence d'edge | idem | idem, + chaque recentrage cristallise la perte | idem |
| Ordres limit sur carnet on-chain (Phoenix, OpenBook v2) | **aucune source sérieuse** ne montre un rendement net positif pour un petit teneur de marché ; Exp 16 montre la sélection adverse des ordres limit sur nos actifs | — | sélection adverse, concurrence des teneurs professionnels | technique OK |

## 2. JLP en détail

### 2.1 Mécanisme (sources officielles)

- JLP est la part d'un pool (cible : SOL 47 %, WBTC 13-15 %, ETH 8 %, stables ≈ 30-32 %) qui sert de contrepartie à tous les perps Jupiter. **75 % de tous les frais** (ouverture/fermeture 0,06 %, impact de prix, emprunt, swaps, mint/burn, liquidations) sont réinvestis chaque heure dans le pool. Les 25 % restants vont au protocole et, depuis le 2025-02-17, pour moitié aux détenteurs de JUP (méthodologie DefiLlama ; docs Jupiter « JLP earn »).
- Le SOL du pool est en grande partie **jalonné** (387 M USD sur 423 M) au profit des détenteurs de JLP (docs Jupiter, earn). Ce rendement est inclus dans le portage mesuré ci-dessous.
- Pas de funding sur Jupiter Perps : les positions paient un **taux d'emprunt horaire** proportionnel à l'utilisation.
- État le 2026-10-08 à 22:50 UTC (API `perps-api.jup.ag/v1/jlp-info`, vérifié) : AUM **897 M USD**, prix 4,659, **APR officiel 8,40 %** (APY 8,76 %). Utilisation SOL 11,4 %, BTC 13,3 %, ETH 5,9 %, USDC 61,6 %. Emprunt des **shorts 0,0007 %/h ≈ 6,1 %/an** ; longs 0,0013-0,0016 %/h ≈ 11-14 %/an (unité « % par heure » d'après l'interface, **non vérifiée** dans une doc).
- Jupiter (rapport de risque Jupiter Lend, 2026-04-30) : les longs représentent souvent plus de 90 % de l'open interest, donc **JLP est en pratique short des traders en marché haussier**.

### 2.2 Rendement historique en USD (exploratoire, en échantillon)

Données : prix quotidiens DefiLlama de JLP (premier point 2023-11-22 à 1,48 USD, dernier 4,65), de SOL, ETH et BTC. Pour la décomposition, j'ai utilisé une régression quotidienne des rendements de JLP sur ceux de SOL, ETH et BTC, sur chaque année civile :

| Période | JLP total (ann.) | Bêtas SOL / ETH / BTC | Portage α (régression, %/an) | Frais LP / AUM (%/an, DefiLlama, corrigé ×0,855) | Reste = PnL traders + bruit | MaxDD JLP | MaxDD SOL |
|---|---|---|---|---|---|---|---|
| 2024 (dès 01-29) | +125 % | 0,23 / 0,08 / 0,04 | **+52** | ≈ 39 | ≈ +13 | −11,0 % | −38,3 % |
| 2025 | +8,3 % | 0,39 / 0,05 / 0,11 | **+18** | ≈ 16 | ≈ +2 | −30,8 % | −59,9 % |
| 2026 YTD (→ 10-07) | +7,3 % | 0,45 / 0,08 / 0,13 | **+8,7** | ≈ 9,5 | ≈ −1 | −35,8 % | −58,0 % |
| 2025-01 → 2026-10 | +7,8 %/an | — | — | ≈ 13 | — | **−46,3 %** | −76,6 % |
| 12 derniers mois | **−20,0 %** | — | — | ≈ 10 | — | −45,8 % | −73,1 % |

Lecture et limites :
- **La part « prix des actifs »** équivaut à ≈ 0,4-0,65 de bêta crypto, et non à ≈ 0,7 : une partie de la hausse revient aux traders longs. JLP n'a pas protégé du baissier 2025-26. Il a perdu −46 % du sommet au creux, soit environ 60 % du drawdown de SOL.
- **Les frais** sont la seule source régulière. Ils chutent : environ 45 %/an en 2024, environ 19 % en 2025 et 7-15 % par mois annualisé en 2026. L'APR officiel est de 8,4 % aujourd'hui.
  - Le ratio DefiLlama « frais LP / TVL » surestime d'environ 17 %, car la TVL DefiLlama (767 M USD) exclut les actifs verrouillés, alors que l'AUM officielle atteint 897 M USD. J'ai donc corrigé ce ratio par 0,855, en supposant un rapport constant (non vérifié dans le temps).
- **Le PnL des traders ne se sépare pas de façon fiable** avec des données publiques quotidiennes.
  - Par la régression, il vaut entre +13 et −1 point/an.
  - Une autre méthode, qui utilise les poids d'actifs DefiLlama (hors actifs verrouillés), donne un résidu d'environ −10 points/an chaque année.
  - Les deux méthodes ne s'accordent pas. La seule conclusion robuste est que **le portage provient presque entièrement des frais**, et que l'effet net des traders reste au plus de quelques points, avec un signe instable.

### 2.3 Couverture delta (exploratoire, en échantillon)

Méthode :
- Les bêtas sont estimés sur une **fenêtre glissante de 60 jours, passée seulement** (hors échantillon pour le bêta). Le short est rééquilibré chaque jour, avec une marge de 1/3 du notionnel.
- Rotation moyenne : 1,6 % du capital par jour.
- Funding Hyperliquid : historique public horaire. Il est positif pour les shorts : ≈ 22-28 %/an en 2024, 5-11 % en 2025, et 0-6 % en 2026 (SOL ≈ 0,1 %).
- Jupiter Perps : 0,06 % par modification de position, taux d'emprunt constant (scénarios ci-dessous). Les frais d'impact sont ignorés.

| Rendement net par dollar de capital | 2024-03 → 12 | 2025 | 2026 YTD | 2025-01 → 2026-10 | MaxDD 2025-26 |
|---|---|---|---|---|---|
| Couvert, sans coût ni funding (par $ de JLP) | 59,7 % | 20,5 % | 8,0 % | 14,9 % | −5,0 % |
| Couvert Hyperliquid (funding + taker 0,045 %) | 62,7 % | 20,8 % | 7,6 % | 14,9 % | −4,5 % |
| **Couvert Jupiter Perps, emprunt 6,1 %/an (taux actuel)** | 48,5 % | 14,4 % | **2,9 %** | 9,2 % | −4,7 % |
| Couvert Jupiter Perps, emprunt 10 %/an | 46,7 % | 12,5 % | 0,7 % | 7,2 % | −4,9 % |
| Couvert Jupiter Perps, emprunt 25 %/an | 39,9 % | 5,4 % | −7,1 % | −0,2 % | −9,3 % |

Avec une fenêtre de 120 jours (variante rapportée) : sans coût, 15,0 % en 2025 et 5,9 % en 2026 ; Jupiter Perps à 10 %, 8,0 % en 2025 et −0,8 % en 2026.

Points clés :
- Le **portage couvert brut s'effondre** : environ 60 % en 2024, 15-20 % en 2025 et **6-8 % en 2026**.
  - Couvrir sur Jupiter Perps coûte environ 0,66 × 6,1 % ≈ 4 points/an d'emprunt, plus la dilution par la marge. Le net de 2026 n'est alors plus que **≈ 1-3 %/an, sous Jupiter Lend (4,1 %)**, avec plus de risques.
  - Le seul cas qui dépasse 15 %/an est 2024-25, quand le volume perps était bien plus élevé. Il n'existe plus aujourd'hui.
- Le taux d'emprunt Jupiter de 2025 n'est pas connu ici. Appliquer le taux de 2026, plus bas, rend la ligne 2025 **optimiste**.
- Le MaxDD couvert de −5 % est **hors risque de queue** : il ne compte ni exploit, ni mauvais prix d'oracle, ni liquidation du short sur une mèche. Avec des shorts à 3×, une hausse de SOL d'environ 30 % entre deux rééquilibrages liquide la couverture, alors que le gain sur JLP reste dans l'autre poche.
- Avec 353 USD, la mise en place est possible techniquement : il faut 10 USD de collatéral minimum par position Jupiter Perps, et trois shorts d'environ 140, 25 et 40 USD de notionnel. Mais 2,9 % de 353 USD ≈ **10 USD/an**, avant impôt et avant le coût d'un serveur au Canada.

### 2.4 Risques

- **Exploit / clé admin :** aucun exploit connu de Jupiter Perps ou JLP (DefiLlama `hacks: []` ; rapport Jupiter du 2026-04-30). Mais **le 2026-04-01, l'exploit de Drift a vidé le coffre « JLP Delta Neutral » hébergé sur Drift**, soit environ 41,7 M JLP (≈ 155 M USD, sources secondaires). Les structures couvertes ajoutent donc un protocole, donc une surface d'attaque. Jupiter déclare JLP « fully backed » après l'événement.
- **Oracle :** l'oracle principal est Chaos Labs (Edge), avec Pyth et Chainlink en secours (DefiLlama ; support Jupiter). Le prix virtuel de JLP dépend des cinq flux de prix.
- **Dépeg :** environ 30 % de stables (USDC ; USDT désormais 0 % ; JUPUSD 2 %), plus du WBTC et de l'ETH ponté (Portal/Wormhole). Un dépeg de WBTC ou de l'ETH Portal toucherait environ 21 % du pool.
- **Contrepartie des traders :** dans une forte hausse avec des longs gagnants, le pool paie. C'est la cause du bêta inférieur au poids des actifs.
- **Liquidité de sortie :** sortie par mint/burn direct contre le pool (frais de base 10 pb pour les actifs crypto et 2 pb pour les stables, ajustés selon l'écart à la cible ; tampon de ±20 %). Cotation Jupiter du 2026-10-08 22:51 UTC, lecture seule, sans frais de plateforme : 360 USDC → 77,392 JLP, puis 77 JLP → 358,148 USDC, soit un **aller-retour ≈ 0,01 %**. C'est un instantané unique.
- **Fiscalité :** chaque achat ou vente de JLP est une disposition. La couverture quotidienne ajoute des centaines d'événements par an. Traitement fiscal des perps DeFi **non vérifié** (voir T-029 §5).
- **Corrélation avec la stratégie active :** remplacer l'USDC inactif par du JLP non couvert ajouterait un bêta crypto d'environ 0,6. Ce bêta est corrélé aux pertes de l'achat de creux, et le capital ne serait plus disponible en USDC au signal sans un swap supplémentaire. C'est à éviter.

### 2.5 Accès depuis le Canada / Québec

- **CGU Jupiter** (relues le 2026-10-08) : la liste des « Prohibited Localities » ne contient pas le Canada. **Aucune clause propre aux perps, à JLP ou aux dérivés.** VPN interdit. Les conditions sont les mêmes que pour nos swaps, avec un serveur au Canada.
- **Détenir JLP** revient à faire un swap de jeton. C'est la même situation juridique que nos swaps : « permis faute d'interdiction », une inférence non vérifiée.
- **Ouvrir des shorts Jupiter Perps** est une opération sur dérivés avec une plateforme non inscrite. La règle projet exclut déjà Hyperliquid pour cette raison. Par cohérence, **la couverture n'est pas acquise au Québec (non vérifié, AMF/Loi sur les instruments dérivés)**. Il faut un avis de l'agent Plateformes avant toute utilisation.
- Montant minimum : aucun pour JLP (un swap) ; 10 USD de collatéral par position perps.

## 3. Pools de liquidité concentrée SOL/USDC

**Littérature (académique) :**
- Milionis, Moallemi, Roughgarden, Zhang, « Automated Market Making and Loss-Versus-Rebalancing » (arXiv 2208.06046, v1 2022-08-11, v6 2026-08-20). Le rendement d'un LP se décompose en bêta, plus (frais − LVR). Pour un CPMM, LVR = σ²/8 par unité de valeur. Plus de 99,99 % de la variance du rendement LP ETH-USDC v2 vient du bêta.
- Loesch, Hindman, Richardson, Welch, « Impermanent Loss in Uniswap v3 » (arXiv 2111.09192, 2021-11-17) : 17 pools, 43 % de la TVL. Frais de 199,3 M USD contre une perte impermanente de 260,1 M USD ; **les LP auraient gagné 60,8 M USD de plus en HODL**.
- Heimbach, Schertenleib, Wattenhofer, « Risks and Returns of Uniswap V3 Liquidity Providers » (arXiv 2205.08904, 2022) : il existe des stratégies simples et rentables seulement dans les pools peu volatils, et leurs rendements sont modestes. Les rendements élevés exigent une gestion active et plus de risque.
- arXiv 2505.15338 (2025) : les stratégies dynamiques de CLMM ne battent pas de façon constante le buy-and-hold.

**Données on-chain Solana (exploratoire, ne compte pas) :**
- Pool Orca Whirlpool SOL/USDC 0,04 % (`Czfq3x…44zE`), API publique Orca du 2026-10-08 :
  - TVL 27,9 M USD ; frais de 1,63 M USD sur 30 jours, soit 19,8 M USD/an (87 % aux LP, 13 % au protocole) ;
  - liquidité active L = 5,53e14, soit une **valeur virtuelle d'environ 368 M USD** au prix courant (≈ 13 × la TVL).
  - **Frais LP par dollar de liquidité virtuelle ≈ 4,7 %/an.**
- **LVR = σ²/8**, avec σ réalisé quotidien de SOL : 81 % en 2024, 84 % en 2025, 68 % en 2026, soit **8,3 / 8,9 / 5,7 %/an par dollar virtuel**.
  - Le LP passif moyen en plage perd donc environ 1 à 4 points/an par dollar virtuel.
  - Pour une position à ±10 % (facteur de concentration ≈ 20), cela fait **≈ −20 à −80 %/an sur le capital engagé** pendant que la position est en plage.
  - Limites : l'APR affiché par DefiLlama (58-73 %) n'est que des frais sur la TVL, sans LVR. Ce calcul utilise un instantané de liquidité et un σ quotidien ; la LVR en blocs de 400 ms avec frais (Milionis et al. 2023) n'est pas modélisée.
- **Structure de marché :** les « prop AMM » (HumidiFi, BisonFi, SolFi, Tessera) traitent plus de 60 % du volume DEX Solana et environ la moitié du SOL-USDC. Ils actualisent leur prix par oracle et captent le flux non informé (Blockworks Research ; Stepdata ; **non académique**). Les CLMM publics gardent une plus grande part du flux d'arbitrage.
- **Bots de rééquilibrage avec 500 CAD :** le coût n'est pas le problème. Une transaction coûte environ 0,001-0,006 USD ; le loyer de position est remboursable ; les comptes de ticks peuvent coûter environ 0,07 SOL s'ils ne sont pas initialisés (non vérifié). Le problème est l'absence d'edge : recentrer cristallise la perte, et chaque recentrage paie un swap de 0,04-0,10 %. Les coffres automatisés (Kamino Liquidity SOL-USDC : APY de frais 7-19 % sur 0,1-0,3 M USD de TVL) n'affichent pas de rendement net de la perte impermanente.

**Verdict CLMM : écarté.** C'est cohérent avec `INDEX.md`, et désormais chiffré sur Solana en 2026.

## 4. Carnets d'ordres on-chain (Phoenix, OpenBook v2)

- OpenBook v2 : taker 4 pb, maker −2 pb (source secondaire, **non académique**). Phoenix : TVL ≈ 1-1,7 M USD (DefiLlama, page protocole).
- **Aucune source sérieuse** (académique ou dashboard) ne montre un rendement net positif pour un petit teneur de marché sur ces carnets. Le flux SOL-USDC est capté par les prop AMM. En interne, l'Exp 16 a montré la sélection adverse des ordres limit sur BTC et ETH.
- **Écarté**, conformément à la consigne : on ne retient une piste que si une source sérieuse montre un rendement net positif.

## 5. Verdict

1. **Aucune option ne mérite un essai réel ni un test préenregistré décisionnel aujourd'hui.**
   - JLP non couvert n'est pas de la fourniture de liquidité au sens d'un edge : c'est un panier crypto à 0,6 de bêta. Il a rapporté +7,8 %/an sur 2025-26, avec un drawdown de −46 % et −20 % sur 12 mois.
   - JLP couvert ne rapporte qu'environ 1-3 %/an net sur les perps Jupiter au niveau de frais de 2026, ce qui est inférieur à Jupiter Lend. De plus, la couverture est juridiquement incertaine au Québec.
   - Les CLMM et les carnets d'ordres sont négatifs ou sans preuve.
2. **Ce qui ferait changer d'avis :** le portage dépend entièrement du volume des perps Jupiter.
   - Si l'APR officiel de JLP remontait durablement au-dessus d'environ 15 %, comme en 2025, le net couvert sur Jupiter Perps (APR − ≈ 4-5 points − dilution) dépasserait environ 8-10 %/an.
   - Il atteindrait environ 15 %/an seulement au-dessus d'un APR d'environ 22-25 %, niveau de la mi-2024.
   - Même dans ce cas, il resterait la question juridique de la couverture, et le risque de queue d'un protocole de dérivés (Drift 2026, Mango 2022).

## 6. Proposition (non exécutée) : H-R13a, veille sans argent à déclencheur

- **But :** ne pas manquer un retour du régime de frais de 2024-25, sans rien risquer.
- **Enregistreur quotidien (lecture seule) :**
  - `perps-api.jup.ag/v1/jlp-info` (APR, AUM, prix, poids, utilisation) ;
  - `pool-info` pour SOL, ETH et BTC (emprunt des shorts) ;
  - cotation `lite-api` USDC↔JLP pour 360 USDC.
- **Calcul :** une NAV fictive « JLP + shorts Jupiter Perps » (bêta 60 j passé, rééquilibrage quotidien, 0,06 % par modification, emprunt observé).
- **Déclencheur préenregistré :** APR officiel sur 30 jours ≥ 15 % **et** NAV fictive couverte nette de ≥ 10 %/an sur 90 jours de forward. Si les deux conditions sont réunies, on demande à l'agent Plateformes de statuer sur la légalité des perps DeFi au Québec. Ce n'est qu'ensuite qu'on décide d'un essai réel, plafonné à 100 USD.
- **Rejet automatique :** déclencheur non atteint au 2027-04-08 → piste close.
- **Coût :** un appel HTTP par jour, aucun compte, aucune clé. **Priorité basse** : à lancer seulement si un enregistreur de cotations existe déjà (H-R01/H-R08).

## 7. Compteur de tests (exploratoire, ne compte pas)

| # | Calcul | Variantes |
|---|---|---|
| 1 | Décomposition par poids d'actifs DefiLlama (frais / résidu) | 1 (rapportée, jugée non fiable) |
| 2 | Régression annuelle JLP ~ SOL+ETH+BTC | 3 périodes |
| 3 | Couverture par bêta glissant | fenêtres 60 et 120 j ; 5 scénarios de coût (sans coût, HL, JP 6,1/10/25 %) |
| 4 | LVR théorique SOL (σ²/8 × concentration) | 4 largeurs de plage × 3 années |
| 5 | Frais par dollar virtuel, pool Orca 0,04 % | 1 instantané |
| 6 | Cotation aller-retour USDC↔JLP | 1 instantané (mesure) |

Aucun calcul sur le registre de trades crypto.

## 8. Sources (consultées le 2026-10-08)

**Données / dashboards (vérifiés par appel public) :**
- DefiLlama, protocole Jupiter Perpetual Exchange (TVL, `hacks`, oracles) : https://api.llama.fi/protocol/jupiter-perpetual-exchange
- DefiLlama, frais et revenus offre (méthodologie 75/25) : https://api.llama.fi/summary/fees/jupiter-perpetual-exchange?dataType=dailySupplySideRevenue
- DefiLlama, prix JLP/SOL/ETH/BTC : https://coins.llama.fi/chart/solana:27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4
- DefiLlama, rendements des pools : https://yields.llama.fi/pools
- Jupiter Perps API : https://perps-api.jup.ag/v1/jlp-info ; https://perps-api.jup.ag/v1/pool-info?mint=So11111111111111111111111111111111111111112
- Cotation Jupiter (lecture) : https://lite-api.jup.ag/swap/v1/quote
- RPC Solana (`getTokenSupply` JLP : 192 560 194 JLP)
- Orca API, pool SOL/USDC : https://api.orca.so/v2/solana/pools/Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE
- Hyperliquid, `fundingHistory` (SOL, ETH, BTC, 2024-01 → 2026-10) : https://api.hyperliquid.xyz/info

**Documentation officielle :**
- Jupiter, conditions d'utilisation : https://developers.jup.ag/docs/legal/terms-of-use
- Jupiter, frais perps/JLP : https://docs.jup.ag/user-docs/trade/perps-and-jlp/fees
- Jupiter, FAQ perps (collatéral min. 10 USD) : https://docs.jup.ag/user-docs/trade/perps-and-jlp/faq.md
- Jupiter, JLP earn (75 % des frais, SOL jalonné) : https://docs.jup.ag/user-docs/earn/jlp/earn.md
- Jupiter, JLP Delta Neutral (fermé, couverture sur Binance) : https://docs.jup.ag/user-docs/earn/jlp/delta-neutral.md
- Jupiter Lend, rapport de risque JLP (2026-04-30) : https://static-r2.jup.ag/lend/risk-research/jlp-risk-report.pdf

**Académique :**
- Milionis et al., arXiv 2208.06046 : https://arxiv.org/abs/2208.06046
- Loesch et al., arXiv 2111.09192 : https://arxiv.org/abs/2111.09192
- Heimbach et al., arXiv 2205.08904 : https://arxiv.org/abs/2205.08904
- arXiv 2505.15338 (stratégies dynamiques CLMM) : https://arxiv.org/pdf/2505.15338

**Non académique (presse, blogs) :**
- Exploit Drift 2026-04-01 et coffre JLP-DN vidé : https://www.coindesk.com/daybook-us/2026/04/02/audit-admin-keys-not-just-code-expert-says-after-usd200-million-drift-exploit-crypto-daybook-americas ; https://news.bitcoin.com/fr/le-piratage-du-protocole-drift-en-2026-ce-qui-sest-passe-qui-a-perdu-de-largent-et-quelle-est-la-suite/
- Gauntlet hJLP : https://gauntlet.xyz/resources/introducing-hjlp-delta-hedging-for-jlp-liquidity-providers
- Prop AMM sur Solana : https://app.blockworksresearch.com/unlocked/solana-dex-winners-all-about-order-flow ; https://stepdata.substack.com/p/prop-amms-on-solana-bisonfi-ends
- Frais OpenBook / Phoenix : https://solanacompass.com/projects/openbook ; https://defillama.com/protocol/phoenix-spot

## 9. Questions ouvertes pour l'orchestrateur

1. Agent Plateformes : les perps DeFi (Jupiter Perps) sont-ils permis à un particulier au Québec (Loi sur les instruments dérivés) ? La réponse conditionne toute couverture.
2. Unité exacte de `shortBorrowRatePercent` (% par heure ?) et historique 2025 des taux d'emprunt Jupiter : non trouvés.
3. Faut-il ajouter H-R13a (veille de l'APR JLP) à l'enregistreur de cotations existant ? Priorité basse.
