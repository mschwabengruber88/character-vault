#!/usr/bin/env bash
# Traegt Schluessel verdeckt in /opt/loomina/.env auf dem Server ein.
# Leere Eingabe ueberspringt einen Wert. Nichts wird angezeigt oder lokal gespeichert.
#
#   bash infra/geheimnisse-setzen.sh              alle Werte
#   bash infra/geheimnisse-setzen.sh GMI_API_KEY  nur diesen
set -euo pipefail
# Ziel setzen, z. B.: export LOOMINA_SERVER=benutzer@1.2.3.4
SERVER=${LOOMINA_SERVER:?LOOMINA_SERVER setzen (benutzer@host)}

hinweis() {
  case "$1" in
    GMI_API_KEY)      echo "console.gmicloud.ai - Identitaetsbilder, Video und Stimmen" ;;
    OPENAI_API_KEY)   echo "platform.openai.com/api-keys - Portraits und Ersatzstimme" ;;
    B2_KEY_ID)        echo "secure.backblaze.com/app_keys.htm - keyID" ;;
    B2_APP_KEY)       echo "dieselbe Seite - applicationKey" ;;
    GENERATE_API_KEY) echo "eigener Besitzerschluessel; hebt alle Limits auf" ;;
    *) return 1 ;;
  esac
}
ALLE=(GMI_API_KEY OPENAI_API_KEY B2_KEY_ID B2_APP_KEY GENERATE_API_KEY)

setzen() {
  local name="$1" wert=""
  printf '%s\n  (%s): ' "$name" "$(hinweis "$name")"
  IFS= read -rs wert; echo
  [ -z "$wert" ] && { echo "  uebersprungen"; return; }
  printf '%s' "$wert" | ssh "$SERVER" "sudo sh -c \"umask 077; cd /opt/loomina && v=\\\$(cat) && { grep -v '^$name=' .env || true; printf '%s=%s\n' '$name' \\\"\\\$v\\\"; } > .env.neu && mv .env.neu .env\"" \
    && echo "  gesetzt"
  wert=""
}

[ "$#" -gt 0 ] && namen=("$@") || namen=("${ALLE[@]}")
for name in "${namen[@]}"; do hinweis "$name" >/dev/null || { echo "Unbekannter Name: $name" >&2; exit 1; }; done
for name in "${namen[@]}"; do setzen "$name"; done

ssh "$SERVER" "cd /opt/loomina && sudo docker compose up -d --force-recreate loomina >/dev/null 2>&1 && sleep 6 && echo 'Loomina neu gestartet.' && curl -s https://loomina.schwabengruber.cloud/capabilities | head -c 120"
echo
