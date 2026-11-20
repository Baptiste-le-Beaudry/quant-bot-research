# Exp 63 — Stratégie C « confirmation du rebond » — PRÉENREGISTREMENT

- **ID :** Exp 63 / `C-REBOUND-CONFIRM-001` (T-040, idée proposée par l'auteur le 2026-10-07). Préenregistré le 2026-10-08 par l'orchestrateur, figé par ce commit, **avant tout calcul**. Juge : Validateur.
- **Ce n'est pas une optimisation de A** (D-06) : la règle A déployée reste gelée. C est une stratégie distincte, avec une autre structure d'entrée.

## Hypothèse

Acheter un creux détecté par le RF n'indique pas que le creux est terminé, et une partie des pertes vient de couteaux qui tombent. Attendre que le prix **commence réellement à remonter** avant d'entrer élimine une partie de ces faux creux. Le gain ainsi obtenu doit être plus grand que le rebond manqué entre le signal et la confirmation.

## Règle C (fixée, une seule variante décisionnelle)

1. **Signal :** modèle **REF** de l'Exp 53/61 (label 10 min, p ≥ 0,70, mêmes filtres), mêmes plis, mêmes signaux que REF. Réutiliser les modèles sauvegardés par l'Exp 61 si leurs signaux sont identiques à ceux de l'Exp 53 (vérification à rapporter).
2. **Confirmation :** soit H le **plus haut de la barre du signal**. On attend la première barre k ∈ [1, 15] après le signal dont la **clôture > H**. S'il n'y en a aucune dans les 15 barres, il n'y a pas de trade.
3. **Entrée :** à l'open de la barre suivant la barre de confirmation.
4. **Sortie :** au temps, 50 barres après l'entrée, au close, **sans stop** (comme D-TIME50).
5. Une position par symbole. Un signal qui survient pendant qu'une position ou une attente de confirmation est en cours sur le même symbole est ignoré.

## Protocole

- **Plis et populations :** identiques à l'Exp 53, avec walk-forward de 2021-11 à 2026-08-17. **P1** = tests 2021-11 → 2025-04 ; **P2** = tests 2025-04 → 2026-08-17. Ces données ont déjà été vues : elles servent **seulement à rejeter**.
- **Exécution :** harness v1.2.0, symboles SOL, BTC, ETH (barres Binance), coût `/build` (≈ 0,02 % AR + 0,01 USD/swap), compte 500 CAD, 33 %/position, plafond de 3 positions.
- **Référence :** REF avec entrée immédiate (open suivant le signal), même sortie, mêmes coûts, même compte.

## Critères (fixés)

- **PASS** si, dans P1 **et** dans P2 : (a) net moyen par trade C > 0 ; (b) net moyen par trade C − REF ≥ +0,03 point ; (c) CAGR du compte C ≥ CAGR du compte REF ; (d) MaxDD du compte C ≥ −35 %.
- **REJET** si net moyen par trade C ≤ 0 dans P1 ou dans P2, ou si CAGR C < CAGR REF dans P1 **et** dans P2.
- **INCERTAIN** sinon.
- **Rapporté sans effet :** taux de confirmation, délai médian, rebond manqué (prix d'entrée C par rapport à REF), PF, pire jour, détail par symbole, fenêtres de confirmation K = 5 et K = 30, coût `/order`.

## Variantes comptées

1 décisionnelle (K = 15, clôture > plus haut de la barre du signal). Rapportées sans effet : K = 5, K = 30, `/order`.

## Si PASS

Instance paper distincte de C sur le serveur forward, préenregistrée, avec une règle d'arrêt du type D-05. A reste inchangée. Les stratégies B et D (zones de haute confiance, taille selon le score) passent après, avec des critères plus sévères, parce qu'elles s'inspirent de l'Exp 58 déjà vue.
