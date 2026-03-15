"""Naming convention transforms between proto and Structured Text.

Converts proto names (PascalCase messages, snake_case fields) into
TwinCAT naming conventions (FB_Otlp*, I_Otlp*, E_Otlp*, Hungarian-prefixed variables).
"""

# Hungarian prefixes by ST type category
_NUMERIC_TYPES = {"DINT", "UDINT", "LINT", "ULINT", "REAL", "LREAL"}
_STRING_TYPES = {"STRING(255)"}
_BOOL_TYPES = {"BOOL"}


def proto_name_to_fb(name: str) -> str:
    """Convert a proto message name to a function block name.

    Example: LogRecord → FB_OtlpLogRecord
    """
    return f"FB_Otlp{name}"


def proto_name_to_interface(name: str) -> str:
    """Convert a proto message name to an interface name.

    Example: LogRecord → I_OtlpLogRecord
    """
    return f"I_Otlp{name}"


def proto_name_to_enum(name: str) -> str:
    """Convert a proto enum name to a ST enum name.

    Example: SeverityNumber → E_OtlpSeverityNumber
    """
    return f"E_Otlp{name}"


def _snake_to_camel(name: str) -> str:
    """Convert snake_case to camelCase.

    Splits on underscore, capitalizes each part after the first, and joins.
    Single-word names are returned as-is.
    """
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _hungarian_prefix(st_type: str) -> str:
    """Determine the Hungarian notation prefix for a ST type."""
    if st_type in _NUMERIC_TYPES:
        return "n"
    if st_type in _STRING_TYPES:
        return "s"
    if st_type in _BOOL_TYPES:
        return "b"
    if st_type.startswith("E_"):
        return "e"
    if st_type.startswith("ARRAY"):
        return "arr"
    if st_type.startswith("FB_") or st_type.startswith("I_") or st_type.startswith("POINTER"):
        return "p"
    return ""


def proto_field_to_st(name: str, st_type: str) -> str:
    """Convert a proto field name to a Hungarian-prefixed camelCase ST variable.

    The prefix is determined by the ST type:
    - n for numeric (DINT, UDINT, LINT, ULINT, REAL, LREAL)
    - s for STRING
    - b for BOOL
    - e for enum (E_*)
    - p for pointer/FB ref (FB_*, I_*, POINTER*)
    - arr for arrays (ARRAY*)

    Examples:
        time_unix_nano, ULINT     → nTimeUnixNano
        severity_text, STRING(255) → sSeverityText
        severity_number, E_...    → eSeverityNumber
        resource, FB_...          → pResource
        attributes, ARRAY...      → arrAttributes
    """
    prefix = _hungarian_prefix(st_type)
    camel = _snake_to_camel(name)
    if prefix:
        return prefix + camel[0].upper() + camel[1:]
    return camel


def proto_field_to_json_key(name: str) -> str:
    """Convert a proto snake_case field name to a camelCase JSON key.

    Per the OTLP/JSON specification, field names use camelCase.

    Example: time_unix_nano → timeUnixNano
    """
    return _snake_to_camel(name)
