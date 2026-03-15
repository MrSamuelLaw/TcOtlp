"""Generate TwinCAT .TcTLEO enum files from proto enum definitions."""

import uuid


def _new_guid() -> str:
    return f"{{{uuid.uuid4()}}}"


def _build_declaration(enum_st_name: str, values: list[dict]) -> str:
    """Build the ST declaration block (tab-indented, inside CDATA)."""
    lines = [
        "{attribute 'qualified_only'}",
        "{attribute 'strict'}",
        "{attribute 'to_string'}",
        f"TYPE {enum_st_name} :",
        "(",
    ]

    for i, val in enumerate(values):
        name = val["name"]
        number = val["number"]
        assignment = f"\t{name} := {number}"
        if i < len(values) - 1:
            assignment += ","
        lines.append(assignment)

    lines.append(");")
    lines.append("END_TYPE")
    lines.append("")  # trailing newline before closing CDATA

    return "\n".join(lines) + "\n"


def _build_text_list_entry(text_id: str, text_default: str, indent: str) -> str:
    """Build a single <o> entry for the XmlArchive TextList."""
    lines = [
        f"{indent}<o>",
        f'{indent}  <v n="TextID">"{text_id}"</v>',
        f'{indent}  <v n="TextDefault">"{text_default}"</v>',
        f'{indent}  <l n="LanguageTexts" t="ArrayList" />',
        f"{indent}</o>",
    ]
    return "\n".join(lines)


def generate_enum(enum_node: dict, enum_st_name: str) -> str:
    """Generate a TcTLEO XML string for a proto enum.

    Args:
        enum_node: AST dict with keys "_type", "name", "elements".
                   Elements can be EnumValue or Comment dicts.
        enum_st_name: The Structured Text enum name (e.g. "E_OtlpSeverityNumber").

    Returns:
        Complete XML string for the .TcTLEO file.
    """
    # Filter to only EnumValue elements
    values = [e for e in enum_node["elements"] if e.get("_type") == "EnumValue"]

    # Generate GUIDs
    enum_id = _new_guid()
    guid_init = _new_guid()
    guid_reinit = _new_guid()
    guid_exit = _new_guid()

    # Build declaration
    declaration = _build_declaration(enum_st_name, values)

    # Build TextList entries
    entry_indent = "            "  # 12 spaces (matches hand-written pattern)
    text_entries = []
    for i, val in enumerate(values):
        name = val["name"]
        number = val["number"]
        # First value always shows its number; subsequent values show number
        # only if it differs from auto-increment (i.e., number != i).
        # But the hand-written examples show "" for auto-increment values.
        if number != i:
            text_default = str(number)
        else:
            text_default = str(number) if i == 0 else ""
        text_entries.append(
            _build_text_list_entry(name, text_default, entry_indent)
        )

    # Trailing empty entry (always present)
    text_entries.append(_build_text_list_entry("", "", entry_indent))

    text_list_body = "\n".join(text_entries)

    xml = f"""\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <EnumerationTextList Name="{enum_st_name}" Id="{enum_id}">
    <Declaration><![CDATA[{declaration}]]></Declaration>
    <XmlArchive>
      <Data>
        <o xml:space="preserve" t="TextListEnumerationTextListObject">
          <l n="TextList" t="ArrayList" cet="TextListRow">
{text_list_body}
          </l>
          <l n="Languages" t="ArrayList" />
          <v n="GuidInit">{guid_init}</v>
          <v n="GuidReInit">{guid_reinit}</v>
          <v n="GuidExitX">{guid_exit}</v>
        </o>
      </Data>
      <TypeList>
        <Type n="ArrayList">System.Collections.ArrayList</Type>
        <Type n="Guid">System.Guid</Type>
        <Type n="String">System.String</Type>
        <Type n="TextListEnumerationTextListObject">{{4b60233c-f940-4beb-b331-82133b520151}}</Type>
        <Type n="TextListRow">{{53da1be7-ad25-47c3-b0e8-e26286dad2e0}}</Type>
      </TypeList>
    </XmlArchive>
  </EnumerationTextList>
</TcPlcObject>"""

    return xml
