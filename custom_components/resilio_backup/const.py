"""Constants for the Resilio Backup integration."""

DOMAIN = "resilio_backup"

CONF_FOLDER_ID = "folder_id"
CONF_FOLDER_PATH = "folder_path"
CONF_BACKUP_PATH = "backup_path"
CONF_USE_SSL = "use_ssl"
CONF_VERIFY_SSL = "verify_ssl"
CONF_MAX_BACKUPS = "max_backups"
CONF_PRUNE_ENABLED = "prune_enabled"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PORT = 8888
DEFAULT_USE_SSL = False
DEFAULT_VERIFY_SSL = True
DEFAULT_MAX_BACKUPS = 7
DEFAULT_PRUNE_ENABLED = True
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 10

MANUFACTURER = "Resilio"
SERVICE_PRUNE_BACKUPS = "prune_backups"

EVENT_PEER_COUNT_CHANGED = f"{DOMAIN}_peer_count_changed"
EVENT_FILE_COUNT_CHANGED = f"{DOMAIN}_file_count_changed"
EVENT_BACKUPS_PRUNED = f"{DOMAIN}_backups_pruned"

ISSUE_FOLDER_NOT_FOUND = "folder_not_found"
