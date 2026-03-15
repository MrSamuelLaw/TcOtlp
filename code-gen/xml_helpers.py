"""XML template helpers for generating TwinCAT project files.

Provides GUID generation, XML boilerplate, and CDATA wrapping
for .TcPOU, .TcTLEO, and .TcIO file generation.
"""

import uuid


def generate_guid() -> str:
    """Return a new random GUID in TwinCAT format.

    Format: {xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx} (lowercase hex, with braces).
    """
    return f"{{{uuid.uuid4()}}}"


def xml_header() -> str:
    """Return the standard XML declaration."""
    return '<?xml version="1.0" encoding="utf-8"?>'


def tcplc_object_start() -> str:
    """Return the opening TcPlcObject tag."""
    return '<TcPlcObject Version="1.1.0.1">'


def tcplc_object_end() -> str:
    """Return the closing TcPlcObject tag."""
    return '</TcPlcObject>'


def cdata_wrap(text: str) -> str:
    """Wrap text in a CDATA section."""
    return f"<![CDATA[{text}]]>"
