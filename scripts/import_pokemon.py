
import json
import re
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

import psycopg
from psycopg.types.json import Jsonb


# Racine du projet.
ROOT = Path(__file__).resolve().parent.parent

# URL officielle de la PokéAPI.
POKEAPI_BASE_URL = "https://pokeapi.co/api/v2"


# Lit les variables du fichier .env sans afficher les secrets.
def load_env():
    env = {}

    with open(ROOT / ".env", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("'\"")

    return env


# Contrôle les redirections HTTP pour éviter les domaines externes.
class PokeApiRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed_url = urlparse(newurl)

        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname != "pokeapi.co"
            or parsed_url.port not in (None, 443)
            or parsed_url.username is not None
            or parsed_url.password is not None
        ):
            raise URLError("Redirection externe interdite")

        return super().redirect_request(
            req, fp, code, msg, headers, newurl
        )


# Récupère un JSON depuis un endpoint autorisé de la PokéAPI.
def fetch_json(endpoint):
    # Seuls les Pokémon et les espèces avec un identifiant positif sont autorisés.
    if not re.fullmatch(
        r"(?:pokemon|pokemon-species)/[1-9]\d*",
        endpoint,
    ):
        raise ValueError(f"Endpoint PokéAPI invalide : {endpoint}")

    # Construit l'URL depuis une base fixe.
    url = f"{POKEAPI_BASE_URL}/{endpoint}"

    request = Request(
        url,
        headers={"User-Agent": "PokedexApp/1.0"},
    )

    # Utilise un gestionnaire qui contrôle les redirections.
    opener = build_opener(PokeApiRedirectHandler)

    with opener.open(request, timeout=30) as response:
        return json.load(response)


# Récupère le nom et la description française d'une espèce.
def get_french_info(species_url):
    parsed_url = urlparse(species_url)

    # Vérifie que l'URL correspond au domaine officiel.
    if (
        parsed_url.scheme != "https"
        or parsed_url.netloc != "pokeapi.co"
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise ValueError("URL d'espèce PokéAPI invalide")

    # Accepte uniquement le chemin officiel d'une espèce.
    match = re.fullmatch(
        r"/api/v2/pokemon-species/([1-9]\d*)/?",
        parsed_url.path,
    )

    if not match:
        raise ValueError("Chemin d'espèce PokéAPI invalide")

    species_id = match.group(1)

    # Reconstruit un endpoint contrôlé plutôt que d'utiliser l'URL reçue.
    species = fetch_json(f"pokemon-species/{species_id}")

    name_fr = next(
        (
            name["name"]
            for name in species["names"]
            if name["language"]["name"] == "fr"
        ),
        None,
    )

    description = next(
        (
            entry["flavor_text"].replace("\n", " ").replace("\f", " ")
            for entry in species["flavor_text_entries"]
            if entry["language"]["name"] == "fr"
        ),
        None,
    )

    return name_fr, description, species


def main():
    env = load_env()

    # Connexion à PostgreSQL et ouverture du curseur.
    with (
        psycopg.connect(
            host="localhost",
            port=5432,
            dbname=env["POSTGRES_DB"],
            user=env["POSTGRES_USER"],
            password=env["POSTGRES_PASSWORD"],
        ) as connection,
        connection.cursor() as cursor,
    ):
        # Importe les 1 025 Pokémon standards.
        for pokemon_id in range(1, 1026):
            try:
                # L'endpoint est construit à partir d'un identifiant numérique.
                pokemon = fetch_json(f"pokemon/{pokemon_id}")

                name_fr, description, species = get_french_info(
                    pokemon["species"]["url"]
                )

                image_path = (
                    ROOT / "data" / "images" / f"{pokemon_id:04d}.png"
                )
                model_path = (
                    ROOT / "data" / "modeles" / f"{pokemon_id:04d}.glb"
                )

                # Les clés correspondent aux objets dans SeaweedFS.
                image_key = (
                    f"images/{pokemon_id:04d}.png"
                    if image_path.is_file()
                    else None
                )
                model_key = (
                    f"models/{pokemon_id:04d}.glb"
                    if model_path.is_file()
                    else None
                )

                cursor.execute(
                    """
                    INSERT INTO pokemon (
                        id, pokedex_number, name, name_fr,
                        height, weight, base_experience,
                        types, abilities, stats, description,
                        capture_rate, is_legendary, is_mythical,
                        image_key, model_key
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        name_fr = EXCLUDED.name_fr,
                        height = EXCLUDED.height,
                        weight = EXCLUDED.weight,
                        base_experience = EXCLUDED.base_experience,
                        types = EXCLUDED.types,
                        abilities = EXCLUDED.abilities,
                        stats = EXCLUDED.stats,
                        description = EXCLUDED.description,
                        capture_rate = EXCLUDED.capture_rate,
                        is_legendary = EXCLUDED.is_legendary,
                        is_mythical = EXCLUDED.is_mythical,
                        image_key = EXCLUDED.image_key,
                        model_key = EXCLUDED.model_key,
                        updated_at = NOW()
                    """,
                    (
                        pokemon["id"],
                        pokemon["id"],
                        pokemon["name"],
                        name_fr,
                        pokemon["height"],
                        pokemon["weight"],
                        pokemon["base_experience"],
                        Jsonb([
                            item["type"]["name"]
                            for item in pokemon["types"]
                        ]),
                        Jsonb([
                            {
                                "name": item["ability"]["name"],
                                "is_hidden": item["is_hidden"],
                            }
                            for item in pokemon["abilities"]
                        ]),
                        Jsonb([
                            {
                                "name": item["stat"]["name"],
                                "base_stat": item["base_stat"],
                            }
                            for item in pokemon["stats"]
                        ]),
                        description,
                        species["capture_rate"],
                        species["is_legendary"],
                        species["is_mythical"],
                        image_key,
                        model_key,
                    ),
                )

                # Valide régulièrement les données importées.
                if pokemon_id % 25 == 0:
                    connection.commit()
                    print(f"{pokemon_id}/1025 Pokémon traités")

                # Limite la fréquence des requêtes à la PokéAPI.
                time.sleep(0.1)

            except Exception as error:
                connection.rollback()
                print(f"Erreur pour le Pokémon {pokemon_id}: {error}")

        # Valide les dernières données importées.
        connection.commit()

    print("Import terminé.")


if __name__ == "__main__":
    main()
