# Exp 72 — Fade de l'échec d'ORB 30 min sur MNQ (R1, H-R19) — PRÉENREGISTREMENT

- Repris **sans modification** de `research/H-R19_funded_meanrev.md` §6 (commit 88dd134). Préenregistré le 2026-10-11 par l'orchestrateur, figé par ce commit avant tout calcul sur la fenêtre de décision. Juge : Validateur. Test de fermeture : si REJET, la famille « retour à la moyenne funded » est close.


**Pourquoi ce test, et pourquoi il est faible.**
- C'est le seul candidat de H-R19 avec un net positif et un profil adapté au funded : σ trois fois plus petit, 5 meilleurs jours = 33 % du net, cohérence peu gênante.
- Il a échoué sur MES et MYM dans la découverte, et ses voisins sont plats. **Probabilité a priori de PASS : ≈ 10 %.**
- Son intérêt principal est de **fermer proprement** la famille avec un regard bon marché : le moteur existe, le calcul prend quelques minutes.

**Fuites déclarées sur la fenêtre de décision.**
- (a) Les Exp 64 (P1 jusqu'au 2024-03-04) et 65 (H) ont vu NDX 2020-2026 pour la règle de **momentum** ; on sait que le momentum y a fonctionné, ce qui joue **contre** un fade.
- (b) BI3 a vu l'**ORB continuation** NDX du 2021-09-23 au 2024-03-05 (dérive négative, donc favorable au fade). **Cette période est exclue de la décision.**
- (c) Le Russell brut « inverse » de l'Exp 71 est connu : **M2K n'est pas utilisé pour décider.**

**Spécification.**
- **Hypothèse.** La règle F2 OR30 gelée (`H-R19_scripts/families.py`, fonction `f2_orb_fade(g, 30)`, commit a18cd02, **sans aucun changement**) donne un Sharpe net ≥ 0,6 sur MNQ dans la fenêtre de décision.
- **Instrument.** NASDAQ100 (Dukascopy) → **MNQ**, 1 contrat par signal pour les statistiques. **Pas le NNQ** (coût 6,4 fois plus élevé, §1.1).
- **Fenêtre de décision (jamais vue pour cette règle).** **D1 = 2020-01-02 → 2021-09-22 et D2 = 2024-03-05 → 2026-08-18** (fin du fichier), ≈ 1 050 séances.
  - La période BI3 (2021-09-23 → 2024-03-04) est calculée et rapportée **sans effet**.
  - Les 14 jours d'historique de σ peuvent venir de décembre 2019.
- **Règle exacte** (celle du code gelé) :
  - éligibilité de l'Exp 64 §3.6 plus σ et VWAP définis (masque `ok`) ;
  - ORH et ORL = plus haut et plus bas des barres 09:30-09:59 ;
  - balayage des clôtures 1 min de 10:00 à 13:29 : une clôture > ORH arme la cassure haussière, et l'extrême haut est suivi ensuite ;
  - si une clôture repasse < ORH, vente à l'ouverture de la barre suivante ;
  - cible : première clôture ≤ (ORH + ORL)/2. Stop : première clôture ≥ l'extrême au moment de l'entrée. Sortie à l'ouverture de la barre suivante ; sinon à l'ouverture de 15:59 ;
  - règle symétrique à la baisse ; au plus une entrée par côté et par jour ; pas de chevauchement de positions.
- **Coûts.** 2,22 USD aller-retour au notionnel actuel (60 000 USD par MNQ), soit 0,0037 % du rendement. Stress : +1 tick par côté (3,22 USD).
- **Mesures :**
  - Sharpe net quotidien (D1 ∪ D2, puis D1 et D2 séparément) ;
  - t par trade, taux de gain, gain et perte moyens ;
  - part du net venant des 5 meilleurs jours, MaxDD, pire jour, résultats par année ;
  - espérance funded avec `H-R19_scripts/funded_orbfade.library` appliquée à D1 ∪ D2 et `H-R17_scripts/funded_sim.run` inchangé, 3 000 parcours, graine 11 :
    - case **principale** : Lucid Flex 50K, `fixed:3`, 5 tentatives ;
    - case **secondaire** : Topstep 50K, `fixed:5`, 5 tentatives ;
    - scénarios « mesuré » et « demi-edge ».
- **PASS (toutes les conditions) :**
  - Sharpe net D1 ∪ D2 ≥ 0,6 ;
  - Sharpe net > 0 sur D1 **et** sur D2 ;
  - Sharpe stress ≥ 0,4 ;
  - 5 meilleurs jours ≤ 50 % du net ;
  - case principale, scénario mesuré : espérance > 2 erreurs types **et** > 0 pour 100 USD ;
  - case principale, demi-edge : espérance ≥ 0 (marge de sécurité) ;
  - au moins 600 trades.
- **REJET :** Sharpe net D1 ∪ D2 ≤ 0,2, **ou** espérance de la case principale (mesurée) ≤ 0. → **Fermer la piste « retour à la moyenne funded ».**
- **INCERTAIN :** tout le reste → aucun achat ; tout au plus un forward papier.
- **Puissance.** Sur ≈ 4,2 ans, l'erreur type du Sharpe est ≈ 0,49. Si le vrai Sharpe vaut 0,68, P(Sharpe observé ≥ 0,6) ≈ 0,55. Le test est donc peu puissant, mais un REJET reste très informatif.
- **Variantes : 1 décisionnelle.** Rapportées **sans effet** :
  - la période BI3 ;
  - MES et MYM sur 2020-2026 (dans la découverte, la règle y échouait) ;
  - M2K sur toute sa série (fuite c).
- **Compteur de la famille :** 41 regards exploratoires (H-R19) + R1.
- **Étape 0 (bloquante) :**
  - `grep` pour vérifier qu'aucun script n'a calculé F2 sur NDX après 2019 ;
  - tests unitaires du chargeur de fenêtre (fixtures dans `tmp_path`, jamais sur `data/`) ;
  - script et tests commités avant tout calcul.
- **Si PASS :** 3 mois de forward papier, sur l'infrastructure MNQ de l'Exp 67. Ensuite seulement, proposer à l'auteur **une** tentative Lucid Flex 50K ou FundedNext Rapid 50K (bots permis, Canada admis), achetée en promotion, à 3 micros.
- **Si REJET :** fermer la piste ; aucun achat.

**Pas de second préenregistrement.**
- F6-VWAP est le meilleur candidat « mécanisme », mais son net (+0,1 à +0,24 pb) est structurellement sous le point mort funded, même au MNQ.
- Pour qu'il compte, il faudrait un coût d'exécution ≈ 0 (ordres limite remplis sans sélection adverse), ce qu'on ne sait pas mesurer avec des barres CFD de 1 minute.

