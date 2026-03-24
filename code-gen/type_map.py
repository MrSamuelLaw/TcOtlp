"""Proto scalar type to Structured Text type mapping.

Maps protobuf scalar types to their TwinCAT Structured Text equivalents,
and provides helpers for JSON serialization method selection.
"""

PROTO_TO_ST: dict[str, str] = {
    "string": "STRING(255)",
    "bool": "BOOL",
    "int32": "DINT",
    "sint32": "DINT",
    "sfixed32": "DINT",
    "uint32": "UDINT",
    "fixed32": "UDINT",
    "int64": "LINT",
    "sint64": "LINT",
    "sfixed64": "LINT",
    "uint64": "ULINT",
    "fixed64": "ULINT",
    "float": "REAL",
    "double": "LREAL",
    "bytes": "ARRAY[0..255] OF BYTE",
}

BYTES_FIELD_SIZES: dict[str, int] = {
    "trace_id": 16,
    "span_id": 8,
    "parent_span_id": 8,
}

ST_TO_JSON_METHOD: dict[str, str] = {
    "STRING(255)": "AddStringMember",
    "BOOL": "AddBoolMember",
    "DINT": "AddIntMember",
    "UDINT": "AddUintMember",
    "LINT": "AddInt64Member",
    "ULINT": "AddUint64Member",
    "REAL": "AddRealMember",
    "LREAL": "AddLrealMember",
}


def proto_type_to_st(proto_type: str) -> str | None:
    """Look up the Structured Text type for a proto scalar type.

    Returns None for non-scalar types (messages, enums).
    """
    return PROTO_TO_ST.get(proto_type)


def bytes_type_for_field(field_name: str) -> str:
    """Return the ST byte array type for a specific bytes field.

    Uses known sizes for fields like trace_id (16) and span_id (8),
    falling back to the generic 256-byte array.
    """
    size = BYTES_FIELD_SIZES.get(field_name, 256)
    return f"ARRAY[0..{size - 1}] OF BYTE"


def json_method_for_type(st_type: str) -> str:
    """Return the FB_JsonDynDomParser method name for a given ST type.

    Raises KeyError if the type has no direct JSON method mapping.
    """
    return ST_TO_JSON_METHOD[st_type]
