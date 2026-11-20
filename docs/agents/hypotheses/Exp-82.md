# Exp 82 — Rabais DRIP émis du trésor : baisse dans la fenêtre de prix, reprise après — PRÉENREGISTREMENT

- **ID :** Exp 82 (T-077). Préenregistré le 2026-10-12 par l'orchestrateur et figé par ce commit, **avant la construction de la table d'événements et avant tout téléchargement de cours**. Juge : Validateur.
- **Source :** brouillon H-R21 §5.2 (branche agents/t075-hr21, ac90f7e), repris tel quel ci-dessous.
- **Arbitrages de l'orchestrateur :**
  - Le Deflated Sharpe est rapporté avec N = 133 (prudent) et avec N = 96.
  - L'étape 0, la table d'événements tirée des communiqués, est commitée **avant** de charger le moindre cours.


**Hypothèse.** Quand un émetteur canadien émet les actions de son DRIP depuis le trésor avec un rabais (≥ 1 %) sur un prix moyen calculé sur les jours précédant le versement, l'action fait moins bien que ses pairs pendant cette fenêtre, puis mieux dans les 5 jours suivants. Rien de tel n'arrive pour la même action quand le rabais est éteint.

**Étape 0 (à faire et commiter AVANT de charger un seul prix).** Table d'événements figée, construite **uniquement** à partir des communiqués de dividende et des circulaires de DRIP :
- Univers : 6 grandes banques (RY, TD, BNS, BMO, CM, NA) + émetteurs de l'indice S&P/TSX 60 qui, à une date quelconque depuis 2000, ont émis des actions de DRIP depuis le trésor avec rabais. Liste établie à partir des communiqués, sans regarder les cours.
- Pour chaque date de versement P de chaque émetteur :
  - indicateur rabais (oui/non, taux) ;
  - source (trésor ou marché) ;
  - définition de la fenêtre de prix moyen selon la circulaire de l'émetteur (TD : moyenne des prix moyens pondérés des **5 jours de bourse avant** la date de placement = date de versement) ;
  - URL de la source.
- Si moins de **40 événements avec rabais** : arrêt, verdict INCERTAIN (puissance insuffisante), sans calcul de rendement.

**Données.** Yahoo `.TO` quotidien (clôture ajustée + volume), 2000 → ; ^GSPTSE ; rapports trimestriels (actions émises par le DRIP). Autre pays : 4 banques australiennes (`.AX`) et leurs annonces de prix DRP (ASX), en suivant la même étape 0.

**Mesures (figées).**
- P = date de versement (jour de bourse suivant si férié).
- Fenêtre A (prix moyen) : rendements des jours P−5 à P−1, ou la fenêtre de la circulaire si elle diffère.
- Fenêtre B (reprise) : rendements des jours P à P+4.
- Rendement anormal :
  - banques : rendement de l'action moins la moyenne équipondérée des grandes banques **sans rabais actif** ce jour-là (^GSPTSE s'il n'y en a aucune) ;
  - autres émetteurs : rendement de l'action moins ^GSPTSE.
- CAR_A, CAR_B = sommes des rendements anormaux.
- Différence-de-différences : DiD_A = moyenne CAR_A(rabais) − moyenne CAR_A(sans rabais, mêmes émetteurs) ; idem DiD_B. Erreurs-types regroupées par date de versement.

**Règle de trading (pour le chiffre de rendement).**
- Détenir le panier des banques équipondéré (ZEB ou panier reconstruit).
- Pour chaque événement avec rabais : basculer la part de ce panier vers l'action concernée.
- Signal connu d'avance : décision à la clôture de P−2, achat à la clôture de P−1 (ordre au marché à la clôture), revente à la clôture de P+4.
- Coût : **0,20 % par événement** (4 ordres ≈ 0,05 % chacun : écart + commission IBKR/Questrade sur grandes capitalisations TSX).
- Nombre d'ordres attendu : 8-40/an selon le nombre d'émetteurs avec rabais actif.

**Référence.** Panier des banques équipondéré × L constant, à la **même volatilité** que la règle, avec le même coût de financement si L > 1.

**Prédiction supplémentaire (obligatoire).**
- Volume anormal dans la fenêtre A : log(volume / médiane des 20 jours avant P−5).
- Exigé : DiD du volume anormal (rabais − sans rabais) **> 0 avec t ≥ 2**.
- Si les ventes de couverture existent, le volume doit monter **seulement** quand le rabais est actif.

**Critères (fixés).** PASS si tout est vrai :
1. DiD_A ≤ −0,20 point avec t ≤ −2,0.
2. DiD_B ≥ +0,15 point avec t ≥ 1,5 (reprise), et règle nette > 0 par événement après 0,20 % de coût.
3. Prédiction supplémentaire sur le volume remplie.
4. Robustesse fixée d'avance (DiD_A < 0 dans chaque cas) :
   - (a) banques seules ;
   - (b) émetteurs non bancaires seuls ;
   - (c) épisode 2022-2024 seul (interrupteur le plus net) ;
   - (d) rendement anormal mesuré contre ^GSPTSE pour tous ;
   - (e) Australie : banques avec DRP à rabais sans preneur ferme, même signe pour DiD_A. Ce point est rapporté si moins de 20 événements.
5. ΔSharpe de la règle contre la référence > 0 sur la période entière.

REJET si DiD_A ≥ 0, **ou** si le volume anormal DiD ≤ 0. INCERTAIN sinon (dont : moins de 40 événements).

**Rapporté sans effet.**
- Pente de CAR_A sur l'intensité (actions émises / volume quotidien moyen) ;
- résultats par émetteur ;
- part des 5 meilleurs événements ;
- rabais 1 % contre 2 % contre ≥ 3 % ;
- événements « achat sur le marché » (prédiction inverse : pression d'achat le jour P, Berkman-Koch) ;
- version « éviter la fenêtre » pour un détenteur de banques (vendre en P−6, racheter en P−1) ;
- DSR avec N = 95 et N = 132.

**Variantes comptées.** 1 décisionnelle. (a)-(e) sont des contrôles obligatoires.

**Probabilité a priori de PASS : ≈ 10 %.** Le petit gain d'arbitrage et le résultat australien nul pour les DRP sans preneur ferme pèsent contre.

**Limites connues avant calcul.**
- Pas de VWAP gratuit (on utilise la clôture) ;
- les cours ajustés de Yahoo peuvent comporter des erreurs autour des dividendes (vérifier sur 10 événements contre les cours bruts) ;
- biais de survie limité (grandes banques), mais réel pour les autres émetteurs ;
- risque Ahamed si plus de ≈ 30 ordres/an dans le CELI : faire la stratégie dans le compte imposable.

**Si PASS.** Revue du Validateur → suivi papier des événements de 2027 (dates connues d'avance) → décision de l'auteur.

---

