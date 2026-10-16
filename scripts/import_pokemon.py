
import json
import os
import time
from pathlib import Path
from urllib.request import Request, urlopen

import psycopg
from psycopg.types.json import Jsonb


# Racine du projet.
ROOT = Path(__file__).resolve().parent.parent


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


# Récupère une ressource JSON depuis la PokéAPI.
def fetch_json(url):
    request = Request(
        url,
        headers={"User-Agent": "PokedexApp/1.0"},
    )

    with urlopen(request, timeout=30) as response:
        return json.load(response)


# Récupère le nom et la description française d'un Pokémon.
def get_french_info(species_url):
    species = fetch_json(species_url)

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
            entry["flavor_text"]
            .replace("\n", " ")
            .replace("\f", " ")
            for entry in species["flavor_text_entries"]
            if entry["language"]["name"] == "fr"
        ),
        None,
    )

    return name_fr, description, species


def main():
    env = load_env()

    # Connexion à PostgreSQL sur le port exposé par Docker.
    with psycopg.connect(
        host="localhost",
        port=5432,
        dbname=env["POSTGRES_DB"],
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    ) as connection:

        with connection.cursor() as cursor:

            # Importe les 1025 Pokémon standards.
            for pokemon_id in range(1, 1026):
                try:
                    pokemon = fetch_json(
                        f"https://pokeapi.co/api/v2/pokemon/{pokemon_id}"
                    )

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

            connection.commit()

    print("Import terminé.")


if __name__ == "__main__":
    main()
