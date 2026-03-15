"""Load and navigate the proto_ast.json file.

Provides helpers to load the AST, find elements by type, resolve
cross-file type references, and extract package names.
"""

import json

# Mapping from proto package names to file keys in the AST dict.
# Uses backslash path separators to match the proto_ast.json keys.
_PACKAGE_TO_FILE_KEY: dict[str, str] = {
    "opentelemetry.proto.collector.logs.v1": "opentelemetry\\proto\\collector\\logs\\v1\\logs_service.proto",
    "opentelemetry.proto.collector.metrics.v1": "opentelemetry\\proto\\collector\\metrics\\v1\\metrics_service.proto",
    "opentelemetry.proto.collector.profiles.v1development": "opentelemetry\\proto\\collector\\profiles\\v1development\\profiles_service.proto",
    "opentelemetry.proto.collector.trace.v1": "opentelemetry\\proto\\collector\\trace\\v1\\trace_service.proto",
    "opentelemetry.proto.common.v1": "opentelemetry\\proto\\common\\v1\\common.proto",
    "opentelemetry.proto.logs.v1": "opentelemetry\\proto\\logs\\v1\\logs.proto",
    "opentelemetry.proto.metrics.v1": "opentelemetry\\proto\\metrics\\v1\\metrics.proto",
    "opentelemetry.proto.profiles.v1development": "opentelemetry\\proto\\profiles\\v1development\\profiles.proto",
    "opentelemetry.proto.resource.v1": "opentelemetry\\proto\\resource\\v1\\resource.proto",
    "opentelemetry.proto.trace.v1": "opentelemetry\\proto\\trace\\v1\\trace.proto",
}


def load_ast(path: str) -> dict:
    """Load the proto_ast.json file and return the parsed dict."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_elements(ast: dict, file_key: str, element_type: str) -> list[dict]:
    """Return all elements of a given _type from a file's file_elements.

    Filters out comments, options, imports, and other non-matching elements.

    Args:
        ast: The full AST dict (from load_ast).
        file_key: The key in the AST dict (e.g. "opentelemetry\\proto\\logs\\v1\\logs.proto").
        element_type: The _type to filter for (e.g. "Message", "Enum").

    Returns:
        A list of element dicts matching the given type.
    """
    file_data = ast[file_key]
    return [
        elem
        for elem in file_data["file_elements"]
        if elem.get("_type") == element_type
    ]


def resolve_type_ref(type_ref: str, current_package: str) -> tuple[str, str]:
    """Resolve a proto type reference to a (file_key, type_name) tuple.

    For fully-qualified references like "opentelemetry.proto.common.v1.AnyValue",
    splits off the last component as the type name and looks up the package.

    For simple names like "SeverityNumber", uses the current_package to resolve.

    Args:
        type_ref: The type reference string from the AST.
        current_package: The package of the file containing the reference.

    Returns:
        A tuple of (file_key, type_name).

    Raises:
        KeyError: If the package cannot be resolved to a file key.
    """
    if "." in type_ref:
        # Fully qualified: split into package + type name
        parts = type_ref.rsplit(".", 1)
        package = parts[0]
        type_name = parts[1]
    else:
        # Simple name: resolve within current package
        package = current_package
        type_name = type_ref

    file_key = _PACKAGE_TO_FILE_KEY[package]
    return (file_key, type_name)


def get_package(ast: dict, file_key: str) -> str:
    """Extract the package name from a file's elements.

    Args:
        ast: The full AST dict.
        file_key: The key in the AST dict.

    Returns:
        The package name string.

    Raises:
        ValueError: If no Package element is found.
    """
    for elem in ast[file_key]["file_elements"]:
        if elem.get("_type") == "Package":
            return elem["name"]
    raise ValueError(f"No Package element found in {file_key}")
