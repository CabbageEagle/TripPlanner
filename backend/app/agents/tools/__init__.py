"""Agent capability tools."""

from .local_events_tool import SearchLocalEventsInput, search_local_events_tool

CAPABILITY_TOOLS = {
    "search_local_events_tool": search_local_events_tool,
}


def get_capability_tool(tool_name: str):
    """Return a registered capability tool by graph-level name."""
    try:
        return CAPABILITY_TOOLS[tool_name]
    except KeyError as exc:
        raise KeyError(f"Capability tool '{tool_name}' is not registered.") from exc

__all__ = [
    "CAPABILITY_TOOLS",
    "get_capability_tool",
    "SearchLocalEventsInput",
    "search_local_events_tool",
]
