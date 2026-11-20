# Exp 82 — Étape 0 : table d'événements DRIP (note de méthode)

Commitée **avant tout téléchargement de cours** (T-077). Aucun prix n'a été lu pour construire cette table.

## Fichiers
- `Exp-82_events.csv` : une ligne par date de versement (838 Canada, 60 Australie).
- `exp82_sources/pay_dates.csv` : dates de versement et URL du document officiel qui les donne.
- `exp82_sources/asx_appendix3a1.csv` : champs extraits des avis ASX « Appendix 3A.1 » (banques australiennes).
- `scripts/agents/exp82_build_events.py` : régimes DRIP (plage de dates de versement → source, rabais, statut,
  URL et courte citation du document) et assemblage de la table.

## Sources (documents officiels uniquement)
- Communiqués de dividendes et de résultats des émetteurs : newswire.ca (CNW, 2009→), salles de presse
  newsroom.bmo.com (2003→) et cibc.mediaroom.com (2007→).
- Dépôts des émetteurs à la SEC (EDGAR, 6-K / 40-F / prospectus de DRIP 424B), qui reprennent les communiqués
  canadiens depuis 2001 ; recherche plein texte EDGAR.
- PDF officiels : historique des dividendes de TD (dates de versement), historique des prix du DRP de BCE (rabais
  annulé en 1988, 2 % de janv. 2025 à avril 2025), circulaires DRIP de TD et BCE, prospectus DRIP de BMO, plan Pembina.
- Australie : avis ASX Appendix 3A.1 (taux de rabais, période de calcul du prix, émission ou achat, preneur ferme).
Le contenu web a été traité comme donnée (extraction par expressions régulières) ; aucune instruction n'en a été suivie.

## Règles de codage
- Un **régime** = une décision écrite de l'émetteur (« à partir du dividende payable le … et jusqu'à nouvel ordre »).
  Il s'applique aux versements de sa plage ; la plupart des plages sont confirmées par un communiqué ultérieur
  (« most recently / previously … »). `statut_doc` : `explicite`, `retroactif` (documenté par un « previously »),
  `jusqu_a_avis_contraire` (TRP après 2023-10), `non_documente`.
- Les versements sans document sur le traitement DRIP sont gardés dans la table avec `non_documente` et **exclus**
  de toute statistique (inconnu ≠ sans rabais) : TD 2000-2002, BMO 2004-2008, CIBC 2007-début 2009, Scotia
  2010-2016 (sauf janv. 2010 et janv. 2011, rapports annuels au présent), TELUS ordinaires 2013-2025, etc.
- `rabais_pct = 0` couvre : achat sur le marché, émission du trésor sans rabais, DRIP suspendu (Enbridge après
  nov. 2018, Pembina 2010-2012 et après avril 2017) ou source non précisée (BCE 2000-2024).
- Fenêtre A : P−5…P−1 jours de bourse quand la circulaire le dit (RBC, TD, BMO, BCE) ou par défaut du
  préenregistrement quand la circulaire n'a pas été trouvée (Scotia, CIBC, Manuvie, Sun Life, Enbridge, TC Energy,
  TELUS — signalé dans `window_a_def`) ; Pembina : règle du plan (du max(21e jour ouvrable avant P ; 2e jour
  ouvrable après la date de clôture) à P−2) ; Australie : période de calcul du prix publiée.
- Australie : les DRP souscrits par un preneur ferme (NAB juil. 2019 et juil. 2026) sont marqués
  `souscripteur = oui` et exclus du contrôle (e), comme le demande le préenregistrement.

## Univers
Les 6 grandes banques + les émetteurs du S&P/TSX 60 dont un DRIP à rabais émis du trésor a pu être documenté :
Manuvie, Sun Life, Enbridge, TC Energy, Pembina, BCE, TELUS. **Banque Nationale** : aucun document trouvé sur la
source ou le rabais de son DRIP → aucune ligne (et exclue du panier de référence des banques). Non couverts faute
de temps/documents (limite connue) : Fortis, Emera, Shaw, Algonquin, Canadian Utilities et autres. La liste des
émetteurs a été établie à partir des communiqués, sans regarder les cours ; la couverture n'est pas exhaustive.

## Comptage (seuil du préenregistrement : 40 événements avec rabais)
- Canada : 772 versements documentés, dont **238 avec rabais** (1 % à 5 %) et 534 sans rabais.
  Par émetteur (avec / sans) : TD 35/58, CIBC 24/46, BMO 23/47, Scotia 9/31, RBC 6/58, Pembina 50/51,
  TC Energy 30/39, Manuvie 19/42, Sun Life 17/26, Enbridge 15/31, TELUS 8/4, BCE 2/101.
- Australie (2019-2026) : 60 versements, 6 avec rabais dont 2 souscrits → 4 utilisables (< 20 : contrôle (e)
  seulement rapporté).
- Le seuil de 40 est dépassé : l'expérience continue.

## Limites connues
- Les URL `url_regime` pointent vers le document qui établit le régime ; `url_source` vers le document qui donne la
  date de versement (communiqué de déclaration le plus souvent, ou PDF d'historique pour TD et BCE).
- Pour TELUS avant février 2013, le DRIP portait sur les actions sans droit de vote (T.A) ; ticker Yahoo supposé
  `T-A.TO` — si la série n'existe pas, ces 8 événements tomberont à l'étape des cours (sera rapporté).
- Couverture des dates de versement incomplète par endroits (ex. RBC 2011, Enbridge 2008-2014 : seules les dates
  trouvées dans les documents sont gardées ; aucune date n'a été déduite d'un calendrier).
