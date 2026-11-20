# Exp 79 — Atelier D-09, candidat D (C02) : parité de risque actions/obligations à levier — PRÉENREGISTREMENT (validation 2010 → fin)

- **ID :** Exp 79 (T-074). Préenregistré le 2026-10-11 par l'orchestrateur et figé par ce commit, **avant tout chargement de données postérieures au 2009-12-31**. Juge : Validateur.
- **Règle, paramètres, données, exécution, coûts, référence, contrôles :** exactement ceux de `docs/agents/research/atelier/candidats.md`, partie commune et section « Candidat D — C02 », au commit 4e85472. Le code des règles et du moteur est celui de `scripts/agents/atelier/` au commit e0c3917, **réutilisé tel quel**. Seul un chargeur de validation distinct est ajouté ; `loader.py` garde sa coupe au 2009-12-31.
- **Famille de validation D-09 :** 4 candidats validés en même temps, les Exp 77, 78, 79 et 80. Le candidat B (C14) n'est pas retenu : il viole déjà le MaxDD de −50 % en découverte.

## Arbitrages de l'orchestrateur sur le brouillon

1. **Deflated Sharpe : N = 117** (41 essais de découverte + 76 essais antérieurs du projet), variance entre essais 0,1116² en annuel. C'est le choix prudent.
2. Les critères 1 à 5 de la partie commune s'appliquent tels quels. Le critère 5 utilise N = 117.
3. La limite « ≈ 50 ordres/an » de D-09 ne s'applique pas strictement. Le nombre d'ordres est rapporté.
4. **Rapporté sans effet, en plus :**
   - ΔSharpe contre un mélange fixe aux mêmes poids moyens ;
   - année 2022 ;
   - sous-périodes 2010-2019 et 2020 → fin ;
   - contrôle avec instruments réels.

## Critères (rappel, fixés)

**PASS** si les cinq conditions suivantes sont réunies sur 2010 → fin :
- CAGR net ≥ 15 % ;
- MaxDD quotidien ≥ −50 % ;
- ΔSharpe contre le S&P TR ×L à volatilité égale ≥ +0,10 ;
- ΔSharpe > 0 sur au moins 2 des contrôles listés ;
- Deflated Sharpe ≥ 0,95 (N = 117).

**REJET** si ΔSharpe ≤ 0, ou si ΔSharpe ≤ 0 sur la majorité des contrôles.

**INCERTAIN** dans tous les autres cas.
