from botocore.exceptions import BotoCoreError, ClientError
from botocore.client import Config
import requests
import boto3
from pathlib import Path
import time
import os


# ============================================================
# CONFIGURATION
# ============================================================

S3_ENDPOINT = "http://localhost:8333"
BUCKET_NAME = "pokemon-assets"

ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "pokedex_admin")
SECRET_KEY = os.getenv("S3_SECRET_KEY", "")

# Dossiers locaux
IMAGES_DIR = Path("images")
MODELS_DIR = Path("modeles")

EXPECTED_BUCKET_OWNER = os.getenv("EXPECTED_BUCKET_OWNER", "")

# API PokéAPI : liste des Pokémon
POKEAPI_URL = "https://pokeapi.co/api/v2/pokemon"

# Images officielles PokéAPI
IMAGE_URL = (
    "https://raw.githubusercontent.com/PokeAPI/sprites/"
    "master/sprites/pokemon/other/official-artwork/{id}.png"
)

# Modèles 3D : source communautaire
MODEL_URL = (
    "https://raw.githubusercontent.com/pokemon-party/3d-pokemon/"
    "main/models/opt/regular/{id}.glb"
)

# ============================================================
# CLIENTS HTTP ET S3
# ============================================================

session = requests.Session()
session.headers["User-Agent"] = "PokedexAssetSeeder/1.0"

s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    region_name=os.getenv("AWS_REGION"),
    config=Config(signature_version="s3v4"),
)


# ============================================================
# RÉCUPÉRER TOUS LES IDENTIFIANTS
# ============================================================

def get_all_pokemon_ids():
    """Récupère tous les identifiants Pokémon exposés par la PokéAPI."""

    pokemon_ids = []
    url = f"{POKEAPI_URL}?limit=1000"

    while url:
        response = session.get(url, timeout=30)
        response.raise_for_status()

        data = response.json()

        for pokemon in data["results"]:
            pokemon_id = int(
                pokemon["url"].rstrip("/").split("/")[-1]
            )
            pokemon_ids.append(pokemon_id)

        # URL de la page suivante, ou None si la liste est terminée.
        url = data["next"]

    return sorted(set(pokemon_ids))


# ============================================================
# TÉLÉCHARGER UN FICHIER
# ============================================================

def download_file(url, destination):
    """Télécharge un fichier s'il n'existe pas déjà localement."""

    # Réutiliser le fichier local s'il existe déjà.
    if destination.exists() and destination.stat().st_size > 0:
        return True

    try:
        response = session.get(url, timeout=30)

        # Le fichier n'existe pas à cette adresse.
        if response.status_code == 404:
            return False

        response.raise_for_status()

        # Créer le dossier si nécessaire.
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Enregistrer le fichier.
        destination.write_bytes(response.content)

        return destination.stat().st_size > 0

    except requests.RequestException as error:
        print(f"  Erreur téléchargement : {error}")
        return False


# ============================================================
# ENVOYER UN FICHIER VERS SEAWEEDFS S3
# ============================================================

def upload_file(path, object_key, content_type):
    """Envoie un fichier local vers le bucket S3."""

    try:
        s3.upload_file(
            str(path),
            BUCKET_NAME,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )
        return True

    except (ClientError, BotoCoreError) as error:
        print(f"  Erreur upload {object_key} : {error}")
        return False


def process_asset(
    pokemon_id,
    url_template,
    directory,
    extension,
    object_prefix,
    content_type,
    label,
):
    """Télécharge puis envoie un fichier vers le stockage S3."""

    filename = f"{pokemon_id:04d}.{extension}"
    path = directory / filename
    url = url_template.format(id=pokemon_id)

    # Télécharger le fichier ou réutiliser le fichier local.
    if not download_file(url, path):
        print(f"  {label} : indisponible")
        return False

    # Envoyer le fichier vers le stockage.
    object_key = f"{object_prefix}/{filename}"

    if not upload_file(path, object_key, content_type):
        print(f"  {label} : échec de l'envoi")
        return False

    print(f"  {label} : OK")
    return True


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main():
    # Créer les dossiers locaux.
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    images_ok = 0
    models_ok = 0
    images_missing = []
    models_missing = []

    # Vérifier l'accès au bucket S3.
    try:
        s3.head_bucket(
            Bucket=BUCKET_NAME,
            ExpectedBucketOwner=EXPECTED_BUCKET_OWNER,
        )
    except (ClientError, BotoCoreError) as error:
        print(f"Impossible d'accéder au bucket {BUCKET_NAME} : {error}")
        return

    # Récupérer tous les identifiants disponibles.
    try:
        pokemon_ids = get_all_pokemon_ids()
    except requests.RequestException as error:
        print(f"Impossible de récupérer la liste des Pokémon : {error}")
        return

    total = len(pokemon_ids)
    print(f"{total} identifiants Pokémon trouvés.")

    # Parcourir tous les identifiants.
    for index, pokemon_id in enumerate(pokemon_ids, start=1):
        pokemon_name = f"{pokemon_id:04d}"

        print(f"\n[{index}/{total}] Pokémon #{pokemon_name}")

        # Traiter l'image du Pokémon.
        if process_asset(
            pokemon_id,
            IMAGE_URL,
            IMAGES_DIR,
            "png",
            "images",
            "image/png",
            "Image",
        ):
            images_ok += 1
        else:
            images_missing.append(pokemon_id)

        # Traiter le modèle 3D du Pokémon.
        if process_asset(
            pokemon_id,
            MODEL_URL,
            MODELS_DIR,
            "glb",
            "models",
            "model/gltf-binary",
            "Modèle 3D",
        ):
            models_ok += 1
        else:
            models_missing.append(pokemon_id)

        time.sleep(0.1)

    # ========================================================
    # BILAN FINAL
    # ========================================================

    print("\n========== BILAN ==========")
    print(f"Identifiants traités : {total}")
    print(f"Images envoyées : {images_ok}/{total}")
    print(f"Images manquantes ou en échec : {len(images_missing)}")
    print(f"Modèles 3D envoyés : {models_ok}/{total}")
    print(f"Modèles manquants ou en échec : {len(models_missing)}")

    if images_missing:
        print(f"Identifiants sans image : {images_missing}")

    if models_missing:
        print(f"Identifiants sans modèle 3D : {models_missing}")


if __name__ == "__main__":
    main()
