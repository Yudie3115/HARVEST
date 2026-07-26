"""Public flow exports, loaded lazily so API-only runtimes do not require Prefect."""
from importlib import import_module

_EXPORTS = {
    "discover_content": ("src.flows.discovery", "discover_content"),
    "discover_all_sites": ("src.flows.discovery", "discover_all_sites"),
    "process_document": ("src.flows.processing", "process_document"),
    "process_documents_batch": ("src.flows.processing", "process_documents_batch"),
    "main_scraper_flow": ("src.flows.orchestration", "main_scraper_flow"),
    "incremental_update_flow": ("src.flows.orchestration", "incremental_update_flow"),
    "reprocess_failed_flow": ("src.flows.orchestration", "reprocess_failed_flow"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
