# Corrections de l'audit du 13 septembre 2026

Les cinq anomalies reproduites dans le code local sont corrigées. Le rapport initial et ses résultats restent inchangés dans le dossier d'audit.

| Anomalie | Comportement corrigé | Validation |
| --- | --- | --- |
| A1 — Exposition prématurée | Les actions utilisent les notes présentes dans la requête ayant produit leur réponse. Récupérer le tableau ne vaut pas envoi au modèle. Les événements portent des identifiants de requête et d'appel d'outil. | Deux outils dans une même réponse ; note arrivée pendant la génération ; réception à la requête suivante |
| A2 — Plafond contournable | Chaque tentative compte avant l'envoi. Les erreurs et les reprises conservent le cumul. Les tokens annoncés dans une réponse tronquée ou invalide sont conservés ; un usage inconnu reste signalé. | Plafond de 1 : une seule requête malgré trois tentatives de reprise, 20 tokens d'entrée et 128 de sortie conservés ; OpenAI compatible et Anthropic factices |
| A3 — Profil variable | Tous les paramètres de fournisseurs sont figés au premier démarrage, avant la première requête. Modifier un profil concerne les prochains essais. Les clés sont liées en mémoire au fournisseur initial et exclues des sauvegardes. | Même modèle et URL pour deux agents du même essai après modification globale ; nouveau profil utilisé dans le nouvel essai ; absence de clés dans les exports et fichiers |
| A4 — Sauvegarde fragile | Un checkpoint atomique contient l'état et toutes les conversations. Les effets d'une réponse et ses résultats d'outils sont enregistrés ensemble. Les miroirs de compatibilité ne font pas autorité. | Pannes avant validation du checkpoint, pendant les miroirs et entre action et résultat ; anciennes conversations corrompues exportées comme partielles |
| A5 — Solo libre contradictoire | Le prompt par défaut dépend de l'effectif. Un solo libre ne demande plus de collaborer ; un prompt explicitement personnalisé est préservé. | Prompt absent, null ou explicitement fourni ; aperçu de l'interface en solo et changement d'effectif |

## Vérification

- **57 tests réussis**, dont 12 nouvelles régressions dans [test_lab_audit_regressions.py](../tests/test_lab_audit_regressions.py).
- **8 contrôles d'audit réussis, aucun invariant en échec**, contre 3 réussites et 5 échecs avant correction.
- **9 704 contrôles du corpus réussis**, sur 100 questions et 200 variantes.
- Syntaxe JavaScript et diff vérifiés.
- Interface contrôlée : solo libre sans pairs fictifs, conservation d'un prompt personnalisé et ouverture d'anciens essais. Aucun défaut JavaScript détecté.
- Exports des archives solo et à huit agents vérifiés après redémarrage du serveur.

Les tests de modèles utilisent des fournisseurs factices. Les vérifications de l'interface utilisent des aperçus et des archives ; elles ne mesurent pas le comportement d'un LLM réel.

## Interpréter les anciennes données

Les nouvelles traces portent `trace_version: 2`. Les archives antérieures ne sont pas réécrites : elles peuvent avoir sous-compté les requêtes échouées et leurs tokens. Des tokens non enregistrés ne peuvent pas être reconstitués par cette correction. Le défaut A1 concerne des outils choisis dans une même réponse ; l'audit initial n'avait pas trouvé ce cas dans les historiques LLM locaux examinés.

Le champ `reported_but_discarded_tokens` de l'ancienne sonde d'audit est calculé comme un total théorique, sans soustraire les tokens enregistrés. Pour vérifier la correction, regarder `recorded_usage` : les 148 tokens de sa réponse tronquée sont maintenant présents. La nouvelle suite vérifie explicitement ces valeurs.

Le checkpoint garantit une dernière sauvegarde cohérente, pas la reconstruction d'une réponse perdue avant son enregistrement. Une tentative réservée avant un incident reste comptée. Une ancienne conversation illisible est signalée comme export partiel, sans inventer son contenu.
