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
    region_name="us-east-1",
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
        s3.head_bucket(Bucket=BUCKET_NAME)
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

        # ----------------------------------------------------
        # 1. IMAGE
        # ----------------------------------------------------

        image_path = IMAGES_DIR / f"{pokemon_name}.png"
        image_url = IMAGE_URL.format(id=pokemon_id)

        if download_file(image_url, image_path):
            if upload_file(
                image_path,
                f"images/{pokemon_name}.png",
                "image/png",
            ):
                images_ok += 1
                print("  Image : OK")
            else:
                images_missing.append(pokemon_id)
                print("  Image : échec de l'envoi")
        else:
            images_missing.append(pokemon_id)
            print("  Image : indisponible")

        # ----------------------------------------------------
        # 2. MODÈLE 3D
        # ----------------------------------------------------

        model_path = MODELS_DIR / f"{pokemon_name}.glb"
        model_url = MODEL_URL.format(id=pokemon_id)

        if download_file(model_url, model_path):
            if upload_file(
                model_path,
                f"models/{pokemon_name}.glb",
                "model/gltf-binary",
            ):
                models_ok += 1
                print("  Modèle 3D : OK")
            else:
                models_missing.append(pokemon_id)
                print("  Modèle 3D : échec de l'envoi")
        else:
            models_missing.append(pokemon_id)
            print("  Modèle 3D : indisponible")

        # Petite pause entre les Pokémon.
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
