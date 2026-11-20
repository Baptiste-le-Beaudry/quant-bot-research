# H-R18 — Swing (quelques jours à quelques semaines) et horizons intermédiaires (quelques heures à 1-3 jours) (T-063, agent Chercheur, 2026-10-10)

- **Branche :** `research/swing` (depuis `agents/orchestration-20261006`, commit 59acfaa).
- **Statut :** revue de littérature et calculs exploratoires légers. **Aucun test décisionnel.** Tous les chiffres calculés ici sont **exploratoires, ils ne comptent pas** et sont **en échantillon** : ils ont été regardés avant tout préenregistrement.
- **Scripts et sorties :** `docs/agents/research/H-R18_scripts/`.
  - Scripts : `fetch_daily.py`, `explore_swing.py`, `explore_swing2.py`, `explore_swing3.py`.
  - Sorties : `outputs/explore_swing*.json`, `outputs/L6_connors_port_daily.csv`.
  - Les données Yahoo sont téléchargées dans le scratchpad de session, jamais dans `data/`. `fetch_daily.py` les reproduit.
- **Sources** consultées le 2026-10-10, listées au §10. « Non académique » signale un praticien ou un blogue.
- **Capital de référence :** 15 000 CAD = 10 550 USD (H-R16). Compte IBKR **imposable** : le trading actif est exclu du CELI (H-R16 §3.5).
- **Coûts IBKR retenus :**
  - **1 USD minimum par ordre** (tarif fixe 0,005 USD/action), comme demandé ;
  - le tarif « tiered » (0,0035 USD/action, minimum 0,35 USD, plus frais de bourse et de régulation) est rapporté en variante.

## 0. Réponse courte

1. **Rien ne tient à 15 %/an avec un risque favorable.** Je n'ai trouvé aucune piste swing ou intermédiaire, testable avec des données gratuites, dont l'espérance nette dépasse clairement celle de l'indice détenu dans le CELI, sans impôt (SPY 2009-2026 : Sharpe ≈ 0,87-0,88, exploratoire).
2. **Un seul effet est solide et survit aux coûts : le retour à la moyenne sur 2 à 5 jours des FNB indiciels** (familles RSI(2) de Connors et IBS).
   - Exploratoire sur 35 FNB actions, 2017-2026, après la publication de Connors (2008) : RSI(2) donne **+0,37 % brut par trade** (n = 2 631, t = 9,8), tenu 3,6 jours en moyenne.
   - Le coût IBKR est d'environ 0,10 % aller-retour pour une position de 2 600 USD.
   - **Mais c'est un effet de marché, pas de sélection.** Une fois couvert par une vente de SPY, l'IBS du panier tombe à **−0,006 %/jour en 2017-2026** (L8). Il ne reste qu'un rebond de l'indice après une baisse.
   - Un portefeuille réaliste à 5 cases ne rapporte qu'environ **+4 %/an** (Sharpe 0,43, MaxDD −19 % en 2017-2026). La raison : il n'est investi qu'à environ 37 % du temps.
   - Son intérêt réel est un **complément faiblement corrélé** à un cœur en actions, pas un moteur de rendement.
3. **Le rendement de nuit sur SPY est surtout du bêta.** Exploratoire 2017-2026 : la nuit seule donne un Sharpe de 0,74, contre 0,88 pour la détention de SPY.
   - Avec 1 USD par ordre, détenir toutes les nuits coûte ≈ 4,8 %/an sur 10 550 USD.
   - Les FNB NightShares, qui vendaient exactement cette idée, ont fermé en 2023 après −3 % contre +15 % pour le S&P 500.
4. **PEAD, prime d'annonce de résultats et dérive pré-FOMC sont morts ou mourants pour les grandes capitalisations** : Martineau 2022 ; « Disappearing EAP » 2020 ; Kurov, Wolfe et Gilbert 2021.
   - **La rotation sectorielle hebdomadaire est nulle** (L4).
   - **Le crypto à 1-3 jours est incohérent d'une pièce à l'autre** (L5), et sa famille est déjà rejetée (Exp 56, 66, 68, BR1-BR2, B1-B8).
5. **Les cassures de type Minervini ou Qullamaggie et le momentum court sur actions ne se testent pas honnêtement avec des données gratuites**, à cause du biais du survivant.
   - La seule étude indépendante sans ce biais (Zarattini, Pagani et Wilcox 2025) tient des positions **pendant des mois**, et ses auteurs la disent difficile à mettre en œuvre sous 1 M USD.
   - Les données sans survivant (Norgate Platinum) coûtent **630 USD/an, soit 6 % du capital par an**.
6. **Deux préenregistrements sont proposés** (§7). Ce sont des tests de rejet rapides : moins d'une heure chacun, données gratuites ou déjà en cache.
   - **Exp A :** RSI(2) sur 4 FNB indiciels US, ordres MOC, cash inactif placé en T-bills.
   - **Exp B :** SPY détenu la nuit seulement, MOC → MOO.

   **Mon attente :** A finit en INCERTAIN ou en PASS modeste (≈ +5-8 %/an, T-bills compris) ; B finit en REJET avec 1 USD par ordre.

## 1. Anti-doublon (lu avant tout calcul)

Lus : `AGENT_RULES.md`, `REPRISE.md` §3, `REGISTRY.csv` (Exp 49-71), `research/INDEX.md`, `H-R15` (§0-1, §4), `H-R16` (en entier), `H-R06`, `hypotheses/Exp-56.md`, `results/Exp-62`, `results/Exp-66`, `results/Exp-68`, `research_plan_status.md` (programme « exit-timing », pistes 1-4, Exp 43-46b), `strategy_b/STRATEGY_B_RESEARCH_LOG.md` (B1-B8, BF1-BF2, BR1-BR2).

| Recouvrement | Avec | Différence et risque de doublon |
|---|---|---|
| Crypto 1-3 jours (piste 5) | **Exp 56** (TSMOM 7 j, REJET) ; **Exp 68** (tendance multi-horizons long/cash, REJET en P2) ; **Exp 66** (heures, REJET) ; **BR1/BR2** (rotation 7 j top-2 / bottom-2 sur 9 cryptos, REJET) ; **B1-B8** (cassures 1-15 min, REJET) ; **exit-timing** (Exp 43-46b : tenir les entrées A plus longtemps, REJET) | Seul « acheter après une chute journalière de −2σ, tenir 1-3 j » n'avait pas été regardé. L5 le trouve incohérent (BTC +, ETH −, SOL −). **Risque de doublon : élevé.** Pas de préenregistrement. |
| Retour à la moyenne 2-5 j (piste 1) | **Exp 62** (A-Equity 1 min chez IBKR, REJET à 500 CAD : coût de 0,46 % contre +0,05 % de brut) ; **H-R06** (fin de séance SPY) | Autre horizon (jours, pas 50 minutes) ; edge brut 10 fois plus grand par trade (+0,3 à +0,6 %) ; positions de 2 600 USD et non 160 USD. **Pas un doublon.** |
| Nuit / jour (piste 4) | **H-R06** (dernière demi-heure), **Exp 64-65, 70-71** (zone de bruit intrajournalière, futures) | Jamais testé comme détention de la clôture à l'ouverture. **Pas un doublon.** |
| Rotation sectorielle (piste 6) | **H-R16 §3.5** (GEM, GTAA-5 mensuels, regardés) ; BR1 (crypto) | Hebdomadaire sur FNB actions jamais regardé ; L4 le trouve nul. Pas de préenregistrement. |
| Tournant du mois | **T-030 en file** (`REPRISE.md` §3, point 5) | L7 est un regard exploratoire sur SPY. Il ne remplace pas T-030 (voir §3.7). |

## 2. Données gratuites et biais du survivant

| Source | Contenu | Profondeur | Survivant | Usage |
|---|---|---|---|---|
| Yahoo (`yfinance` 1.5.2, vérifié le 2026-10-10) | OHLCV journalier non ajusté + Adj Close | SPY 1993-01, secteurs SPDR 1998-12, pays iShares 1996-03, QQQ 1999-03, IWM 2000-05, BTC 2014-09 | **Actions radiées absentes.** FNB : seuls ceux encore cotés | décisionnel pour FNB |
| Yahoo horaire | barres 60 min | **730 derniers jours seulement** | idem | contrôle d'exécution récent |
| Dukascopy 1 min (déjà en cache, `data/indices/`) | CFD SP500, NASDAQ100, DOW30, RUSSELL2000 | 2011-09, 2011-09, 2013-09, 2018-08 → 2026 | sans objet (indices) | **étape 0** : signal calculé à 15:50 ET au lieu du close |
| SEC EDGAR (submissions API, 8-K item 2.02) | dates d'annonce de résultats, horodatées | ≈ 2004 → | inclut les sociétés radiées | seulement si la piste PEAD ou EAP rouvrait |
| GitHub `fja05680/sp500` (non vérifié ici) | membres historiques du S&P 500 | 1996 → | liste sans biais, mais **prix des radiées absents chez Yahoo** | univers figé, biais documenté |
| Norgate Platinum (payant) | actions US, radiées comprises, membres d'indices historiques | 1950 → | sans biais | 630 USD/an = 6 % du capital/an : **non recommandé** à 15 k |
| Stooq | journalier | — | — | non revérifié en 2026 (accès automatisé limité) ; Yahoo suffit pour les FNB |

**Traitement du biais du survivant :**
- **Préférer les FNB.** Les 4 FNB indiciels de l'Exp A (SPY, QQQ, IWM, DIA) étaient déjà les plus gros et les plus liquides en 2000-2005. On les choisit pour leur liquidité, connue d'avance, pas pour leur performance.
- **Biais résiduel faible :** un FNB indiciel ne « fait pas faillite ». Le panier de 35 FNB regardé ici (pays, secteurs) contient seulement des fonds encore cotés. Des fonds de pays ou de secteurs fermés depuis 1996 en sont absents. Ce biais est probablement faible et n'a pas été mesuré.
- **Actions individuelles :** aucun test honnête n'est possible avec Yahoo seul.
  - Un univers figé dans le passé (par exemple le S&P 500 au 2018-12-31) perd chez Yahoo toutes les sociétés radiées depuis. Elles le sont surtout par fusion, soit environ 15-25 % de l'univers en 7 ans (ordre de grandeur, non mesuré).
  - Le biais n'a pas de signe connu pour une stratégie de cassure : on perd à la fois des gagnants rachetés et des perdants radiés.
  - **Conclusion :** les pistes sur actions (cassures, momentum court, renversement résiduel, PEAD) restent hors préenregistrement tant qu'il n'y a pas de données sans survivant.

## 3. Détail par piste

Convention de tous les chiffres exploratoires :
- remplissage au close (ou à l'open) journalier Yahoo, ajusté des dividendes et splits ;
- coût indiqué à chaque ligne ;
- catégorie : **en échantillon**.

Périodes : 1993/1996-2008 (avant ou autour de la publication de Connors 2008, de Cooper et al. 2008 et de Pagonidis 2014 pour l'IBS), 2009-2016 et 2017-2026-10-09.

### 3.1 Retour à la moyenne 2-5 jours sur FNB (RSI(2), IBS, baisse de N jours avec filtre de tendance)

**Mécanisme :**
- Fourniture de liquidité : après une vente forcée ou impatiente, les teneurs de marché exigent une prime qui se rembourse en quelques jours (Nagel 2012, déjà cité en H-R01).
- Inventaire des intermédiaires : Boyarchenko, Larsen et Whelan (RFS 2023) montrent que les ventes massives de fin de séance sont suivies d'un **rebond de nuit robuste**, alors que les hausses ne se retournent presque pas. Cette asymétrie est la base de l'achat de creux au close.
- Au niveau de l'indice, l'autocorrélation journalière du S&P 500 est négative depuis 2000 (Lewellen ; Portnaya 2026 : ρ(1) = −0,081 pour SPY 1993-2026).
- **Mais Portnaya (arXiv 2606.29591, 2026-06)** trouve que ce ρ(1) vient de **l'amplitude** et non du signe : le test de signe ne rejette pas à 1 jour (p = 0,11). La seule inversion directionnelle significative est **au retard 3** (p = 0,02). Cela va dans le sens d'une sortie après plusieurs jours (RSI(2) avec sortie au-dessus de la SMA5) plutôt que d'un aller-retour sur 1 jour (IBS).

**Preuves après publication et après coûts :**
- Connors (2008) : RSI(2) < 5 ou < 10 au-dessus de la SMA200, sortie au-dessus de la SMA5. Aucune étude académique indépendante.
- Backtrex (non académique, 2016-2026, S&P 500, RSI(2) < 5 long et court) : +1,7 %/an contre +13,5 % pour la détention. Taux de gain 71 %, PF 1,43, 73 trades.

  Lecture : **l'edge par trade existe, mais l'exposition est trop faible pour qu'il pèse.**
- IBS : Pagonidis (2014, FNB jusqu'en 2013) ; arXiv 2306.12434 (2023, FNB pays sur 10 ans) confirme le pouvoir prédictif.

**Exploratoire (ne compte pas) :**

| Regard | 1993/96-2008 | 2009-2016 | 2017-2026 |
|---|---|---|---|
| L1 IBS < 0,2, close → close suivant, 35 FNB actions : brut/trade | +0,274 % (t 21,5, n 22 748) | +0,206 % (t 14,4) | **+0,131 % (t 11,3, n 16 922)** |
| L1 même règle, contrôle obligations, or, pétrole (5 FNB) | +0,054 % (t 1,2) | −0,014 % | +0,057 % (t 1,7) |
| L1 SPY seul | +0,162 % (t 3,4) | +0,185 % (t 2,5) | +0,133 % (t 2,0, n 437) |
| L1 portefeuille (capital réparti sur les signaux du jour, 0,03 % AR) : CAGR / MaxDD / Sharpe | 88 % / −22 % / 3,2 (**prix figés des FNB pays, non exécutable**) | 14,5 % / −25 % / 0,87 | **8,6 % / −33 % / 0,57** |
| **L8 même portefeuille couvert par SPY** (0,06 % AR) : moyenne/jour à signal, Sharpe | +0,36 %, 4,24 | +0,03 %, −0,57 | **−0,006 %, −1,21** |
| L2 RSI(2) < 10, close > SMA200, sortie close > SMA5 (max 10 j), 35 FNB : brut/trade | +0,586 % (t 12,3) | +0,416 % (t 8,1) | **+0,369 % (t 9,8, n 2 631)** |
| L2 SPY seul | +0,83 % (n 116) | +0,43 % (n 65, t 1,6) | **+0,58 % (n 84, t 3,6)** |
| L2 contrôle (obligations, or, pétrole) | +0,09 % | +0,16 % | +0,19 % (t 1,2) |
| L6 portefeuille RSI(2), 5 cases de 20 %, 0,05 % AR, cash à 0 : CAGR / MaxDD / Sharpe / exposition moyenne | 9,2 % / −11 % / 0,93 / 1,44 case | 4,0 % / −17 % / 0,45 / 1,7 | **3,8 % / −19 % / 0,43 / 1,87** |

Années de L6 en 2017-2026 : +14,0 ; −11,1 ; +2,5 ; +3,7 ; +4,4 ; −8,3 ; +2,5 ; −0,9 ; +13,0 ; +21,1 (2026 partiel).

**Lecture :**
1. L'edge par trade est réel et persistant après publication, mais il **décroît d'environ 40 %** d'une décennie à l'autre.
2. Il vient du **niveau du marché**, pas d'un choix entre FNB (L8). Les contrôles hors actions sont proches de zéro, ce qui va dans le sens du mécanisme « actions et liquidité ».
3. La faiblesse du portefeuille vient de l'**exposition** : le portefeuille est investi en moyenne à 37 %, et le reste dort.
   - En plaçant le cash inactif en T-bills (SGOV, ≈ 3,9 %), on gagnerait environ +2,4 points.
   - Le Sharpe resterait **sous celui de SPY**.
   - L'intérêt est un **alpha** contre SPY, à mesurer : c'est le critère de l'Exp A.

**Coûts IBKR à 15 k :**
- Position de 2 640 USD (4 cases) : 1 USD × 2 = 0,076 %, plus frais d'enchère et de régulation ≈ 0,01 %, plus 0,01 % de prudence ⇒ **≈ 0,10 % AR**, soit 15-25 % du brut.
- En tiered : ≈ 0,04 % AR.

**Ordres de grandeur :**
- Trades : ≈ 30-40 par an sur 4 FNB indiciels (SPY seul : 8,6/an) ; ≈ 270 par an sur 35 FNB.
- Historique : 26 ans (IWM 2000-05).
- **Pire drawdown attendu : −20 à −30 %.** Exploratoire : −19 % ; 2008 n'est pas couvert par le filtre SMA200 en début de baisse. Un krach éclair au-dessus de la SMA200, comme février 2020, déclenche plusieurs achats à la fois.

### 3.2 Renversement hebdomadaire (Lehmann 1990, Lo-MacKinlay 1990) et « residual reversal » (Robeco)

**Mécanisme :**
- Les perdants de la semaine rebondissent (Lehmann).
- Lo et MacKinlay montrent qu'une grande part des profits contrarians vient des **corrélations croisées** (les grandes capitalisations mènent les petites) et non d'une surréaction.
- La version « résiduelle » (Blitz, Huij, Lansdorp et Verbeek 2013) trie sur le rendement débarrassé des facteurs : elle est moins exposée aux krachs.

**Preuves après coûts :**
- De Groot, Huij et Zhou (2012) : 30-50 pb par semaine nets sur les grandes capitalisations, **pour un investisseur institutionnel**.
- Blitz, Hanauer, Honarvar, Huisman et van Vliet (FAJ 2023, Robeco) : alpha net seulement en combinant 5 signaux courts sur un **univers mondial liquide**, avec des règles d'achat et de vente qui réduisent la rotation. L'alpha tient hors échantillon et se transpose en long seul.
- **Medhat et Schmeling (RFS 2022)** : parmi les actions à **forte rotation**, c'est-à-dire les grandes et les plus suivies, le mois passé donne du **momentum**, pas du renversement. Le renversement ne survit que dans les titres peu échangés, donc coûteux.

**À 15 k :**
- 20-30 lignes de 350-500 USD, avec 1 USD minimum ⇒ 0,2-0,3 % par côté, chaque semaine. Le coût dépasse l'alpha.
- Le résiduel exige des données de facteurs et un univers sans survivant.

**Verdict : écarté** (coûts, données).

### 3.3 Dérive après résultats (PEAD) et prime d'annonce (EAP)

- **PEAD :** Martineau (CFR 2022) : « inexistante pour les grandes capitalisations depuis 2006 », disparue plus récemment pour les microcapitalisations. Elle demande les surprises de consensus, **non gratuites** (Zacks, I/B/E/S).
- **EAP :** Frazzini et Lamont (2007) ; Savor et Wilson (2016) ; Barber et al. (2013, mondial).
  - « The Disappearing Earnings Announcement Premium » (2020) : la prime ne subsiste que pour les sociétés qui ne déposent pas de 8-K, ce qui ne nous concerne pas.
  - Les dates d'annonce sont gratuites et sans biais via EDGAR (8-K item 2.02), mais les prix des sociétés radiées manquent chez Yahoo.
- **À 15 k :** ≈ 4 annonces par titre et par an ; position de 1 500 USD ⇒ 0,13 % de commission AR plus 0,02-0,05 % d'écart. Il faudrait une prime d'au moins 0,3 % sur 2-3 jours.

**Verdict : écarté** (effet disparu, coûts).

### 3.4 Cassures après consolidation (Minervini, Qullamaggie) et tendance sur actions

**Mécanisme :**
- Ancrage sur les plus hauts (George et Hwang 2004 : plus haut de 52 semaines, horizon mensuel).
- Sous-réaction aux nouvelles, puis flux de momentum.

**Preuves :**
- **Aucune étude indépendante** des règles VCP (Minervini) ou des « episodic pivots » (Qullamaggie) n'a été trouvée. Les résultats publiés viennent des auteurs eux-mêmes, par exemple des championnats US Investing, et souffrent du biais du survivant.
- Seule référence sérieuse : **Zarattini, Pagani et Wilcox (2025)**, qui prolongent Wilcox et Crittenden (2005).
  - Règle : achat au plus haut historique, sortie par stop suiveur ATR(42).
  - Données sans survivant, 1950-2024, 66 000 trades ; le résultat tient hors échantillon en 2005-2024.
  - CAGR ≈ 15 %, alpha ≈ 6 %/an, MaxDD ≈ −32 %.
  - Mais : moins de 7 % des trades font l'essentiel du profit ; volatilité ciblée de 30 % avec levier jusqu'à 2× ; positions tenues **des mois** ; les auteurs jugent la stratégie difficile **sous 1 M USD** à cause des coûts.

**À 15 k :**
- 5-8 positions seulement, alors que le profit dépend de quelques rares gagnants extrêmes : la variance d'un compte de cette taille est énorme.
- **Test honnête impossible avec des données gratuites** (§2).

**Verdict : non préenregistré.** À rouvrir seulement si l'auteur accepte de payer Norgate (630 USD/an) et de dépasser 15 k.

### 3.5 Rendement de nuit contre rendement de jour

**Mécanisme :**
- Cooper, Cliff et Gulen (2008) : toute la prime actions US 1993-2006 est gagnée la nuit.
- Lou, Polk et Skouras (JFE 2019) : le momentum se gagne la nuit, les autres anomalies le jour ; « tug of war » entre particuliers (la nuit) et institutions (le jour).
- Boyarchenko, Larsen et Whelan (RFS 2023) : la dérive de nuit est concentrée à l'ouverture européenne et liée aux déséquilibres d'ordres de la clôture (inventaire des intermédiaires).

**Après publication :** les FNB **NightShares** (NSPY, NIWM), lancés en 2022-06, ont fermé le 2023-08-10.
- Sur un an : NSPY −3 %, NIWM −6 %, contre +15 % pour le S&P 500.
- La raison invoquée : les coûts et une période où le jour a battu la nuit.

**Exploratoire (L3, ne compte pas) :**

| Instrument | Période | Nuit : moyenne/nuit (t) | Jour : moyenne (t) | Nuit seule, 1 pb de coût : CAGR / MaxDD / Sharpe | Détention : CAGR / MaxDD / Sharpe |
|---|---|---|---|---|---|
| SPY | 2009-2016 | +0,026 % (1,8) | +0,033 % | 3,5 % / −15 % / 0,39 | 14,4 % / −27 % / **0,87** |
| SPY | 2017-2026 | +0,044 % (3,0) | +0,019 % | 8,3 % / −30 % / 0,74 | 15,4 % / −34 % / **0,88** |
| QQQ | 2017-2026 | +0,056 % (3,2) | +0,032 % | 11,3 % / −29 % / 0,84 | 21,6 % / −35 % / **0,98** |
| IWM | 2017-2026 | +0,066 % (3,6) | −0,021 % | 13,9 % / −29 % / **0,97** | 9,1 % / −41 % / 0,49 |

- Nuit après une journée SPY ≤ −1 % (version Boyarchenko) : +0,08 %/nuit (≈ 27 nuits/an, t ≈ 1 par période). C'est le double de la nuit moyenne, mais trop rare pour peser.
- **Coût réel :** 2 ordres par jour ouvrable.
  - À 1 USD : 504 USD/an = **4,8 %/an** sur 10 550 USD, plus les frais d'enchère et SEC (≈ 0,3 %/an).
  - En tiered : ≈ 1,9 %/an.
  - Sur 3 FNB à la fois, le coût triple : impossible.
- **Lecture :**
  - SPY et QQQ : la nuit seule a un Sharpe **inférieur** à la détention, même avant le coût de 1 USD.
  - IWM fait exception en 2017-2026, mais le choisir *après* l'avoir vu serait de la sélection interdite.
  - **Fiscalité :** 252 aller-retours par an dans un compte imposable donnent probablement un revenu d'entreprise, imposé à 100 %.

  **Prédiction : REJET.** L'Exp B ferme la question proprement et à bas coût.

### 3.6 Momentum ou renversement crypto de quelques heures à 1-3 jours

**Littérature :**
- Les grandes cryptos montrent du **momentum** journalier et hebdomadaire. Le renversement n'existe que dans les jetons peu liquides : FFA WP 2023 ; « Cryptocurrency return reversals » (Fairfield) ; HSE.
- Liu, Tsyvinski et Wu (JF 2022) : momentum de 1 à 4 semaines **en coupe transversale**. Avec 3 jetons, il n'y a pas de coupe exploitable, et BR1 est déjà rejeté.
- Portnaya (2026) : les cryptos se comportent comme une marche aléatoire au retard 1.

**Exploratoire (L5, P1 seulement, ≤ 2025-03-27 ; P2 non regardé pour ne pas le contaminer).** Après un jour < −2σ(30 j) :

| Jeton | Rendement à 1 jour | Rendement à 3 jours |
|---|---|---|
| BTC | +0,69 % (n 108, t 1,3) | +1,73 % (t 2,6) |
| ETH | +0,75 % | **−0,69 %** |
| SOL | +0,48 % | **−4,08 %** |

- Moyennes inconditionnelles à 3 jours : BTC +0,61 %, ETH +0,52 %, SOL +1,49 %.
- **Incohérent** entre jetons, dans une famille déjà rejetée cinq fois (Exp 56, 66, 68, BR1-BR2, A tenue plus longue).

**Verdict : écarté.** Le coût Jupiter (0,02 %) n'est pas le problème ; c'est l'absence d'edge.

### 3.7 Rotation sectorielle à 1-4 semaines, tournant du mois, autres

- **Secteurs (L4, ne compte pas) :** classement des 9 SPDR sur 5 jours, tenue d'une semaine, écart avec le panier égal.
  - Top-3 : −0,06 / −0,04 / −0,02 % par semaine sur les 3 périodes.
  - Bottom-3 : +0,10 / +0,03 / **+0,017 %** (t 0,35 en 2017-2026).
  - **Nul.** Le momentum d'industrie de Moskowitz et Grinblatt (1999) est mensuel ; il relève de la famille GTAA/GEM déjà vue en H-R16.
- **Tournant du mois (L7, SPY ; T-030 en file) :** de la clôture de l'avant-dernier jour du mois à la clôture du 3e jour du mois suivant.
  - Rendement : +0,35 / +0,24 / +0,32 % par fenêtre, contre +0,11 / +0,24 / +0,25 % pour 4 jours moyens.
  - L'excès est **≈ 0 en 2009-2016** et ≈ +0,06 % en 2017-2026 (t < 2).
  - Faible. T-030 peut rester en file, avec une attente basse.
- **Dérive pré-FOMC :** Lucca et Moench (JF 2015) ; disparue après 2015 selon Kurov, Wolfe et Gilbert (FRL 2021). Écartée.
- **Effet d'inclusion dans un indice :** en disparition (Greenwood et Sammon). Écarté, déjà en H-R15.

## 4. Classement

Critère : espérance nette réaliste × probabilité que ce soit vrai ÷ coût du test. Le concurrent est **SPY ou XEQT détenu dans le CELI, sans impôt**. Une stratégie du compte imposable doit apporter un **alpha** contre cet indice, pas seulement un rendement positif.

| Rang | Piste | Edge brut (exploratoire ou littérature) | Coût IBKR à 15 k | Trades/an | Historique gratuit | Pire DD attendu | Rendement net attendu | Décision |
|---|---|---|---|---|---|---|---|---|
| **1** | Retour à la moyenne 2-5 j, FNB indiciels US, RSI(2) (§3.1) | +0,37 % (panel) à +0,58 % (SPY) par trade, 2017-2026 | ≈ 0,10 % AR (1 USD) | 30-40 | 26 ans | −20 à −30 % | **+5 à +8 %/an T-bills compris** ; alpha ≈ +1 à +4 %/an si vrai | **Préenregistrement Exp A** |
| **2** | Nuit seule SPY, MOC → MOO (§3.5) | +0,044 %/nuit 2017-2026 ; Sharpe < détention | 0,019 %/nuit (1 USD) = 4,8 %/an | 252 | 33 ans | −30 % | **≈ +4 à +7 %/an** ; alpha ≈ 0 | **Préenregistrement Exp B** (test de rejet rapide) |
| 3 | Tournant du mois SPY (T-030) | excès ≈ 0 à +0,06 %/fenêtre | 0,02 % AR | 12 | 33 ans | −10 à −15 % | +3-4 %/an + T-bills | laisser T-030 en file, attente basse |
| 4 | Cassures et tendance sur actions (§3.4) | alpha ≈ 6 %/an (ZPW 2025, > 1 M USD, mois de détention) | 1 USD sur des lignes de 1-2 k = 0,1-0,2 % AR + données 6 %/an | 20-60 | **non testable gratuitement sans biais** | −30 à −40 % | inconnu ; négatif net de données à 15 k | écarté (données) |
| 5 | Momentum court des grandes capitalisations (Medhat-Schmeling) | ≈ momentum classique, échantillon → 2018 | 0,1 % AR par mois | 120 | non testable gratuitement (rotation, radiées) | −30 % | inconnu | écarté (données) ; vrai hors échantillon 2019-2026 possible si données payantes |
| 6 | Renversement hebdomadaire et résiduel (§3.2) | 30-50 pb/sem. institutionnel | 0,4-0,6 % AR par semaine | > 1 000 | non testable sans biais | −20 % | négatif à 15 k | écarté |
| 7 | Rotation sectorielle hebdomadaire (§3.7) | ≈ 0 (L4) | 0,02-0,05 % | 52 | 27 ans | — | ≈ 0 | écarté |
| 8 | PEAD / EAP (§3.3) | disparus pour les grandes capitalisations | 0,15-0,2 % AR | 100-400 | dates gratuites, surprises payantes | — | ≈ 0 ou négatif | écarté |
| 9 | Crypto 1-3 j après une chute (§3.6) | incohérent entre jetons | 0,02 % (Jupiter) | 10-40 | 5-11 ans | −30 % | ≈ 0 | écarté (famille rejetée) |
| 10 | Pré-FOMC, inclusions | disparus après publication | — | 8 | — | — | ≈ 0 | écarté |

## 5. Pourquoi l'horizon plus long n'a pas suffi

La consigne avait raison sur un point : à 2-5 jours, les coûts IBKR deviennent petits devant le mouvement (0,10 % contre 0,4-0,6 % brut). **Ils ne sont plus le problème.**

Le problème est ailleurs. Les effets de quelques jours qui restent après 2009 sont des **effets de marché** : rebond de l'indice après une baisse, nuit contre jour, tournant du mois.
- Ils ne sont présents qu'une petite fraction du temps.
- Leur Sharpe par unité de temps investi est bon. Mais un portefeuille investi à 20-40 % du temps a un Sharpe annuel **inférieur à la simple détention de l'indice**, qui touche la prime actions tous les jours.

Ces stratégies ne battent la détention que comme **complément** : un alpha positif et une faible corrélation. Pour un compte de 15 k, ce complément vaut quelques points par an, **pas 15 %**.

## 6. Arithmétique honnête pour 15 000 CAD

| Combinaison | Rendement attendu | MaxDD attendu | Commentaire |
|---|---|---|---|
| XEQT dans le CELI (H-R16 P_B) | +6-8 %/an, sans impôt | −50 % en 2008 | référence |
| 60/20/20 dans le CELI (H-R16 P_A) | +5-6 %/an | −17 à −30 % | référence prudente |
| Exp A si PASS, compte imposable, cash en SGOV | **+5 à +8 %/an avant impôt** (alpha +1 à +4, T-bills ≈ +2,5) ; ≈ +3,5 à +5,5 % après un impôt marginal de 37 % | −20 à −30 % | complément, pas un moteur |
| Exp B si, contre mon attente, PASS | +4-7 %/an avant impôt | −30 % | dominé par la détention dans le CELI |

**15 %/an n'est atteint par aucune piste swing que j'ai pu vérifier.**

## 7. Préenregistrements proposés (à exécuter par l'orchestrateur ; numéros à attribuer, prochain libre : Exp 72)

Discipline commune :
- **l'historique ne peut que rejeter**, et toutes les périodes ont été partiellement vues ici (§8) ;
- la confirmation vient d'un **forward papier** (règle D-05) ;
- un seul processus Python lourd à la fois ; données Yahoo téléchargées dans un dossier isolé, avec le hash du fichier noté dans le résultat.

### 7.1 Exp A — Retour à la moyenne 2-5 jours sur FNB indiciels US (RSI(2) de Connors), ordres MOC

- **Question :** sur la période qui suit la publication (2009-2026), la règle RSI(2) de Connors, appliquée à 4 FNB indiciels US avec des ordres au close, donne-t-elle un **alpha net positif contre SPY**, avec un drawdown acceptable, sous les coûts IBKR réels d'un compte de 10 550 USD ?
- **Univers figé :** SPY, QQQ, IWM, DIA. Aucun ajout ni retrait.
- **Données :**
  - Yahoo journalier (`fetch_daily.py`), OHLC multipliés par Adj Close / Close ;
  - T-bills : `^IRX` (rendement annualisé / 252 par jour) ;
  - étape 0 : CFD Dukascopy 1 min dans `data/indices/` (SP500, NASDAQ100, DOW30, RUSSELL2000), en lecture seule.
- **Périodes :**
  - décisionnelle : **2009-01-02 → 2026-09-30**, coupée en **H1 2009-2016** et **H2 2017-2026** ;
  - rapportée sans effet : 2000-06 → 2008-12 (avant publication).
- **Règle (unique) :**
  - Pour chaque FNB, au jour *t* : signal d'entrée si RSI(2) de Wilder (lissage α = 1/2) < 10 **et** close > SMA200 du close.
  - Achat au close de *t* (MOC), **25 % de l'équité du compte au close de t−1**, au plus une position par FNB.
  - Sortie au close du premier jour *j > t* où close > SMA5, ou au close de *t + 10* jours de bourse.
  - Pas de stop. Pas d'entrée le jour d'une sortie sur le même FNB.
  - Cash inactif : SGOV (avant 2020-06 : `^IRX`), moins 0,10 %/an. Chaque entrée et chaque sortie déclenche aussi un ordre SGOV, qui coûte 1 USD.
- **Coûts décisionnels :**
  - 1,00 USD par ordre (FNB et SGOV) ;
  - frais SEC sur les ventes, au taux en vigueur sur la période ;
  - frais d'enchère 0,0012 USD/action par côté (non vérifié : à confirmer par l'agent Plateformes) ;
  - 0,01 % par côté de prudence pour l'écart entre l'enchère de clôture et le close Yahoo.
- **Étape 0 (exécution, obligatoire avant le PnL) :**
  - Recalculer chaque signal (entrée et sortie) avec un prix à **15:50 ET** au lieu du close. Pour le FNB : P(15:50) = close × indice CFD(15:50) / indice CFD(16:00).
  - Fenêtres : SPY 2013-06+ (qualité Exp 64), QQQ 2012-02+, DIA 2013-10+, IWM 2018-08+.
  - Mesurer la part de signaux identiques et le net/trade de la version « 15:50 », en gardant les fills au close.
  - **REJET technique** si la version 15:50 garde moins de 50 % du net/trade de la version au close.
- **PASS (tous requis), sur 2009-2026 net :**
  1. net moyen par trade ≥ +0,20 %, t ≥ 2,5 (trades groupés sur les 4 FNB) ;
  2. alpha annualisé contre SPY ≥ +2,0 %/an, t de Newey-West (5 retards) ≥ 2,0. Régression des rendements journaliers du compte en excès de T-bill sur ceux de SPY ;
  3. CAGR net ≥ +5 %/an, T-bills compris ;
  4. MaxDD ≥ −20 % ;
  5. alpha > 0 **et** net/trade > 0 dans H1 et dans H2 ;
  6. net/trade > 0 sur au moins 3 des 4 FNB ;
  7. étape 0 : la version 15:50 garde ≥ 70 % du net/trade.
- **REJET** si l'une de ces conditions est vraie :
  - net/trade < +0,10 % ou t < 1,5 ;
  - alpha ≤ 0 ;
  - une moitié avec un alpha ≤ 0 **et** un net/trade ≤ 0 ;
  - MaxDD < −30 % ;
  - étape 0 < 50 %.

  **INCERTAIN** sinon.
- **Variantes rapportées sans effet sur le verdict :**
  - (a) commission tiered (0,35 USD minimum + frais) ;
  - (b) coût doublé (stress) ;
  - (c) cash à 0 ;
  - (d) entrée à l'open de *t + 1* (exécution tardive) ;
  - (e) IBS < 0,2 sur les mêmes 4 FNB, tenue 1 jour ;
  - (f) panier de 35 FNB à 5 cases (déjà vu en L6).

  **Une seule règle décisionnelle.**
- **Si PASS :** forward papier d'au moins 6 mois et au moins 25 trades.
  - Signal calculé en direct à 15:50 ET à partir de cotations IBKR papier ou Yahoo.
  - PnL au close officiel.
  - Critère forward : net/trade ≥ 0 et écart moyen entre fill papier et close ≤ 0,05 %.
  - Argent réel seulement après un « go » de l'auteur.
- **Ma prédiction :** PASS 25 %, INCERTAIN 35 %, REJET 40 %.
  - Le risque principal est le critère d'alpha : SPY seul fait +0,58 %/trade, mais seulement 84 trades en 10 ans.
  - Le second risque est le MaxDD les années de krach rapide (2018, 2020, 2022).

### 7.2 Exp B — SPY détenu la nuit seulement (MOC → MOO)

- **Question :** détenir SPY de la clôture à l'ouverture suivante donne-t-il un **alpha net contre la détention de SPY**, avec 1 USD par ordre, après la publication de Cooper, Cliff et Gulen (2008) ?
- **Univers figé :** SPY seul. C'est l'instrument de référence de la littérature ; QQQ et IWM ne sont **pas** retenus, car IWM a été vu favorable en L3.
- **Données :** Yahoo journalier SPY (Open, Close, Adj Close), `^IRX`.
- **Étape 0 :** vérifier que l'Open Yahoo de SPY est un prix d'ouverture exécutable.
  - Méthode : comparer le rendement nuit Yahoo à celui du CFD SP500 Dukascopy, de 16:00 à 09:30-09:31 ET, sur 2013-06 → 2026-08.
  - **REJET technique** si l'écart moyen dépasse 0,005 %/nuit en faveur de Yahoo.
- **Périodes :**
  - décisionnelle : **2009-01-02 → 2026-09-30**, avec H1 = 2009-2018 (avant Lou, Polk et Skouras 2019) et H2 = 2019-2026 ;
  - rapportée : 1993-2008.
- **Règle :**
  - Chaque jour de bourse, achat MOC de SPY pour 100 % de l'équité (nombre entier d'actions), vente MOO au jour de bourse suivant (week-ends et fériés compris dans la nuit).
  - Cash de jour non rémunéré : il ne reste que quelques heures en cash.
- **Coûts décisionnels :** 1,00 USD par ordre, frais SEC à la vente, frais d'enchère 0,0012 USD/action par côté (non vérifié).
- **PASS (tous requis) :**
  1. alpha annualisé contre SPY ≥ +2 %/an, t de Newey-West ≥ 2 ;
  2. Sharpe net ≥ Sharpe de SPY détenu, sur 2009-2026 ;
  3. alpha > 0 dans H1 et dans H2.
- **REJET :**
  - alpha ≤ 0 ;
  - ou Sharpe net < 0,8 × Sharpe de SPY détenu ;
  - ou étape 0 échouée.

  **INCERTAIN** sinon.
- **Variantes rapportées :**
  - (a) tiered ;
  - (b) QQQ et IWM, rapportés, **jamais décisionnels** ;
  - (c) nuit seulement après un jour SPY ≤ −1 % (Boyarchenko).
- **Ma prédiction :** REJET à 70 %. Même avant le coût de 1 USD, le Sharpe de la nuit (0,39 et 0,74) est sous celui de la détention (0,87 et 0,88). Ce test sert à **fermer** la piste 4 avec un résultat écrit.

## 8. Compteur de calculs exploratoires (ne comptent pas)

| Regard | Contenu | Cellules |
|---|---|---|
| L1 | IBS < 0,2 : panier de 35 FNB, contrôle de 5 FNB, SPY ; portefeuille | 4 × 3 périodes |
| L2 | RSI(2) Connors (< 10, SMA200, SMA5, max 10 j) : panier, SPY, contrôle | 3 × 3 |
| L3 | nuit / jour / nuit après −1 %, SPY, QQQ, IWM ; portefeuilles nuit (1 pb) et détention | 3 FNB × 5 × 3 |
| L4 | secteurs hebdomadaires, top-3 / bottom-3 contre panier égal | 2 × 3 |
| L5 | crypto, chute de −2σ, tenue 1 et 3 jours, BTC/ETH/SOL, **P1 seulement** | 3 × 2 (+ inconditionnels) |
| L6 | portefeuille RSI(2), 35 FNB, 5 cases, 0,05 % | 1 règle × 3 périodes + années |
| L7 | tournant du mois SPY | 1 × 3 |
| L8 | IBS du panier couvert par SPY, contre non couvert | 2 × 3 |

- **Total : 8 regards, aucune variante de seuil essayée** : chaque règle a été prise une seule fois, dans sa forme publiée.
- Aucune correction de bogue ; chaque script a tourné une fois.
- **Contamination pour les préenregistrements :**
  - **Exp A :** les 4 FNB font partie du panier de L1, L2 et L6, et SPY a été regardé seul en L1 et L2. La règle des 4 FNB à 25 %, elle, n'a pas été calculée.
  - **Exp B :** SPY nuit a été regardé en L3, avec un coût de 1 pb, pas de 1 USD.

  Les deux tests restent donc **en échantillon** et ne peuvent que rejeter.
- Aucun calcul sur la stratégie A, sur un HOLDOUT non consommé, ni sur la crypto après 2025-03-27.

## 9. Limites

- L'Open et le Close Yahoo ne sont pas garantis égaux aux prix d'enchère officiels, surtout avant 2005. D'où les étapes 0.
- **Les FNB pays de 1996-2008 ont des prix figés** : le +0,27 %/trade de cette période n'est pas exécutable. Le chiffre 2017-2026 est le seul pertinent.
- Frais d'enchère NYSE Arca, Nasdaq et SEC : ordres de grandeur, non vérifiés. Commission de 1 USD : consigne de l'auteur. 0,35 USD tiered : vérifié en Exp 62.
- Fiscalité : dans un compte imposable, des aller-retours fréquents risquent d'être imposés comme revenu d'entreprise (H-R16 §4). Pas un avis fiscal.
- Pistes non testées faute de données gratuites sans biais : cassures, momentum court et renversement sur actions. **Mon verdict sur ces pistes repose sur la littérature et les coûts, pas sur un calcul.**

## 10. Sources (consultées le 2026-10-10)

Académiques :
- Portnaya, « The Bounce Has No Direction » (arXiv 2606.29591, 2026-06) : https://arxiv.org/abs/2606.29591
- Boyarchenko, Larsen, Whelan, « The Overnight Drift », RFS 36(9), 2023 : https://ideas.repec.org/a/oup/rfinst/v36y2023i9p3502-3547..html ; https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr917.pdf
- Lou, Polk, Skouras, « A tug of war: overnight versus intraday expected returns », JFE 2019 : https://personal.lse.ac.uk/polk/research/TugOfWar.pdf ; https://www.cxoadvisory.com/calendar-effects/momentum-happens-at-night/
- Medhat, Schmeling, « Short-term Momentum », RFS 35(3), 2022 : https://openaccess.city.ac.uk/id/eprint/31278/ ; https://alphaarchitect.com/short-term-momentum/
- Blitz, Hanauer, Honarvar, Huisman, van Vliet, « Beyond Fama-French Factors: Alpha from Short-Term Signals », FAJ 79(4), 2023 : https://rpc.cfainstitute.org/research/financial-analysts-journal/2023/beyond-fama-french-factors-alpha-from-short-term-signals ; https://www.robeco.com/en-latam/insights/2022/05/beyond-fama-french-alpha-from-short-term-signals
- Short-term reversal sur les grandes capitalisations, après coûts (De Groot, Huij, Zhou 2012, résumé Quantpedia) : https://quantpedia.com/strategies/short-term-reversal-in-stocks ; https://efmaefm.org/0EFMAMEETINGS/EFMA%20ANNUAL%20MEETINGS/2011-Braga/papers/0259_update.pdf
- Martineau, « Rest in Peace Post-Earnings Announcement Drift », CFR 11(3-4), 2022 : https://cfr.ivo-welch.info/published/papers/martineau2021rest.pdf
- « The Disappearing Earnings Announcement Premium » (2020) : https://www.iimb.ac.in/ARC2020/Papers/The_Disappearing_Earnings_Announcement_Premium.pdf ; Savor-Wilson / EAP : https://quantpedia.com/strategies/earnings-announcement-premium
- Kurov, Wolfe, Gilbert, « The Disappearing Pre-FOMC Announcement Drift », FRL 2021 : https://www.skidmore.edu/economics/documents/KurovWolfeGilbert-TheDisappearingPre-FOMC-Announce-Drift-200914.pdf
- Zarattini, Pagani, Wilcox, « Does Trend-Following Still Work on Stocks? » (2025) : https://concretumgroup.com/does-trend-following-still-work-on-stocks/ ; https://cxoadvisory.com/momentum-investing/all-time-high-trend-following ; Wilcox & Crittenden 2005 : https://www.cis.upenn.edu/~mkearns/finread/trend.pdf
- IBS sur FNB pays (2023) : https://arxiv.org/abs/2306.12434v1
- Crypto reversal ou momentum selon la liquidité : https://wp.ffu.vse.cz/artkey/wps-202301-0003_impact-of-size-and-volume-on-cryptocurrency-momentum-and-reversal.php ; https://fairfield.elsevierpure.com/en/publications/cryptocurrency-return-reversals/ ; https://www.hse.ru/en/news/research/559533243.html
- Autocorrélation du S&P 500 (Lewellen) : https://faculty.tuck.dartmouth.edu/images/uploads/faculty/jonathan-lewellen/Autocorrelations.pdf

Marché, plateformes :
- Fermeture NightShares : https://www.etf.com/sections/news/2-nightshares-etfs-close-after-struggling-gain-traction ; https://www.wealthmanagement.com/etfs/-night-effect-etfs-to-shut-down-with-overnight-stock-returns-elusive
- Commissions IBKR Canada actions : https://www.interactivebrokers.ca/en/pricing/commissions-home.php ; https://investors.interactivebrokers.com/en/pricing/commissions-stocks.php
- Frais d'enchère NYSE : https://www.nyse.com/markets/nyse/trading-info/fees
- Norgate Platinum : https://norgatedata.com/stockmarketpackages.php

Praticiens (non académique) :
- Backtrex, RSI(2) sur le S&P 500 2016-2026 : https://backtrex.com/en/backtests/connors-rsi-2-sp-500
- Prorealcode, règles RSI(2) de Connors : https://www.prorealcode.com/prorealtime-trading-strategies/rsi-2-strategy-larry-connors/

## 11. Questions ouvertes pour l'orchestrateur

1. Commission réelle de l'auteur chez IBKR Canada : **fixe** (1 USD minimum) ou **tiered** (0,35 USD) ? Le choix change Exp B, mais pas Exp A.
2. L'agent Plateformes doit vérifier :
   - les frais d'enchère MOC et MOO (NYSE Arca pour SPY, IWM et DIA ; Nasdaq pour QQQ) ;
   - l'heure limite de dépôt des MOC (15:50 ET) chez IBKR ;
   - la possibilité de vendre SGOV et d'acheter un FNB au même close dans un compte sur marge.
3. Faut-il lancer Exp A et Exp B, ou seulement A ? B est surtout un test de fermeture. Ma recommandation : **A d'abord** ; B seulement si l'auteur tient à une réponse écrite sur la nuit.
4. Payer des données sans survivant (Norgate, 630 USD/an) ne se justifie pas à 15 k, puisque c'est 6 % du capital par an. À reconsidérer seulement au-delà d'environ 50-100 k.
