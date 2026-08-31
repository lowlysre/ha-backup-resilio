"""Constants for the Resilio Backup integration."""

from datetime import timedelta

DOMAIN = "resilio_backup"

CONF_FOLDER_ID = "folder_id"
CONF_FOLDER_PATH = "folder_path"
CONF_BACKUP_PATH = "backup_path"
CONF_USE_SSL = "use_ssl"
CONF_VERIFY_SSL = "verify_ssl"
CONF_MAX_BACKUPS = "max_backups"
CONF_PRUNE_ENABLED = "prune_enabled"

DEFAULT_PORT = 8888
DEFAULT_USE_SSL = False
DEFAULT_VERIFY_SSL = True
DEFAULT_MAX_BACKUPS = 7
DEFAULT_PRUNE_ENABLED = True

SCAN_INTERVAL = timedelta(seconds=60)

MANUFACTURER = "Resilio"
SERVICE_PRUNE_BACKUPS = "prune_backups"
