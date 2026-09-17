#!/bin/bash
# Backup von Loomina (/opt/loomina): das Volume mit SQLite und Zwischendateien.
# Die erzeugten Bilder und Videos liegen in Backblaze B2, hier steht, wem sie
# gehoeren - inklusive der Arbeitsbereich-Token aus geteilten Links.
# Taeglich 05:15 UTC per systemd-Timer, 14 Tage lokal und in R2.
set -euo pipefail

STAMP=$(date +%F_%H%M%S)
BACKUP_DIR=/opt/loomina/backups
# Die eigene IPv4 des Servers: rclone bindet die Verbindung daran, sonst waehlt
# es unter Umstaenden eine Adresse, die der Bucket nicht erwartet.
SERVER_IPV4=${SERVER_IPV4:?eigene Server-IPv4 setzen}
REMOTE=r2:pocketbase-backups/loomina
RCLONE_FLAGS=(--bind "${SERVER_IPV4}" --s3-no-check-bucket)

# Der Ordner gehoert dem Dienstnutzer, nicht root — sonst scheitert das erste
# Backup an "Permission denied" (passiert, /opt/loomina gehoert root):
#   sudo install -d -o marc -g marc -m 700 /opt/loomina/backups
umask 077

docker run --rm \
  -v loomina_vault-data:/data:ro \
  -v "${BACKUP_DIR}":/backup \
  alpine:3.20 \
  sh -c "umask 077 && tar czf /backup/vault_${STAMP}.tar.gz -C /data . && chown $(id -u):$(id -g) /backup/vault_${STAMP}.tar.gz"

find "${BACKUP_DIR}" -name "vault_*.tar.gz" -mtime +14 -delete

rclone copy "${BACKUP_DIR}/vault_${STAMP}.tar.gz" "${REMOTE}/" "${RCLONE_FLAGS[@]}"
rclone delete "${REMOTE}" --min-age 14d "${RCLONE_FLAGS[@]}"
