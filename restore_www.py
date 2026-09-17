#!/usr/bin/env python3

import os
import sys
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from datetime import datetime
import getpass


BACKUP_ROOT = Path("/backup")
ARCHIVE_DIR = BACKUP_ROOT / "archives"
KEY_DIR = BACKUP_ROOT / "keys"
RESTORE_DIR = Path("/var/www")

if os.geteuid() != 0:
    print("[ERREUR] Exécuter en root (sudo).", file=sys.stderr)
    sys.exit(1)

if shutil.which("openssl") is None:
    print("[ERREUR] openssl manquant.", file=sys.stderr)
    sys.exit(1)

os.system("clear")

print("============================================================")
print("   Restauration de sauvegardes chiffrées")
print("============================================================")

archives = sorted(
    ARCHIVE_DIR.glob("*.tar.gz.enc"),
    key=lambda fichier: fichier.stat().st_mtime,
    reverse=True
)

if not archives:
    print("Aucune archive trouvée.")
    sys.exit(1)

for i, archive in enumerate(archives, start=1):
    size = archive.stat().st_size
    date = datetime.fromtimestamp(
        archive.stat().st_mtime
    ).strftime("%Y-%m-%d %H:%M:%S")

    print(f"{i}) {archive.name} ({size} octets, {date})")

selection = input(
    "Numéro de l'archive à restaurer (ou 'q' pour quitter) : "
)

if selection.lower() == "q":
    sys.exit(0)

try:
    selection = int(selection)
except ValueError:
    print("Choix invalide.")
    sys.exit(1)

if selection < 1 or selection > len(archives):
    print("Choix invalide.")
    sys.exit(1)

archive_enc = archives[selection - 1]

basename = archive_enc.name.removesuffix(".tar.gz.enc")

key_file = KEY_DIR / f"{basename}.key"
archive_plain = Path("/tmp") / f"{basename}.tar.gz"

cleanup_key = False

if key_file.is_file():
    print(f"Clé trouvée automatiquement : {key_file}")
    use_key = input("Utiliser cette clé ? [O/n] : ")

    if use_key.lower() == "n":
        key_file = None

if key_file is None or not key_file.is_file():
    manual_key = getpass.getpass("Clé de déchiffrement : ")

    if not manual_key:
        print("Clé vide, abandon.")
        sys.exit(1)

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        delete=False
    )

    tmp.write(manual_key + "\n")
    tmp.close()

    key_file = Path(tmp.name)
    cleanup_key = True

commande = [
    "openssl",
    "enc",
    "-d",
    "-aes-256-cbc",
    "-pbkdf2",
    "-iter", "100000",
    "-in", str(archive_enc),
    "-out", str(archive_plain),
    "-pass", f"file:{key_file}"
]

try:
    subprocess.run(commande, check=True)
except subprocess.CalledProcessError:
    print("[ERREUR] Échec du déchiffrement (mauvaise clé ?).")

    archive_plain.unlink(missing_ok=True)

    if cleanup_key:
        key_file.unlink(missing_ok=True)

    sys.exit(1)

dest = input(
    f"Restaurer dans [{RESTORE_DIR}] ? "
).strip()

if not dest:
    dest = RESTORE_DIR
else:
    dest = Path(dest)

confirmation = input(
    f"ATTENTION : le dossier 'html' existant dans {dest} "
    "sera remplacé. Continuer ? [o/N] : "
)

if confirmation.lower() != "o":
    print("Annulé.")
    archive_plain.unlink(missing_ok=True)

    if cleanup_key:
        key_file.unlink(missing_ok=True)

    sys.exit(0)

html_dir = dest / "html"

if html_dir.is_dir():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = dest / f"html.bak.{timestamp}"

    shutil.move(html_dir, safe)

dest.mkdir(parents=True, exist_ok=True)

with tarfile.open(archive_plain, "r:gz") as tar:
    tar.extractall(dest)

for path in html_dir.rglob("*"):
    if path.is_dir():
        path.chmod(0o755)
    elif path.is_file():
        path.chmod(0o644)

shutil.chown(html_dir, user="www-data", group="www-data")

for path in html_dir.rglob("*"):
    shutil.chown(path, user="www-data", group="www-data")

    if path.is_dir():
        path.chmod(0o755)
    elif path.is_file():
        path.chmod(0o644)

archive_plain.unlink(missing_ok=True)

if cleanup_key:
    key_file.unlink(missing_ok=True)

print()
print("=== Restauration terminée avec succès ===")
print(f"Contenu restauré : {html_dir}")