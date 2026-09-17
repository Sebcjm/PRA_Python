#SOURCE_DIR = "/var/www/html"
#BACKUP_ROOT = "/backup"

#ARCHIVE_DIR = f"{BACKUP_ROOT}/keys"
#KEY_DIR = f"{BACKUP_ROOT}/keys"
#LOG_DIR = f"{BACKUP_ROOT}/logs"

#value = int(input("Choisissez un nombre entre 1 et 3"))
#print("1) Sauvegarde complète")
#print("2) Sauvegarde + suppression de la clé")
#print("3) Quitter")
#match value : 
#    case 1 : 

#!/usr/bin/env python3

# ============================================================
# backup_www.py - Sauvegarde chiffrée de /var/www/html
# ============================================================

import os
import sys
import shutil
import subprocess
import tarfile
from pathlib import Path
from datetime import datetime


# ---------- Configuration ----------
SOURCE_DIR = Path("/var/www/html")
BACKUP_ROOT = Path("/backup")

ARCHIVE_DIR = BACKUP_ROOT / "archives"
KEY_DIR = BACKUP_ROOT / "keys"
LOG_DIR = BACKUP_ROOT / "logs"


# ---------- Fonctions utilitaires ----------
def die(message):
    """Affiche une erreur et arrête le programme."""
    print(f"[ERREUR] {message}", file=sys.stderr)
    sys.exit(1)


def log(message):
    """Affiche un message et l'ajoute au fichier de log."""
    date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ligne = f"[{date}] {message}"

    print(ligne)

    with LOG_FILE.open("a", encoding="utf-8") as fichier:
        fichier.write(ligne + "\n")


# ---------- Vérifications ----------
if os.geteuid() != 0:
    die("Ce script doit être exécuté en root (sudo).")

if not SOURCE_DIR.is_dir():
    die(f"Le dossier source {SOURCE_DIR} n'existe pas.")

if shutil.which("openssl") is None:
    die("openssl n'est pas installé.")


# ---------- Création des dossiers ----------
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
KEY_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ---------- Mode automatique ou interactif ----------
if "--auto" in sys.argv:
    # Mode cron : aucune question posée
    # La clé est automatiquement conservée
    delete_key_after = False

else:
    os.system("clear")

    print("============================================================")
    print(f"   Sauvegarde chiffrée de : {SOURCE_DIR}")
    print("============================================================")
    print("1) Sauvegarde complète (archive + chiffrement AES-256)")
    print("2) Sauvegarde chiffrée + suppression de la clé après usage")
    print("3) Quitter")
    print("============================================================")

    choice = input("Votre choix [1-3] : ")

    if choice == "1":
        delete_key_after = False

    elif choice == "2":
        delete_key_after = True

    elif choice == "3":
        print("Annulé.")
        sys.exit(0)

    else:
        die("Choix invalide.")


# ---------- Génération de l'horodatage ----------
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

basename = timestamp

archive_plain = ARCHIVE_DIR / f"{basename}.tar.gz"
archive_enc = ARCHIVE_DIR / f"{basename}.tar.gz.enc"
key_file = KEY_DIR / f"{basename}.key"
LOG_FILE = LOG_DIR / f"{basename}.log"


# ---------- Début de la sauvegarde ----------
log(f"=== Début de la sauvegarde : {basename} ===")


# ---------- Génération du secret ----------
log("Génération de la clé de chiffrement...")

try:
    with key_file.open("w") as fichier:
        subprocess.run(
            ["openssl", "rand", "-base64", "32"],
            stdout=fichier,
            check=True,
            text=True
        )

except subprocess.CalledProcessError:
    die("Impossible de générer la clé.")

# chmod 600 : seul root peut lire/écrire la clé
key_file.chmod(0o600)

log(f"Clé générée : {key_file}")


# ---------- Création de l'archive tar.gz ----------
log(f"Création de l'archive : {archive_plain}")

try:
    with tarfile.open(archive_plain, "w:gz") as tar:
        tar.add(
            SOURCE_DIR,
            arcname=SOURCE_DIR.name
        )

except (tarfile.TarError, OSError) as erreur:
    archive_plain.unlink(missing_ok=True)
    die(f"Impossible de créer l'archive : {erreur}")


size = archive_plain.stat().st_size

log(f"Archive créée : {size} octets")


# ---------- Chiffrement AES-256-CBC ----------
log("Chiffrement AES-256-CBC de l'archive...")

commande = [
    "openssl",
    "enc",
    "-aes-256-cbc",
    "-salt",
    "-pbkdf2",
    "-iter", "100000",
    "-in", str(archive_plain),
    "-out", str(archive_enc),
    "-pass", f"file:{key_file}"
]

try:
    subprocess.run(
        commande,
        check=True
    )

except subprocess.CalledProcessError:
    archive_enc.unlink(missing_ok=True)
    archive_plain.unlink(missing_ok=True)
    die("Échec du chiffrement de l'archive.")


size_enc = archive_enc.stat().st_size

log(
    f"Archive chiffrée : {archive_enc} "
    f"({size_enc} octets)"
)


# ---------- Suppression de l'archive en clair ----------
archive_plain.unlink(missing_ok=True)

log("Archive non chiffrée supprimée.")


# ---------- Option : suppression de la clé ----------
if delete_key_after:

    log(
        "ATTENTION : la clé va être supprimée. "
        "Notez-la avant de continuer !"
    )

    print()
    print("===== CLÉ DE DÉCHIFFREMENT =====")

    with key_file.open("r") as fichier:
        print(fichier.read().strip())

    print("================================")
    print()

    confirm = input(
        "Avez-vous bien noté la clé ? [o/N] : "
    )

    if confirm.lower() == "o":

        # On essaie d'abord d'utiliser shred,
        # comme dans le script Bash.
        if shutil.which("shred") is not None:
            try:
                subprocess.run(
                    ["shred", "-u", str(key_file)],
                    check=True
                )
            except subprocess.CalledProcessError:
                key_file.unlink(missing_ok=True)
        else:
            key_file.unlink(missing_ok=True)

        log(f"Clé supprimée : {key_file}")

    else:
        log(f"Conservation de la clé : {key_file}")


# ---------- Fin ----------
log("=== Sauvegarde terminée avec succès ===")

print()
print(f"Archive : {archive_enc}")

if key_file.exists():
    print(f"Clé     : {key_file}")
else:
    print("Clé     : supprimée")

print(f"Log     : {LOG_FILE}")