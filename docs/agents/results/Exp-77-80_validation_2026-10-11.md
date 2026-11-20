# Exp 77-80 — validation unique 2010 → fin des 4 candidats de l'atelier D-09 (T-074)

- **Date :** 2026-10-11. **Auteur :** agent Développeur (T-074). Branche `agents/t074-validation`, partie de 9f6baca (préenregistrements figés).
- **Catégorie des chiffres :** hors échantillon, **une seule exécution** (aucune relance, aucun paramètre modifié). Ce ne sont pas des résultats forward.
- **Convention :** décision au close t, exécution au close t+1, premier rendement en t+2 (mensuel : décision en fin de mois). Coût 0,10 % × |Δpoids| + 0,10 % × dérive rééquilibrée en fin de mois. Levier au-delà de ×1 financé au T-bill + 1,8 %/an. Code `engine.py` inchangé.
- **Fichiers :** `Exp-77-80_validation_2026-10-11_criteria.json` (tous les chiffres), `Exp-77-80_validation_2026-10-11_daily.csv` (rendements quotidiens nets des 4 règles).

## Verdict en une phrase

**Les 4 candidats sont REJETÉS mécaniquement.** Après 2009, aucun ne bat le S&P 500 TR à levier constant de même volatilité : ΔSharpe entre −0,03 et −0,28. Les contrôles vont dans le même sens. L'atelier D-09 ne produit donc aucune stratégie validée.

## Tableau récapitulatif (2010-01-04 → fin)

| | Exp 77 (C09) | Exp 78 (C19) | Exp 79 (C02) | Exp 80 (C13) |
|---|---|---|---|---|
| Règle | S&P ×1,532, repli B10 si tendance ET crédit mauvais | top 3/12 industries ×1,418 + repli C09 | parité de risque S&P/B10 ×2,877 | top 3/12 industries ×1,098 |
| Période | → 2026-10-08 | → 2026-08-31 | → 2026-10-08 | → 2026-08-31 |
| CAGR net (≥ 15 %) | 11,3 % ✗ | 10,9 % ✗ | 9,2 % ✗ | **16,2 % ✓** |
| MaxDD quotidien (≥ −50 %) | −44,1 % ✓ | −39,5 % ✓ | −52,6 % ✗ | −41,1 % ✓ |
| Sharpe règle | 0,567 | 0,512 | 0,495 | 0,732 |
| Référence S&P TR ×L (L ; Sharpe) | 1,147 ; 0,770 | 1,298 ; 0,760 | 1,064 ; 0,777 | 1,271 ; 0,762 |
| **ΔSharpe (≥ +0,10)** | **−0,203** ✗ | **−0,248** ✗ | **−0,282** ✗ | **−0,030** ✗ |
| Contrôles ΔSharpe > 0 | 0 sur 3 ✗ | 0 sur 2 ✗ | 0 sur 3 ✗ | 1 sur 2 ✗ |
| DSR (N = 117 ; ≥ 0,95) | 0,870 ✗ | 0,817 ✗ | 0,800 ✗ | **0,963 ✓** |
| **Verdict mécanique** | **REJET** | **REJET** | **REJET** | **REJET** |
| Motif du REJET | ΔSharpe ≤ 0 et 3/3 contrôles ≤ 0 | ΔSharpe ≤ 0 et 2/2 contrôles ≤ 0 | ΔSharpe ≤ 0 et 3/3 contrôles ≤ 0 | ΔSharpe ≤ 0 |
| Ordres/an | 20,8 | 57,3 | 45,9 | 36,9 |
| ΔSharpe en découverte 1990-2009 | +0,259 | +0,420 | +0,192 | +0,176 |

Pour comparaison, sur la même période : S&P 500 TR ×1 seul = CAGR 14,4 %, Sharpe 0,784, MaxDD −33,8 %.

Le DSR mesure seulement si le Sharpe de la règle dépasse ce que donnerait le meilleur de 117 essais au hasard. Il ne compare pas la règle au S&P. Le DSR de 0,963 de l'Exp 80 reflète donc surtout la prime actions de 2010-2026 : le S&P ×1 a lui-même un Sharpe plus élevé (0,784).

**Contrôle de reproduction (données déjà vues).** Avec les données retéléchargées, les 4 règles redonnent sur 1990-2009 exactement les chiffres de `LOG.csv` : Sharpe 0,567 / 0,727 / 0,500 / 0,484 et ΔSharpe +0,259 / +0,420 / +0,192 / +0,176, identiques à 3 décimales. Les nouvelles séries sont donc cohérentes avec celles de la découverte, et le code a bien tourné tel quel.

## Détail par Exp

### Exp 77 — C09 (S&P ×1,532, repli obligataire si tendance ET crédit mauvais) : REJET

- **Résultat :** CAGR 11,3 %, MaxDD −44,1 %, Sharpe 0,567, contre 0,770 pour la référence (L = 1,147, CAGR 15,8 %). **ΔSharpe = −0,203.** DSR = 0,870.
- **Contrôles (k figés) :**

  | Contrôle | k | ΔSharpe | CAGR | Période |
  |---|---|---|---|---|
  | Nasdaq-100 | 0,896 | −0,166 | 11,9 % | → 2026-10-08 |
  | Russell 2000 | 1,390 | −0,281 | 3,9 % | → 2026-10-08 |
  | Developed ex US | 1,650 | −0,167 | 5,4 % | → 2026-08-31 |

- **Rapporté sans effet :**
  - **Mélange fixe aux mêmes poids moyens** (S&P 1,297 + B10 0,235) : Sharpe 0,760, CAGR 17,0 %. Règle − mélange = **−0,192**. Le signal de bascule a coûté du rendement.
  - **Sous-périodes :**

    | Période | ΔSharpe | CAGR |
    |---|---|---|
    | 2010-2019 | −0,301 | 9,9 % |
    | 2020 → fin | −0,112 | 13,2 % |

  - **2022 : −42,2 %**, contre −21,3 % pour la référence et −18,1 % pour le S&P ×1. Le repli sur B10 a perdu en même temps que les actions, ce que le brouillon avait anticipé.
  - **Années :** 2011 −18,5 % et 2015 −22,2 % sont des faux signaux, contre environ +1 % pour la référence ces années-là. Le surplus total est négatif (−0,67 en log) : la « part des 3 meilleures années » n'a donc pas de sens. Les 3 meilleures années relatives sont 2013, 2018 et 2021.
  - **CAD (non couvert, DEXCAUS) :** règle CAGR 13,2 %, MaxDD −40,6 % ; référence CAGR 17,9 %, MaxDD −32,0 %.
  - **Instruments réels :**
    - SPY/IEF ×1 avec financement du moteur : CAGR 11,6 %, ΔSharpe −0,182 ;
    - mélange SPY+SSO / IEF+UST, sans emprunt (2010-02-10 → fin) : CAGR 13,0 %, ΔSharpe −0,132, MaxDD −41,8 %.
  - **Ordres :** 20,8 par an ; actions détenues 85 % des jours.

### Exp 78 — C19 (momentum sectoriel top 3/12 + repli C09) : REJET

- **Résultat :** CAGR 10,9 %, MaxDD −39,5 %, Sharpe 0,512, contre 0,760 pour la référence (L = 1,298, CAGR 17,2 %). **ΔSharpe = −0,248.** DSR = 0,817.
- **Contrôles :**

  | Contrôle | k | ΔSharpe | Ordres/an |
  |---|---|---|---|
  | 30 industries top 8 | 1,370 | −0,206 | 116 |
  | 49 industries top 12 | 1,377 | −0,272 | 157 |

- **Rapporté sans effet :**
  - **Mélange fixe** (S&P 1,199 + B10 0,219) : Sharpe 0,770, CAGR 16,1 %. Règle − mélange = **−0,258**.
  - **Sous-périodes :**

    | Période | ΔSharpe | CAGR |
    |---|---|---|
    | 2010-2019 | −0,274 | 10,7 % |
    | 2020 → 2026-08 | −0,228 | 11,2 % |

  - **2022 :** −27,4 %, contre −24,6 % pour la référence.
  - **Années :** 2011 −23,6 % et 2015 −16,6 % ; 2025 −3,7 % et 2026 (8 mois) −1,4 %, contre environ +16 à +21 % pour la référence. Le surplus total est négatif (−0,92 en log). Les 3 meilleures années relatives sont 2020, 2013 et 2018.
  - **CAD :** CAGR 12,7 %, contre 19,1 % pour la référence.
  - **Instruments réels :** FNB sectoriels SPDR ×1 + IEF, financement du moteur. CAGR 8,8 %, ΔSharpe −0,316. La correspondance industries Ken French → FNB est approximative (voir Limites).
  - **Ordres :** 57,3 par an, au-dessus de la limite d'environ 50.
  - **Fuite par mémoire (D-09 §6) :** le biais technologique d'après 2009, jugé « favorable » dans le brouillon, n'a pas suffi.

### Exp 79 — C02 (parité de risque S&P/B10 ×2,877) : REJET

- **Résultat :** CAGR 9,2 %, **MaxDD −52,6 %** (critère 2 violé), Sharpe 0,495, contre 0,777 pour la référence (L = 1,064, CAGR 15,0 %). **ΔSharpe = −0,282.** DSR = 0,800.
- **Contrôles (mensuels, monnaie locale) :**

  | Contrôle | k | ΔSharpe | CAGR | Période |
  |---|---|---|---|---|
  | Allemagne | 3,434 | −0,392 | 2,1 % | → 2026-08 |
  | Royaume-Uni | 3,070 | −0,224 | 5,1 % | → 2026-01, série OECD arrêtée plus tôt |
  | Japon | 3,077 | −0,682 | 0,2 % | → 2026-08 |

- **Rapporté sans effet :**
  - **Mélange fixe** (S&P 0,950 + B10 1,927) : Sharpe 0,573. Règle − mélange = −0,078.
  - **Sous-périodes :**

    | Période | ΔSharpe | CAGR | Sharpe | MaxDD |
    |---|---|---|---|---|
    | 2010-2019 | **+0,195** | 16,4 % | 1,09 | −17,5 % |
    | 2020 → fin | **−0,701** | −0,5 % | −0,03 | — |

    Tout l'échec vient de la hausse des taux depuis 2020.
  - **2022 : −46,7 %**, contre −19,5 % pour la référence. C'était prévu dans le brouillon (fuite par mémoire défavorable).
  - **CAD :** CAGR 11,2 %, MaxDD −48,6 % ; référence CAGR 17,1 %.
  - **Instruments réels :**
    - SPY/IEF ×1 avec financement du moteur : CAGR 10,1 %, ΔSharpe −0,225, MaxDD −50,7 % ;
    - SSO + UST à k/2, avec emprunt de 0,44 au T-bill + 1,8 % (2010-02-10 → fin) : CAGR 11,7 %, ΔSharpe −0,156, MaxDD −49,9 %.
  - **Ordres :** 45,9 par an.

### Exp 80 — C13 (momentum sectoriel top 3/12 seul, ×1,098) : REJET

- **Résultat :** CAGR **16,2 %** (critère 1 ✓), MaxDD −41,1 % ✓, Sharpe 0,732, contre 0,762 pour la référence (L = 1,271, CAGR 17,0 %). **ΔSharpe = −0,030** ✗. DSR = 0,963 ✓.
- **Contrôles :**

  | Contrôle | ΔSharpe |
  |---|---|
  | 30 industries | +0,029 |
  | 49 industries | −0,024 |

  Un seul sur deux est positif : le critère 4 échoue. Ce n'est pas une majorité ≤ 0, mais le ΔSharpe ≤ 0 suffit pour le REJET.
- **Lecture :** le CAGR passe parce que le levier de 1,1 sur des actions a profité du marché haussier de 2010-2026. La sélection sectorielle n'ajoute rien par unité de risque.
- **Rapporté sans effet :**
  - **Mélange fixe des 12 industries aux poids moyens tenus :** Sharpe 0,756. Règle − mélange = −0,024.
  - **Sous-périodes :**

    | Période | ΔSharpe | CAGR |
    |---|---|---|
    | 2010-2019 | −0,033 | 15,0 % |
    | 2020 → 2026-08 | −0,008 | 18,0 % |

  - **2022 : +0,7 %**, contre −24,0 % pour la référence (rotation vers l'énergie). En revanche, la règle est en retard en 2019, 2021, 2023 et 2024. Le surplus total est légèrement négatif (−0,11 en log) : la « part des 3 meilleures années » n'a pas de sens. Les 3 meilleures années relatives sont 2022, 2020 et 2010.
  - **CAD :** CAGR 18,1 %, MaxDD −35,3 % ; référence CAGR 18,9 %.
  - **Instruments réels :** FNB sectoriels SPDR ×1, financement du moteur. CAGR 13,6 %, ΔSharpe −0,093.
  - **Ordres :** 36,9 par an.

## Méthode (résumé)

- **Données retéléchargées sans borne de fin** dans `data/atelier_validation/`. `meta.json` contient l'URL, la date et le sha256 de chaque fichier.
  - Yahoo : ^SP500TR, ^GSPC, ^IRX, ^NDX, ^RUT, ^GDAXI, ^FTSE, ^N225.
  - FRED : DGS10, BAA10Y, 3 taux longs et 3 taux courts OECD, plus DEXCAUS pour la conversion en CAD.
  - Ken French : 12, 30 et 49 industries daily, F-F daily, Developed ex US daily.
  - FNB réels (rapportés seulement) : SPY, SSO, IEF, UST, XLP, XLY, XLI, XLE, XLB, XLK, IYZ, XLU, XLV, XLF.
- **Dernières dates disponibles :** S&P/GSPC/IRX au 2026-10-09, DGS10/BAA10Y au 2026-10-08, Ken French au 2026-08-31. Chaque Exp s'arrête à la dernière séance où **toutes** ses sources existent : 2026-10-08 pour les Exp 77 et 79, 2026-08-31 pour les Exp 78 et 80. Cela évite une fin de série remplie de zéros.
- **Chargeur de validation :** `scripts/agents/atelier/loader_validation.py`. C'est une **instance séparée** du module `loader.py`, dont seule la borne de fin est levée : les analyseurs sont identiques. `loader.py` garde sa coupe au 2009-12-31, ce que vérifie un test.
- **Ordre des commits :** chargeur, exécuteur et tests commités en d9ecd0e **avant** tout téléchargement ou chargement de données postérieures à 2009.
- **Exécuteur :** `scripts/agents/atelier/validate.py`.
  - Il appelle `discovery.rule` (C02, C09, C13, C19 et les variantes ind30/ind49 des contrôles), `controls.c09_control`, `controls.monthly_market`/`monthly_control` et `engine.simulate`/`evaluate`, **sans les modifier** (commit e0c3917, aucun diff).
  - Les k sont les valeurs figées ; `scale_to_vol` n'est jamais appelé.
  - Les fonctions de contrôle de la découverte re-résolvent k et écrivent `LOG.csv` à la fin. Elles sont donc interceptées juste avant ce point : les poids qu'elles construisent sont capturés, puis simulés avec le k figé.
  - La simulation couvre tout l'historique : avant 2010, c'est l'échauffement, et les positions de fin 2009 sont reportées. Les métriques portent seulement sur 2010-01-04 → fin. Les contrôles mensuels vont de 2010-01 au dernier mois complet.
- **DSR :** Bailey et López de Prado, calculé sur les rendements excédentaires quotidiens. N = 117, variance entre essais = 0,1116²/252, soit un seuil SR0 = 0,289 en annuel.
- **Une seule exécution** de `validate.py` sur les données réelles, terminée sans erreur. Aucune relance.

## Limites et anomalies

1. **Assemblage des données :** `discovery.data()` n'est pas appelé directement, car il charge aussi Shiller, T10Y3M et les facteurs Europe/Japon/Asie, qui ne figurent pas dans la liste de la partie commune. `validate.fill_cache()` reprend **mot pour mot** ses lignes pour les clés utilisées par ces 4 règles et leurs contrôles. Ce n'est pas de la logique de règle, et le contrôle de reproduction 1990-2009 (identique à 3 décimales) confirme l'équivalence.
2. **Fins de période différentes :** les Exp 78 et 80 s'arrêtent au 2026-08-31 (Ken French), les Exp 77 et 79 au 2026-10-08. Le contrôle Royaume-Uni de l'Exp 79 s'arrête en 2026-01, car la série OECD GB est publiée avec retard.
3. **« Part des 3 meilleures années » :** elle n'a pas de sens ici, car le surplus total est négatif pour les 4 règles (valeurs négatives dans le JSON). Les années sont rapportées telles quelles. L'année 2026 est partielle.
4. **Mélange fixe :** ses poids sont les moyennes des poids tenus sur la validation, donc connus après coup. C'est une comparaison descriptive, sans effet sur le verdict. Pour C13, qui n'a pas de jambe obligataire, le mélange porte sur les 12 industries à leurs poids moyens.
5. **Instruments réels :**
   - prix ajustés Yahoo, approximation du rendement total ;
   - correspondance Ken French → SPDR approximative : Durbl et Shops → XLY, Telcm → IYZ, Other → SPY ;
   - pas de FNB sectoriels ×2 : le levier sectoriel est financé par le moteur ;
   - UST n'existe que depuis 2010-01-19 (variante ×2 à partir du 2010-02-10).
6. **CAD :** conversion non couverte au taux DEXCAUS. Pas de frais de change ni de retenue fiscale.
7. **Fuite par mémoire (D-09 §6) :** les échecs de C02 (2022) et de C09 (repli obligataire en 2022) étaient anticipés dans les brouillons. Le biais technologique supposé favorable à C13/C19 ne s'est pas traduit en ΔSharpe positif.
8. **Données non fiables** (Yahoo, FRED, Ken French téléchargés le 2026-10-11) : lues avec pandas seulement, sans aucune exécution.

## Anti-doublon

Sources consultées : D-09, `docs/agents/research/atelier/` (RAPPORT_T-073, candidats.md, LOG.csv : 41 évaluations de découverte) et les Exp 74-76 (levier, ciblage de volatilité, empilement tendance ; même référence à volatilité égale). Cette validation est la seule utilisation prévue de la période 2010 → fin pour ces 4 candidats. Elle est désormais **consommée**.

## Fichiers écrits

- `scripts/agents/atelier/loader_validation.py`, `download_validation.py`, `validate.py`
- `tests/agents/test_atelier_loader_validation.py`, `tests/agents/test_atelier_validate.py`
- `docs/agents/results/Exp-77-80_validation_2026-10-11.md`, `_criteria.json`, `_daily.csv`
- Données : `data/atelier_validation/` (nouveau répertoire, non versionné)
