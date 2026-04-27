#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-$(dirname "$SOURCE_DIR")/AIH-Contexture}"
DRY_RUN="${DRY_RUN:-0}"
SKIP_PIP_INSTALL="${SKIP_PIP_INSTALL:-0}"

if [[ ! -f "$SOURCE_DIR/pyproject.toml" ]]; then
  echo "[upgrade] Source directory is missing pyproject.toml: $SOURCE_DIR" >&2
  exit 1
fi

if ! grep -q 'version = "0.3.0"' "$SOURCE_DIR/pyproject.toml"; then
  echo "[upgrade] Source directory does not look like AIH-Contexture 0.3.0: $SOURCE_DIR" >&2
  exit 1
fi

if [[ ! -d "$TARGET_DIR" || ! -f "$TARGET_DIR/pyproject.toml" ]]; then
  echo "[upgrade] Target directory is invalid or missing pyproject.toml: $TARGET_DIR" >&2
  exit 1
fi

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_ROOT="$(dirname "$TARGET_DIR")/AIH-Contexture-backup-before-0.3-$TIMESTAMP"

DIR_ITEMS=(aih_contexture scripts static tests docs .github)
FILE_ITEMS=(
  pyproject.toml poetry.lock requirements.txt README.md CHANGELOG.md UPDATE_0.3.md LICENSE MODEL_LICENSE
  DOCUMENTATION.md CLA.md contexture_app.py install.bat install.sh install.command start.bat start.sh start.command
  .pre-commit-config.yaml .gitignore pytest.ini
)

log() { echo "[upgrade] $*"; }

log "Source: $SOURCE_DIR"
log "Target: $TARGET_DIR"
log "Backup: $BACKUP_ROOT"
log "Protected in target: .venv venv .git .claude .env configs output uploads conversion_results debug_data temp"

if [[ "$DRY_RUN" != "1" ]]; then
  mkdir -p "$BACKUP_ROOT"
else
  log "DRY_RUN=1; no files will be changed."
fi

backup_item() {
  local rel="$1"
  if [[ -e "$TARGET_DIR/$rel" ]]; then
    if [[ "$DRY_RUN" == "1" ]]; then
      log "Would backup: $rel"
    else
      mkdir -p "$(dirname "$BACKUP_ROOT/$rel")"
      cp -a "$TARGET_DIR/$rel" "$BACKUP_ROOT/$rel"
    fi
  fi
}

replace_dir() {
  local rel="$1"
  if [[ ! -d "$SOURCE_DIR/$rel" ]]; then
    log "Skip missing source directory: $rel"
    return
  fi
  backup_item "$rel"
  if [[ "$DRY_RUN" == "1" ]]; then
    log "Would replace directory: $rel"
    return
  fi
  rm -rf "$TARGET_DIR/$rel"
  cp -a "$SOURCE_DIR/$rel" "$TARGET_DIR/$rel"
  log "Replaced directory: $rel"
}

replace_file() {
  local rel="$1"
  if [[ ! -f "$SOURCE_DIR/$rel" ]]; then
    log "Skip missing source file: $rel"
    return
  fi
  backup_item "$rel"
  if [[ "$DRY_RUN" == "1" ]]; then
    log "Would replace file: $rel"
    return
  fi
  mkdir -p "$(dirname "$TARGET_DIR/$rel")"
  cp -f "$SOURCE_DIR/$rel" "$TARGET_DIR/$rel"
  log "Replaced file: $rel"
}

for item in "${DIR_ITEMS[@]}"; do replace_dir "$item"; done
for item in "${FILE_ITEMS[@]}"; do replace_file "$item"; done

if [[ -d "$SOURCE_DIR/configs" ]]; then
  while IFS= read -r -d '' file; do
    rel="${file#$SOURCE_DIR/configs/}"
    if [[ ! -e "$TARGET_DIR/configs/$rel" ]]; then
      if [[ "$DRY_RUN" == "1" ]]; then
        log "Would add missing config example: configs/$rel"
      else
        mkdir -p "$(dirname "$TARGET_DIR/configs/$rel")"
        cp -f "$file" "$TARGET_DIR/configs/$rel"
        log "Added missing config example: configs/$rel"
      fi
    fi
  done < <(find "$SOURCE_DIR/configs" -type f -print0)
fi

if [[ "$SKIP_PIP_INSTALL" != "1" ]]; then
  if [[ -x "$TARGET_DIR/.venv/Scripts/python.exe" ]]; then
    if [[ "$DRY_RUN" == "1" ]]; then
      log "Would run: $TARGET_DIR/.venv/Scripts/python.exe -m pip install -e $TARGET_DIR --no-deps"
    else
      log "Refreshing editable install without dependencies."
      "$TARGET_DIR/.venv/Scripts/python.exe" -m pip install -e "$TARGET_DIR" --no-deps
    fi
  else
    log "No target .venv found; skip pip install. If needed, activate your old environment and run: python -m pip install -e '$TARGET_DIR' --no-deps"
  fi
fi

log "Upgrade file replacement completed."
if [[ "$DRY_RUN" != "1" ]]; then
  log "Backup saved at: $BACKUP_ROOT"
  log 'Verify with: python -c "import aih_contexture; print(aih_contexture.__file__)"'
  log "Then run: contexture_gui"
fi
