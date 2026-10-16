
import os

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, HTTPException, Query

app = FastAPI(
    title="Pokedex API",
    description="API du Pokédex",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    """Vérifie que l'API répond."""
    return {"status": "ok"}

# Récupère une liste de Pokémon depuis PostgreSQL.


@app.get("/pokemon")
def get_pokemon(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    # L'URL est fournie par Docker via la variable DATABASE_URL.
    database_url = os.environ["DATABASE_URL"]

    try:
        # Ouvre une connexion à PostgreSQL.
        with psycopg.connect(
            database_url,
            row_factory=dict_row,
        ) as connection:

            # Exécute la requête SQL.
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        id,
                        pokedex_number,
                        name,
                        name_fr,
                        types,
                        image_key,
                        model_key
                    FROM pokemon
                    ORDER BY pokedex_number
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset),
                )

                # Convertit les lignes SQL en dictionnaires Python.
                pokemon = cursor.fetchall()

        # FastAPI convertit la liste en JSON.
        return pokemon

    except psycopg.Error:
        # Évite de renvoyer les détails internes de la base.
        raise HTTPException(
            status_code=500,
            detail="Erreur lors de la lecture des Pokémon.",
        )
