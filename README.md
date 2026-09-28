# Entreprise – Miel

## Outil de prospection des boutiques

`prospection/prospection_miel.py` liste les commerces autour d'une adresse (épiceries fines, magasins bio, primeurs, fromageries, boulangeries, caves…) et récupère leur **téléphone** et leur **e-mail** pour les démarcher avec le miel.

### Comment ça marche

1. L'adresse est placée sur la carte avec OpenStreetMap.
2. Les commerces dans le rayon choisi sont récupérés depuis OpenStreetMap (données ouvertes et libres).
3. Si une boutique a un site web mais pas d'e-mail ou de téléphone connu, l'outil lit sa page d'accueil et ses pages « contact » / « mentions légales » (en respectant `robots.txt`).
4. Le résultat est un fichier CSV trié par distance, avec les colonnes « Statut » et « Notes » pour suivre la prospection.

Aucune dépendance à installer : Python 3 suffit.

### Utilisation

```bash
python3 prospection/prospection_miel.py --adresse "12 rue de la Paix, 69001 Lyon" --rayon 5000
```

Options utiles :

| Option | Rôle |
|---|---|
| `--rayon 10000` | Rayon en mètres (défaut 5 km) |
| `--types deli,organic,farm` | Limiter à certains types de commerces |
| `--types ...,supermarket` | Ajouter les supermarchés (non inclus par défaut) |
| `--sans-sites` | Ne pas visiter les sites web (plus rapide) |
| `--sortie fichier.csv` | Nom du fichier de résultat |

### Règles à respecter pour démarcher (RGPD / CNIL)

- En B2B, l'e-mail de prospection vers une adresse **professionnelle** est autorisé sans accord préalable, si le message concerne l'activité de la boutique (ce qui est le cas du miel pour une épicerie).
- Chaque e-mail doit dire **qui tu es** et proposer un **moyen simple de ne plus recevoir de messages**. Retire tout de suite les personnes qui le demandent.
- Ne garde que les données utiles (nom, contact professionnel) et supprime les prospects qui ne donnent pas suite après un certain temps.
