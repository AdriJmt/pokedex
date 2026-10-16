
import os
from typing import Annotated

import psycopg
from psycopg.rows import dict_row
from fastapi import Depends, FastAPI, HTTPException, Query

from app.schemas.pokemon import HealthResponse, PokemonResponse

app = FastAPI(
    title="Pokedex API",
    description="API du Pokédex",
    version="0.1.0",
)


def get_database_url() -> str:
    """Récupère l'URL de connexion à PostgreSQL."""
    return os.environ["DATABASE_URL"]


DatabaseUrl = Annotated[str, Depends(get_database_url)]


@app.get("/health")
def health_check() -> HealthResponse:
    """Vérifie que l'API répond."""
    return {"status": "ok"}


@app.get(
    "/pokemon",
    responses={
        500: {"description": "Erreur lors de la lecture des Pokémon."}
    },
)
def get_pokemon(
    database_url: DatabaseUrl,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PokemonResponse]:
    """Récupère une liste paginée de Pokémon depuis PostgreSQL."""
    try:
        with (
            psycopg.connect(database_url, row_factory=dict_row) as connection,
            connection.cursor() as cursor,
        ):
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
            return cursor.fetchall()

    except psycopg.Error as error:
        raise HTTPException(
            status_code=500,
            detail="Erreur lors de la lecture des Pokémon.",
        ) from error
