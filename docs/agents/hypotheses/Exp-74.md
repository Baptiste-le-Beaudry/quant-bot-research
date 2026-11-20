# Exp 74 — Indice à levier ×2 avec filtre de tendance 200 jours (« Leverage for the Long Run ») — PRÉENREGISTREMENT

- **ID :** Exp 74 / `L-LEV-TREND-001` (T-068). Demandé par l'auteur le 2026-10-11 (« il faut que les backtests fassent environ 15 % ; tente des trucs »). Préenregistré le 2026-10-11 par l'orchestrateur, figé par ce commit, **avant tout calcul**. Juge : Validateur.
- **Pourquoi cette piste :**
  - Atteindre 15 %/an demande plus d'exposition au marché, pas seulement un meilleur signal.
  - H-R16 a écarté les FNB à levier détenus en permanence, à cause du risque de ruine (≈ −80 % en 2022), mais **pas** la version filtrée par la tendance. C'est la règle publiée par Gayed & Bilello (2016), « Leverage for the Long Run », SSRN 2741701.
  - Elle n'a jamais été testée dans ce projet.
- **Compteur global :** 74e expérience du projet. Ce nombre sert au Deflated Sharpe.

## Règle (fixée, publiée, aucun réglage)

1. **Signal :** à la clôture du jour t, on compare l'indice de prix S&P 500 (^GSPC) à sa moyenne mobile simple sur 200 séances.
2. **Si l'indice est au-dessus :** on détient un indice ×2 synthétique à rééquilibrage quotidien. **Sinon :** on détient des bons du Trésor à 3 mois.
3. **Exécution :** le changement de position prend effet à la clôture de **t+1**, et non à t comme dans le papier, pour ne pas supposer qu'on trade au prix qui génère le signal.
4. **Rendement quotidien du ×2 :** 2·r_TR − 1·rf − 0,95 %/an de frais.
   - r_TR est le rendement total de l'indice. On utilise le dividende, si les données sont disponibles (^SP500TR, ou dividende approximé à 2 %/an avant sa date de début) ; sinon on note le biais.
   - rf est le taux T-bill du jour (^IRX / 252).
5. **Coût par bascule :** 0,10 % du capital (écart et glissement).
6. **Rendements en USD.** La conversion en CAD est rapportée sans effet.

## Données

- Quotidiennes, Yahoo (ou FRED / Stooq si Yahoo échoue), de 1990-01-01 à la dernière clôture disponible.
- Le résultat doit citer la source et la date de téléchargement.
- Contrôle obligatoire : le ×2 synthétique est comparé à SSO (FNB ProShares ×2 réel) sur 2007-2026. L'écart de CAGR doit être ≤ 1,5 pt/an ; sinon, signaler et appliquer une correction.

## Périodes

- **Pré** : 1990-01 → 2016-02, la période de l'article. C'est un résultat en échantillon pour les auteurs.
- **Post (décisionnelle)** : 2016-03 → fin des données, après la publication.

## Critères (fixés)

**PASS** si les quatre conditions sont réunies :
1. CAGR net Post ≥ 15 % ;
2. MaxDD Post ≥ −45 % ;
3. CAGR net Post > CAGR du S&P 500 rendement total ×1 détenu sur la même période ;
4. **Même signe ailleurs :** la même règle (×2, sa propre MM200) bat la détention ×1 de son propre indice sur toute la période disponible, sur **au moins 2 des 3** indices suivants : Nasdaq-100 (^NDX), Russell 2000 (^RUT), DAX (^GDAXI, en EUR, avec rf américain comme approximation, à signaler).

**REJET** si l'une des conditions suivantes est remplie :
- CAGR net Post < 10 % ;
- CAGR net Post ≤ S&P 500 ×1 ;
- MaxDD Post < −60 %.

**INCERTAIN** sinon.

**Rapporté sans effet :**
- ×3 (UPRO synthétique, contrôle contre UPRO 2009-2026) ;
- détention ×2 sans filtre ;
- pire année et pire mois ;
- nombre de bascules par an ;
- temps passé investi ;
- résultat par décennie ;
- Sharpe et Deflated Sharpe avec N = 74 essais ;
- résultat en CAD ;
- exécution à la clôture de t (version du papier).

## Si PASS

- Ce n'est **pas** un feu vert pour l'argent réel. C'est surtout du risque de marché amplifié, pas un avantage caché.
- Suite : fiche pratique CELI (FNB disponibles : SSO, UPRO, QLD, ou équivalents canadiens ; retenue fiscale de 15 % ; fréquence des bascules par rapport au risque « entreprise » au sens d'Ahamed).
- Paper sur 3 mois au minimum, puis décision de l'auteur.

## Variantes comptées

1 décisionnelle (S&P ×2, MM200, exécution à t+1). Tout le reste est rapporté.
