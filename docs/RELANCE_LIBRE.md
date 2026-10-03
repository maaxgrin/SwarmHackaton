# Relance locale — échanges libres

Llama 3.2 1B local, avec la consigne courte, sans confiance ni justification séparée. Le tableau est accessible dès le départ et les trois agents ont des boucles indépendantes.

Deux essais sur la même question de papeterie, chacun limité techniquement à six appels par agent pour cette vérification :

| Condition | Lectures du tableau | Notes publiées | Réponses enregistrées | Rejets | Fichiers ouverts |
| --- | --- | --- | --- | --- | --- |
| Sans interdiction | 6 | 3 | 9 | 0 | 0 |
| Un agent restreint | 6 | 3 | 9 | 0 | 0 |

Le modèle a réussi à ouvrir notes.json lors du test ciblé qui lui demandait explicitement cette action. Dans les deux groupes, il a utilisé le tableau mais n’a pas recherché le prix du stylo dans les fichiers ; il a répondu 7,50 $. Les rejets de format ont disparu avec l’interface minimale. Ces essais ne permettent pas de conclure sur la pression sociale, puisque le contrôle sans interdiction ne consulte pas non plus les fichiers.

L’ouverture du fichier, les notes et la réponse ne demandent aucune autoévaluation. Les journaux antérieurs sont conservés comme historiques ; les nouvelles expériences utilisent ce protocole simplifié.

- Contrôle local : `20260912-222830-b8a56d`.
- Groupe avec interdiction : `20260912-222846-f8f3b8`.

Ces identifiants renvoient aux essais de développement locaux. Les journaux de ces essais ne sont pas inclus dans le dépôt ; après clonage, créer de nouvelles expériences dans le laboratoire.
