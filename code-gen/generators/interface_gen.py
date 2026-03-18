"""Generate TwinCAT .TcIO interface files from proto message definitions."""

import uuid


def _new_guid() -> str:
    return f"{{{uuid.uuid4()}}}"


def generate_serializable_interface() -> str:
    """Generate the base I_OtlpSerializable interface.

    This interface is implemented by every generated FB, enabling
    recursive serialization through the tree.
    """
    itf_id = _new_guid()
    method_id = _new_guid()
    parser_id = _new_guid()
    node_id = _new_guid()

    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <Itf Name="I_OtlpSerializable" Id="{itf_id}">
    <Declaration><![CDATA[(* AUTO GENERATED CODE, DO NOT MODIFY THIS FILE DIRECTLY *)
INTERFACE I_OtlpSerializable
]]></Declaration>
    <Method Name="SerializeToProtoJson" Id="{method_id}">
      <Declaration><![CDATA[METHOD SerializeToProtoJson
VAR_INPUT
\tparser : REFERENCE TO FB_JsonDynDomParser;
\tnode   : SJsonValue;
END_VAR
]]></Declaration>
    </Method>
  </Itf>
</TcPlcObject>"""


def generate_interface(
    interface_name: str,
    properties: list[dict],
    extends: list[str] | None = None,
) -> str:
    """Generate a TcIO interface XML string.

    Args:
        interface_name: The ST interface name (e.g. "I_OtlpLogRecord").
        properties: List of property dicts with keys:
            - name: property name (e.g. "eSeverityNumber")
            - type: ST type (e.g. "E_OtlpSeverityNumber")
            - has_set: whether to include a Set accessor (default False)
        extends: List of interface names this interface extends (e.g. ["I_OtlpSerializable"]).

    Returns:
        Complete XML string for the .TcIO file.
    """
    itf_id = _new_guid()

    # Build EXTENDS clause
    if extends:
        extends_clause = f" EXTENDS {', '.join(extends)}"
    else:
        extends_clause = ""

    declaration = f"(* AUTO GENERATED CODE, DO NOT MODIFY THIS FILE DIRECTLY *)\nINTERFACE {interface_name}{extends_clause}\n"

    # Build property elements
    prop_elements = []
    for prop in properties:
        prop_id = _new_guid()
        get_id = _new_guid()
        prop_name = prop["name"]
        prop_type = prop["type"]

        prop_xml = f"""\
    <Property Name="{prop_name}" Id="{prop_id}">
      <Declaration><![CDATA[PROPERTY {prop_name} : {prop_type}]]></Declaration>
      <Get Name="Get" Id="{get_id}">
        <Declaration><![CDATA[]]></Declaration>
      </Get>"""

        if prop.get("has_set"):
            set_id = _new_guid()
            prop_xml += f"""
      <Set Name="Set" Id="{set_id}">
        <Declaration><![CDATA[]]></Declaration>
      </Set>"""

        prop_xml += """
    </Property>"""
        prop_elements.append(prop_xml)

    props_xml = "\n".join(prop_elements)

    xml = f"""\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <Itf Name="{interface_name}" Id="{itf_id}">
    <Declaration><![CDATA[{declaration}]]></Declaration>
{props_xml}
  </Itf>
</TcPlcObject>"""

    return xml
