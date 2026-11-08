import inspect
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentToolRegistry:
    """
    Registry of tools exposed to AI Agent Copilot.
    Validates arguments and coordinates execution directly with Core Services.
    """

    def __init__(self):
        self._tools: Dict[str, Callable[..., Any]] = {}
        self._descriptions: Dict[str, str] = {}
        self._schemas: Dict[str, Dict[str, Any]] = {}

    def register_tool(
        self,
        name: str,
        handler: Callable[..., Any],
        description: str = "",
        parameters_schema: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._tools[name] = handler
        self._descriptions[name] = description or handler.__doc__ or f"Execute {name}"

        if parameters_schema:
            self._schemas[name] = parameters_schema
        else:
            # Auto-infer simple parameters from handler signature
            sig = inspect.signature(handler)
            properties: Dict[str, Any] = {}
            required: List[str] = []
            for param_name, param in sig.parameters.items():
                if param_name in ("self", "cls"):
                    continue
                param_type = "string"
                if param.annotation == int:
                    param_type = "integer"
                elif param.annotation == float:
                    param_type = "number"
                elif param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation in (dict, Dict):
                    param_type = "object"
                elif param.annotation in (list, List):
                    param_type = "array"

                properties[param_name] = {"type": param_type}
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)

            self._schemas[name] = {
                "type": "object",
                "properties": properties,
                "required": required,
            }

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' is not registered.")
        handler = self._tools[name]
        return handler(**args)

    def safe_execute_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            res = self.execute_tool(name, args)
            return {"success": True, "result": res}
        except Exception as e:
            logger.error("Error executing tool %s: %s", name, e, exc_info=True)
            return {"success": False, "error": str(e)}

    def get_tools_schema(self) -> List[Dict[str, Any]]:
        schemas: List[Dict[str, Any]] = []
        for name, params in self._schemas.items():
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": self._descriptions.get(name, ""),
                    "parameters": params,
                },
            })
        return schemas
