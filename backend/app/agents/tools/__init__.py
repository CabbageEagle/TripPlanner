"""Agent capability tools."""

from .attractions_tool import SearchAttractionsInput, search_attractions_tool
from .hotels_tool import SearchHotelsInput, search_hotels_tool
from .local_events_tool import SearchLocalEventsInput, search_local_events_tool
from .transit_tool import EstimateTransitTimeInput, estimate_transit_time_tool
from .weather_tool import QueryWeatherInput, query_weather_tool

CAPABILITY_TOOLS = {
    "estimate_transit_time_tool": estimate_transit_time_tool,
    "query_weather_tool": query_weather_tool,
    "search_attractions_tool": search_attractions_tool,
    "search_hotels_tool": search_hotels_tool,
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
    "EstimateTransitTimeInput",
    "QueryWeatherInput",
    "SearchAttractionsInput",
    "SearchHotelsInput",
    "SearchLocalEventsInput",
    "estimate_transit_time_tool",
    "query_weather_tool",
    "search_attractions_tool",
    "search_hotels_tool",
    "search_local_events_tool",
]
