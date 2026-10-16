from pydantic import BaseModel


class PokemonResponse(BaseModel):
    """Représentation publique d'un Pokémon."""

    id: int
    pokedex_number: int
    name: str
    name_fr: str | None
    types: list[str]
    image_key: str | None
    model_key: str | None


class HealthResponse(BaseModel):
    """Réponse du endpoint de santé."""

    status: str
