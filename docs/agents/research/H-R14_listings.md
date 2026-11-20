# H-R14 — Acheter sur Jupiter un jeton Solana juste après l'annonce de son listing (Coinbase, Binance, Upbit) — T-042

**Agent :** Chercheur. **Date :** 2026-10-08. **Branche :** `research/listings`.
Recherche web et calculs légers seulement. Aucun compte, aucune transaction, aucune clé. Les seuls appels réseau sont des lectures publiques : API d'annonces Upbit, API CMS d'annonces Binance, archive `data.binance.vision`, cotation Jupiter `lite-api` (chronométrage seulement).
**Tous les chiffres calculés ici sont exploratoires et ne comptent pas.** Ils portent sur 22 événements choisis à la main (biais de sélection possible), **en échantillon**, sans coûts on-chain mesurés. Scripts : `docs/agents/research/H-R14_scripts/`. Les données téléchargées ne sont pas commitées.
Change : 500 CAD ≈ **353 USD** (même taux que H-R13). Taille par événement : 100 à 350 USD.

## Résumé

L'effet existe et il est fort : en médiane, +12 % en une minute sur nos 22 événements. Mais **il est entièrement pris en 1 à 2,5 secondes** après la publication. Dans notre échantillon exploratoire, quand on achète **5 secondes** après la publication et qu'on revend 5 minutes plus tard, le rendement moyen est de **−0,7 %** (médiane −1,7 %, 7 positifs sur 22, écart-type 6,4 %). Ce calcul est fait **avant tout coût**. À 10 secondes, on obtient −0,9 % (médiane −2,0 %).
Notre chaîne réaliste est la suivante : sondage d'une page d'annonces depuis le Québec ou les É.-U., puis Jupiter `/build`, puis une transaction Solana sans infrastructure dédiée. Elle met **au moins 2 à 6 secondes**, souvent plus de 10. Dans une pointe, le coût réel n'est pas l'écart coté (0,01 à 0,35 %) : c'est le glissement entre la cotation et l'atterrissage, estimé à **1-4 %**, avec une sélection adverse (les ordres qui passent sont ceux où le prix n'a pas filé).
**Gain net central estimé : ≈ −2,7 % par événement, soit ≈ −110 USD/an (≈ −30 %/an du compte)**, avec un intervalle d'environ −80 % à +9 %/an (voir §5). **Verdict : on ne trade pas.** Un test historique est faisable et gratuit, mais il ne changerait pas la décision tant que notre latence réelle dépasse ≈ 2 secondes. Je propose d'abord une **mesure de latence sans argent (H-R14a)**. Le préenregistrement d'un test historique (H-R14b) est fourni, à n'exécuter que si H-R14a montre une latence médiane ≤ 2 s.

## Anti-doublon

- `research_plan_status.md`, `REGISTRY.csv`, `results/` : **aucune** expérience sur les annonces de listing. Les seules mentions de « listing » concernent l'historique de cotation des symboles (Phase A, Exp 37-39).
- `JOURNAL.md` (2026-10-07 22:00) : T-042 retenue parmi les textes de trois IA. Le JOURNAL de 2026-10-09 00:30 note son lancement.
- **H-R08** et **Exp 61** (REJET, 2026-10-08) : même univers de jetons (JUP, RAY, BONK, WIF, JTO, PYTH), mais avec un autre signal (achat de creux, sortie à 50 min). J'en réutilise seulement les **coûts aller-retour mesurés** sur Jupiter `/build` à 116 USD : JUP ≈ 0,01 %, RAY et BONK ≈ 0,09 %, PYTH et WIF ≈ 0,19 %, JTO ≈ 0,35 %. Ce n'est pas un doublon.
- **H-R13** : la fourniture de liquidité y est écartée, et la stratégie inverse (vendre la pointe à ceux qui achètent l'annonce) l'est aussi, faute de vente à découvert accessible (voir §7).
- `venues/VENUES_500CAD_2026-10-06.md` : les CGU de Jupiter excluent les É.-U. et imposent un serveur au Canada. Cela **interdit justement** le serveur à Séoul ou à Tokyo qu'il faudrait pour être rapide (voir §2.3).

## 1. Ce que dit la littérature sur l'effet

| Source | Type | Échantillon | Mesure | Résultat |
|---|---|---|---|---|
| Ante (2019), *Market Reaction to Exchange Listings of Cryptocurrencies*, BRL WP 3 | document de travail | 327 listings, 180 jetons, 22 plateformes, 2018-2019 | rendement anormal **journalier**, jour du listing (et non de l'annonce) | **+5,7 %** le jour J, +9,2 % sur [−3 ; +3]. Jusqu'à +25,5 % sur certaines plateformes. **Upbit : 15 événements, CAAR −2,9 %**, 73 % négatifs (l'annonce précède le listing et la hausse est déjà faite) |
| Ante (2021), *Cross-listings of blockchain-based tokens issued through ICOs*, Decisions in Economics and Finance | revue à comité | 250 listings | journalier | **+6,51 %** le jour J, +9,97 % sur 7 jours. Effet concentré sur quelques plateformes, et nul ou négatif ailleurs. Prime « plateforme régulée aux É.-U. » ≈ +11,4 %, tirée par Coinbase |
| Messari (2018), « Coinbase effect » | non académique | quelques dizaines de listings, 2017-2018 | 5 jours | +91 % en moyenne. Souvent cité, jamais reproduit depuis |
| Asalio123, *binance-listing-study* (GitHub) | **non académique, non revu** | 470 listings USDT Binance 2021-2026, avec les jetons morts ; horodatage à la minute par l'API CMS | depuis la clôture du jour du listing | **J+1 −4,5 %, J+7 −11,5 %, J+30 −21,5 %** (médianes). **Avant l'annonce, sur les plateformes où le jeton se négociait déjà : +24,4 % sur 3 jours et +9,4 % sur les 3 heures précédentes.** Réplication annoncée sur Bybit (415) et Coinbase (566) |
| BeInCrypto / SwissBorg (2025) | non académique | 27 listings Binance 2025 | depuis le listing | 89 % négatifs, en moyenne −44 % |
| Blockmedia / Four Pillars (2026-03) | non académique | 59 nouvelles paires KRW sur Upbit en 2025 | depuis la clôture de J1 jusqu'au 2026-03-11 | médiane **−80,9 %** ; 2 jetons positifs sur 59 |
| CZ (Binance), cité par la presse en 2025 | non académique | — | — | Il reconnaît qu'environ 4 h séparent l'annonce de l'ouverture du marché : les prix montent sur les DEX, puis « les gens vendent sur le CEX » |
| Argus / WSJ (2022) | non académique | 46 portefeuilles, 2021-02 → 2022-04 | achats avant les listings Coinbase/Binance | ≥ 1,7 M$ de profits pour des achats faits **avant** l'annonce : délit d'initié présumé |

**Lecture.**
1. L'effet à l'annonce est réel et large (+5 à +30 % selon la plateforme), mais la littérature académique ne le mesure qu'à la journée.
2. Je n'ai trouvé **aucune étude académique intrajournalière** (1 min, 5 min) sur les annonces de listing. Les mesures à la seconde ci-dessous sont les miennes (exploratoires).
3. Après la pointe, la dérive est **négative** à 1 jour et au-delà, quelle que soit la plateforme (Binance, Upbit, Coinbase). La partie « détenir 1 jour » est donc défavorable.
4. Une partie de l'information sort **avant** l'annonce : présomptions de délit d'initié sur Upbit (WIF, VVV, 2026), Argus 2022, et +9,4 % sur les 3 h précédentes selon l'étude GitHub. Ceux qui ont l'information avant nous sont des vendeurs naturels de la pointe.
5. **Évolution 2024-2026.** Le nombre d'annonces Upbit a explosé (10 en 2022, 40 en 2024, 98 en 2025, 59 au 2026-10-08 ; comptage ci-dessous), et la qualité moyenne des jetons a baissé. Binance a déplacé ses listings vers Alpha et HODLer Airdrops (56 et 53 annonces en 2025, contre 15 listings spot). Depuis décembre 2025, **Coinbase permet de négocier n'importe quel jeton Solana via un DEX dans son application**, sans listing : l'« annonce Coinbase » d'un jeton Solana ne porte presque plus d'information nouvelle. Les fournisseurs de flux d'annonces disent eux-mêmes que la fenêtre de réaction « s'est resserrée » depuis deux ans (non académique).

## 2. La course de vitesse

### 2.1 Mesure exploratoire : en combien de secondes le prix bouge (ne compte pas)

Méthode. Je prends un jeton Solana **déjà négocié sur Binance** au moment de l'annonce. Binance est arbitré avec les pools Solana en 1 à 3 slots (≈ 0,4-1,2 s), ce qui en fait un indicateur de ce que le pool Jupiter offrait au même instant. L'arbitrage CEX-DEX est documenté dans les sources de l'arbitrage Solana (non académiques). Le prix utilisé est le dernier prix connu à la seconde, close à close, **sans aucun coût**.
- **Upbit** : 16 annonces de jetons Solana (2024-02 → 2026-05). Horodatage `first_listed_at` de l'API Upbit, à la seconde. Prix : klines **1 s** du spot Binance. 2Z exclu (pas de données 1 s).
- **Binance** : 6 annonces de listing spot de jetons qui avaient déjà un perpétuel Binance (BONK, WIF, TRUMP, KMNO, PUMP, MET ; 2023-12 → 2025-11). Horodatage `releaseDate` du CMS Binance, **à la milliseconde**. Prix : `aggTrades` du perpétuel USDT-M, à la milliseconde. BOME, PNUT et ACT exclus faute de perpétuel avant l'annonce.

| Mesure (22 événements) | Valeur |
|---|---|
| Rendement de t0−1 s à t0+60 s | moyenne **+15,1 %**, médiane **+11,8 %** |
| Rendement de t0−1 h à t0 (fuite avant l'annonce) | moyenne +1,6 % (faible sur ces 22 événements) |
| **Binance : délai entre `releaseDate` et un prix > +2 %** | **1,9 à 3,4 s** (BONK 2,2 ; WIF 1,9 ; KMNO 2,4 ; MET 2,4 ; TRUMP 3,4). PUMP : pas de saut (+0,6 %) |
| Upbit : saut dans la même seconde, ou la suivante, que `first_listed_at` | 14 sur 16 (r+1 s déjà entre +9 et +30 % dans 9 cas). MET n'a pas sauté |
| Upbit : part du maximum sur 10 min déjà atteinte à t0+2 s | médiane 59 % (24 % pour RENDER, 100 % pour JUP et JTO BTC/USDT) ; seconde du maximum : médiane ≈ 30 s |

Rendement **d'un achat retardé** (entrée à t0 + délai, sortie à l'horizon), sans coûts :

| Entrée après publication | n | Sortie +60 s : moyenne / médiane / % positifs | Sortie +5 min : moyenne / médiane / % positifs | Sortie +1 h : moyenne / médiane |
|---|---|---|---|---|
| Binance seul, +2 s | 6 | +6,7 % / +6,9 % / 5 sur 6 | +7,2 % / +8,1 % / 5 sur 6 | +9,1 % / +10,3 % |
| Binance seul, +5 s | 6 | −0,3 % / −1,0 % / 2 sur 6 | +0,4 % / −1,2 % / 2 sur 6 | +2,0 % / 0,0 % |
| Upbit seul, +2 s | 16 | −0,1 % / 0,0 % / 8 sur 16 | −0,8 % / +0,1 % / 8 sur 16 | −1,4 % / −0,8 % |
| **Tous, +5 s** | 22 | −0,2 % / −1,8 % / 7 sur 22 | **−0,7 % / −1,7 % / 7 sur 22** (écart-type 6,4 %) | −0,8 % / −1,6 % |
| Tous, +10 s | 22 | +0,4 % / −0,9 % / 9 sur 22 | −0,9 % / −2,0 % / 8 sur 22 | −0,7 % / −3,1 % |
| Tous, +30 s | 22 | +1,8 % / 0,0 % / 11 sur 22 | −0,6 % / −0,9 % / 11 sur 22 | −0,5 % / −0,3 % |

**Lecture.** Sur Binance, la fenêtre se ferme entre 2 et 5 secondes après la publication CMS. Sur Upbit, elle est déjà fermée à 2 secondes. Ensuite, l'espérance brute est nulle ou légèrement négative, avec un écart-type de 5 à 10 % par événement. Pour **notre latence**, il n'y a pas d'effet à capturer.
Réserves :
- 22 événements choisis par moi parmi ceux que je savais être des jetons Solana cotés sur Binance (biais de sélection possible) ;
- le prix Binance n'est qu'un indicateur du prix du pool ;
- un écart de ±1 s sur l'horodatage officiel est possible (5 cas Upbit ont un prix déjà en hausse à la seconde t0) ;
- **30 cellules regardées** (5 délais × 3 horizons × 2 ensembles) : compteur de tests multiples.

### 2.2 Délai des flux d'annonces

| Canal | Délai publié ou mesuré | Statut |
|---|---|---|
| API Upbit `api-manager.upbit.com/api/v1/announcements` | Temps de réponse mesuré depuis le Québec : **0,32-0,76 s**. Débit limité : des **429 dès 1 requête / 0,4 s** (vu en téléchargeant l'historique). On ne peut donc sonder qu'environ 1 fois par seconde, d'où un retard moyen de ≥ 0,5 s + 0,3 s + cache CDN inconnu | mesuré 2026-10-08, exploratoire |
| API CMS Binance `bapi/composite/v1/public/cms/article/list/query` | Temps de réponse mesuré : **0,09-0,35 s**. Contenu derrière un CDN, durée de cache inconnue | mesuré 2026-10-08 |
| Telegram (canaux officiels, bots) | 150-500 ms (fournisseur cryptolisting.ws) ; ≈ 80 ms par MTProto (dépôt d'un bot « Upbit sniper ») | **non académique**, déclarations commerciales |
| X / Twitter | 2-10 s (cryptolisting.ws) | **non académique** |
| Flux WebSocket payants (cryptolisting.ws, newlistings.pro) | « < 1 ms » entre détection et envoi, points de présence à Tokyo et Séoul ; offre gratuite retardée de +240 ms | **non académique** |
| Coinbase | pas d'API officielle d'annonces. Comptes X @CoinbaseMarkets / @CoinbaseAssets ; feuille de route. Par X : 2-10 s | non vérifié |

### 2.3 Envoi de la transaction Solana (notre cas)

- Cotation Jupiter `lite-api` : **0,12-0,18 s** mesuré depuis le Québec. Il faut ensuite `/build`, la signature, l'envoi par RPC et l'atterrissage.
- Atterrissage. Chorus One, 2024-11, mesure on-chain (**étude de validateur, non académique**) : pour un expéditeur non optimisé, la distribution a trois modes, autour de **≈ 5 s, ≈ 17 s et ≈ 63 s**. Les frais de priorité et les pourboires Jito changent peu le délai ; seul le swQoS (connexion pondérée par le stake, réservée aux gros acteurs) aide vraiment. En congestion (2025), 20 à 45 % des transactions échouent.
- **Notre délai réaliste, de la publication à l'atterrissage** : ≈ 0,5-1,5 s (détection) + 0,3-0,5 s (cotation et construction) + 0,4-5 s (atterrissage), soit **≈ 1,5 s au mieux, 3-6 s en général, > 10 s souvent**. Pendant une annonce, le réseau se congestionne localement : tout le monde achète le même pool.
- **Concurrence.** Bots colocalisés à Séoul ou Tokyo branchés sur des flux à la milliseconde (Telegram MTProto, WebSockets dédiés). Bots d'arbitrage CEX-DEX qui réalignent le pool sur Binance en 1-3 slots. Un dépôt « Upbit sniper » ferme sa position **15 s** après l'entrée (paramètre par défaut) : la pointe utile dure quelques secondes. Le serveur Séoul/Tokyo qui nous rapprocherait est **exclu par les CGU de Jupiter**, qui imposent un serveur au Canada (VENUES). Un EC2 aux É.-U. est exclu aussi.

## 3. Données pour un test historique

| Donnée | Source | Précision | Profondeur | Gratuit ? | Vérifié |
|---|---|---|---|---|---|
| Annonces Upbit | `api-manager.upbit.com/api/v1/announcements?category=trade` (JSON, sans clé) | seconde (KST). `first_listed_at` ≠ `listed_at` quand l'avis est mis à jour : **utiliser `first_listed_at`** | 785 avis « trade » depuis le 2017-10-27 | oui | **oui**, téléchargé le 2026-10-08 |
| Annonces Binance | API CMS, `catalogId=48` (« New Cryptocurrency Listing ») | **milliseconde** (UTC) | 2 279 articles depuis le 2017-07-21 | oui | **oui** |
| Annonces Coinbase | X @CoinbaseMarkets (horodatage à la seconde, mais API X payante), blog, feuille de route | seconde par X | depuis ≈ 2021 | non (API X), archives manuelles | non |
| Prix CEX à la seconde | `data.binance.vision` : klines spot **1 s** ; `aggTrades` spot et USDT-M à la ms | 1 s / 1 ms | spot 1 s sur toute la période testée (2024-02 → 2026-05) | oui | **oui** (16 + 6 événements) |
| Prix on-chain 1 min | GeckoTerminal `ohlcv/minute` | 1 min | API gratuite : **6 derniers mois seulement** ; depuis 2021-09 en payant (Analyst+) ; 30 appels/min | partiel | doc consultée |
| Prix on-chain 1 min | Birdeye OHLCV 1m | 1 min | 1 000 bougies/appel ; offre gratuite ≈ 30 k CU/mois (≈ 750 appels) | oui, limité | non (source tierce) |
| Trades on-chain à la seconde | Dune `dex_solana.trades` (`block_time`) | seconde, swap par swap | depuis 2021 | **non** depuis le 2026-09-10 pour les anciens comptes gratuits (lecture seule) ; Analyst ≈ 65 USD/mois | doc consultée |
| Idem | Flipside | — | — | **studio fermé le 2025-07-01** | doc consultée |
| Idem | RPC Solana (`getBlock` sur les slots de la fenêtre, ou `getSignaturesForAddress` sur le pool) | slot (0,4 s) | toute l'histoire | oui, mais lent (≈ 150 blocs par minute de fenêtre) | non |

**Nombre d'événements par an (jetons Solana déjà négociables sur Jupiter)** :
- **Upbit** (nouveau listing ou ajout du marché KRW), classement Solana fait par moi (marge d'erreur de quelques jetons). PYTH, JUP, MEW ×2, W, BONK ×2, DRIFT, RENDER, SONIC, JTO ×2, LAYER, TRUMP, ORCA, PENGU, SOON ×2, RAY, MOODENG, HUMA, 2Z, DOOD, MET, SKR, WIF, IO, USELESS : **≈ 29 en 2,6 ans, soit ≈ 10-11/an**, dont ≈ 7/an sur le marché KRW (le plus fort).
- **Binance spot** : JTO, BONK, JUP, PYTH, WIF, BOME, W, TNSR, PNUT/ACT, ME, TRUMP, KMNO, PUMP, MET… soit **≈ 5-9/an** (en baisse : 24 listings spot en 2024, 15 en 2025). S'y ajoutent les perpétuels (84-107 par an, toutes chaînes confondues) et Binance Alpha (non comptés : effet incertain).
- **Coinbase** : ≈ 10-20 jetons Solana par an sur la feuille de route jusqu'en 2025. Valeur informative très réduite depuis la négociation DEX Solana intégrée à l'application (décembre 2025).
- **Total réaliste : ≈ 15-30 événements par an**, dont une partie chevauche (le même jeton sur deux plateformes).

## 4. Coûts réels sur Jupiter pendant l'annonce

- **Écart coté en temps calme** (Exp 61 et H-R08, 116 USD, `/build`) : JUP 0,01 %, BONK/RAY ≈ 0,09 %, PYTH/WIF ≈ 0,19 %, JTO 0,35 %, autres jetons moyens 0,2-1,2 %. À 350 USD : ×1,5 à ×3 sur les jetons moyens.
- **Pendant la pointe**, le coût dominant est le **glissement entre la cotation et l'atterrissage**. Sur nos 22 événements, le prix bouge de **2 à 5 % par seconde** pendant les 5 premières secondes (par exemple JUP +29,9 → +33,7 → +19,2 % entre t0+1 s et t0+5 s). Avec un atterrissage à 0,4-5 s :
  - tolérance de glissement serrée (≤ 1 %) : une bonne partie des transactions échoue, ou atterrit seulement quand le prix est retombé. C'est une **sélection adverse** : les ordres qui passent sont les mauvais ;
  - tolérance large (5-20 %) : remplissage au pire prix de la fourchette, et **sandwich possible jusqu'à la tolérance**. Les sandwichs sur Solana représentent 370 à 500 M$ en 16 mois (sandwiched.me, non académique). Jupiter Ultra (`/order`) réduit ce risque avec un routage privé, mais `/build`, notre chemin, ne bénéficie pas de cette protection par défaut.
  - Mon estimation du coût d'entrée en pointe est **1-4 %**, non mesurée on-chain ; la sortie en temps calme coûte 0,1-0,4 %. Les frais réseau et la priorité (≈ 0,01-0,2 USD) sont négligeables.

## 5. Gain net estimé par événement et par an (500 CAD ≈ 353 USD)

Hypothèses :
- délai réaliste de 3-6 s, d'où un brut par événement tiré de la ligne « Tous, +5 s, sortie +5 min » : moyenne −0,7 %, erreur type 1,4 % (n = 22) ;
- coût total aller-retour en pointe de 1,3-3,5 % ;
- 20 événements par an à 200 USD.

| Scénario | Brut/événement | Coût AR | Net/événement | Net/an (20 × 200 USD) | % du compte |
|---|---|---|---|---|---|
| Central | −0,7 % | 2,0 % | **≈ −2,7 %** | **≈ −110 USD** | **≈ −30 %/an** |
| Favorable (brut à +2 erreurs types, coût bas) | +2,1 % | 1,3 % | +0,8 % | ≈ +32 USD | ≈ +9 %/an |
| Défavorable | −3,5 % | 3,5 % | −7 % | ≈ −280 USD | ≈ −80 %/an |
| Hypothétique « latence ≤ 2 s sur Binance » (inaccessible) | +7 % (n = 6) | 3 % | +4 % | ≈ +160 USD | ≈ +45 %/an |

Intervalle à environ 95 % (brut −0,7 % ± 2 erreurs types, coût de 1,3 à 3,5 %) : net de **−7 % à +0,8 % par événement**, soit **≈ −80 % à +9 %/an** du compte.
La distribution par événement a une queue épaisse : ORCA +60 % et JUP −20 % dans l'échantillon. Le dernier scénario montre où se trouve l'argent : **dans les 2 premières secondes**, hors de portée sans colocation en Asie et sans flux payant, et interdit par nos contraintes de serveur.
Catégorie : **en échantillon, exploratoire** (22 événements, sans coût on-chain mesuré, aucune confirmation forward).

## 6. Verdict

- **Pas d'argent réel. Pas de test décisionnel dans l'immédiat.**
- **Test historique : faisable (données gratuites vérifiées pour Upbit, Binance et les prix CEX à la seconde) mais peu utile.** Le calcul exploratoire montre déjà que l'effet s'éteint avant notre délai minimal. Un test plus large ne ferait que préciser un nombre déjà sous le coût, sauf si notre délai réel s'avérait ≤ 2 s.
- **Ce qui serait utile et bon marché : H-R14a**, une mesure de latence sans argent. Un petit enregistreur sur le PC de l'auteur (serveur au Canada) sonde l'API Upbit (1 requête/s) et l'API CMS Binance (1 requête/s). Pour chaque nouvel avis, il note :
  - l'heure de détection moins `first_listed_at` / `releaseDate` ;
  - une cotation Jupiter (`lite-api`) du jeton s'il est sur Solana, à la détection puis à +5 s, +60 s et +5 min ;
  - le délai d'atterrissage d'une transaction **simulée**, sans signature réelle (`simulateTransaction`).

  Un mois d'enregistrement donne ≈ 10-20 annonces toutes chaînes confondues (≈ 1-3 jetons Solana). **Déclencheur** pour passer à H-R14b : délai médian de détection ≤ 1 s **et** délai de détection plus estimation d'atterrissage ≤ 2 s sur au moins 10 annonces. Sinon, on clôt H-R14.

## 7. Préenregistrement proposé — H-R14b (non exécuté, conditionnel à H-R14a)

- **Hypothèse.** Acheter le jeton à t0 + L, où L = délai mesuré par H-R14a (au moins 2 s), et le revendre à t0 + L + 5 min donne un net > 0 après coûts réalistes.
- **Population figée a priori.**
  - Toutes les annonces Upbit (`first_listed_at`) de 2023-01-01 → 2026-09-30 dont le titre contient « 신규 거래지원 » ou « 디지털 자산 추가 », pour un jeton **déjà coté sur le spot Binance** au moment de l'annonce. Toutes chaînes confondues : le mécanisme est le même et cela augmente la puissance, avec une estimation de 100-200 événements.
  - Toutes les annonces Binance « Will List » (`releaseDate`) pour un jeton ayant un perpétuel USDT-M avant l'annonce.
  - Sous-ensemble décisionnel secondaire : jetons Solana.
  - Les **22 événements déjà vus** dans cette fiche sont signalés et rapportés à part ; le verdict est donné sans eux.
- **Données.** Klines spot 1 s ou `aggTrades` (data.binance.vision). Pour le sous-ensemble Solana, vérification on-chain sur au moins 10 événements par RPC `getBlock` : prix du pool principal par slot, comparé au prix Binance à ±1 s.
- **Règle.**
  - Entrée : dernier prix à t0 + L, majoré d'un **coût d'entrée = max(1 %, |rendement de t0+L à t0+L+1 s|)** + écart coté (Exp 61, ou 0,35 % par défaut).
  - Sortie : dernier prix à t0 + L + 300 s, moins l'écart coté.
  - Une position à la fois, 200 USD.
  - Variantes rapportées sans effet : sorties à 60 s et 3 600 s, L + 3 s.
- **Critères.**
  - **PASS** si les trois conditions sont réunies : net moyen > +1 % par événement avec t ≥ 2 (erreur type sur événements) ; net > 0 dans chacune des deux moitiés chronologiques ; net > 0 sur le sous-ensemble Solana (n ≥ 20).
  - **REJET** si le net moyen ≤ 0, ou si l'une des deux moitiés est ≤ 0.
  - **INCERTAIN** sinon (pas d'argent, prolonger H-R14a).
- **Même en cas de PASS**, il faudrait encore une confirmation forward sans argent (H-R14a prolongé, ≥ 20 événements Solana, soit environ un an) avant tout ordre réel, à cause de l'écart entre le prix Binance et le remplissage on-chain.
- **Compteur de tests multiples** : 1 variante décisionnelle ; 3 rapportées sans effet ; plus les 30 cellules exploratoires de §2.1.

## 8. Stratégies dérivées regardées et écartées

| Idée | Raison |
|---|---|
| Vendre la pointe (dérive négative de J+1 à J+30) | Pas de vente à découvert accessible au Québec pour ces jetons (perps exclus, voir INDEX et H-R13). « Ne pas acheter » est la seule application. |
| Acheter **avant** l'annonce (deviner les listings) | La hausse de 3 h à 3 jours avant l'annonce vient d'informations d'initiés (Argus, WSJ, plaintes Upbit 2026). Une prédiction publique (feuille de route Coinbase, rumeurs) est un autre pari, au mauvais signe historique. Non poursuivi. |
| Fenêtre de 4 h entre l'annonce Binance et l'ouverture du marché | Le prix DEX monte dans les secondes qui suivent puis se fait vendre sur le CEX (CZ). Mesure exploratoire : depuis +30 s, sortie +1 h, −0,5 % en moyenne. Pas d'edge. |
| Annonces de perpétuels Binance (≈ 100/an) | Effet non mesuré ici ; même problème de vitesse. À regarder seulement si H-R14a passe. |

## Sources (consultées le 2026-10-08)

- L. Ante (2019), *Market Reaction to Exchange Listings of Cryptocurrencies*, Blockchain Research Lab WP 3 : https://www.blockchainresearchlab.org/wp-content/uploads/2019/10/Exploring-Market-Reactions-to-Exchange-Listings-of-Cryptocurrencies-BRL-working-paper3.pdf
- L. Ante (2021), *Cross-listings of blockchain-based tokens issued through initial coin offerings: do liquidity and specific cryptocurrency exchanges matter?*, Decisions in Economics and Finance : https://link.springer.com/article/10.1007/s10203-021-00323-0
- Asalio123, *binance-listing-study* (non académique) : https://github.com/Asalio123/binance-listing-study
- BeInCrypto, *Binance Token Listings Fail to Deliver in 2025* (non académique) : https://beincrypto.com/binance-listed-tokens-negative-return
- Blockmedia, *Key Takeaways from Upbit's New KRW Listings in 2025* (non académique) : https://www.blockmedia.co.kr/research-english/1064579 ; Four Pillars, *2025 Korean CEX listings post-mortem* : https://research.4pillars.io/en/research/2025-korean-cex-listings-post-mortem (429, non lu en entier)
- Fortune / WSJ, étude Argus 2022 (non académique) : https://fortune.com/crypto/2022/05/23/binance-ceo-changpeng-zhao-crypto-insider-trading-twitter-frontrunning
- CryptoRank, allégations de délit d'initié Upbit sur WIF et VVV (non académique) : https://cryptorank.io/news/feed/ca2ea-upbit-insider-trading-allegations-wif-vvv-listings
- cryptolisting.ws, délais par canal (non académique, commercial) : https://cryptolisting.ws/blog/how-to-detect-new-crypto-listings/ et https://cryptolisting.ws/blog/upbit-listing-effect-kimchi-premium/
- Dépôt « Upbit Crypto Listing Sniper Bot » (non académique) : https://github.com/VQuant68/Upbit-Crypto-Listing-Sniper-Bot
- Chorus One (2024-11), *Transaction Latency on Solana* (non académique, données de validateur) : https://chorus.one/reports-research/transaction-latency-on-solana-do-swqos-priority-fees-and-jito-tips-make-your-transactions-land-faster
- Arbitrage CEX-DEX sur Solana, fenêtre de 1 à 3 slots (non académique) : https://api.blog.jpool.one/?p=1096
- Sandwichs sur Solana : https://solanacompass.com/learn/accelerate-25/scale-or-die-at-accelerate-2025-the-state-of-solana-mev ; https://cryptobriefing.com/jupiter-ultra-sandwich-attacks-study/
- Coinbase, négociation DEX Solana dans l'application : https://thedefiant.io/coinbase-adds-native-solana-dex-trading ; https://www.theblock.co/post/379964/coinbase-vector-fun-tensor-solana-everything-exchange-vision
- Presse sur ACT/PNUT (Binance, 2024-11) et ORCA (Upbit, 2025-03) : https://cryptobriefing.com/solana-meme-coin-surge-binance/ ; https://www.cryptotimes.io/2025/03/21/orca-price-jumps-170-following-upbit-listing-announcement/
- GeckoTerminal, historique OHLCV : https://docs.coingecko.com/changelog/extended-historical-data-for-onchain-ohlcv-endpoint
- Dune, offre gratuite en lecture seule : https://cryptobriefing.com/dune-free-plan-view-only-access/
- Données (lectures publiques, 2026-10-08) : `https://api-manager.upbit.com/api/v1/announcements` ; `https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?catalogId=48` ; `https://data.binance.vision/data/spot/daily/klines/<SYM>/1s/` ; `https://data.binance.vision/data/futures/um/daily/aggTrades/<SYM>/`
- Internes : `docs/agents/research/H-R08_univers_solana_cout_bas.md`, `docs/agents/results/Exp-61_2026-10-08.md`, `docs/agents/research/H-R13_fourniture_liquidite.md`, `docs/agents/venues/VENUES_500CAD_2026-10-06.md`, `docs/research_plan_status.md`, `docs/agents/JOURNAL.md`.

## Scripts (exploratoires)

`docs/agents/research/H-R14_scripts/` :
- `upbit_fetch.py` : avis Upbit ;
- `upbit_count.py` : comptage par an ;
- `binance_fetch.py` : annonces CMS Binance ;
- `reaction_1s.py` : réaction en klines spot 1 s aux annonces Upbit ;
- `reaction_aggtrades.py` : réaction du perpétuel en `aggTrades` aux annonces de listing spot Binance.

Chaque script se lance avec `python -I` et écrit dans un dossier fourni en argument (zips dans un dossier vide dédié).
