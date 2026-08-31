"""Constants for the Resilio Backup integration."""

DOMAIN = "resilio_backup"

CONF_FOLDER_ID = "folder_id"
CONF_FOLDER_PATH = "folder_path"
CONF_BACKUP_PATH = "backup_path"
CONF_USE_SSL = "use_ssl"
CONF_VERIFY_SSL = "verify_ssl"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PORT = 8888
DEFAULT_USE_SSL = False
DEFAULT_VERIFY_SSL = True
DEFAULT_SCAN_INTERVAL = 300
MIN_SCAN_INTERVAL = 10

MANUFACTURER = "Resilio"

EVENT_PEER_COUNT_CHANGED = f"{DOMAIN}_peer_count_changed"
EVENT_FILE_COUNT_CHANGED = f"{DOMAIN}_file_count_changed"

ISSUE_FOLDER_NOT_FOUND = "folder_not_found"
