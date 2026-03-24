"""Generate TwinCAT .TcPOU function block files from proto message definitions.

Each proto message becomes:
- An FB_Otlp* function block with VAR declarations, properties, setter methods,
  a SerializeToProtoJson method, and FB_exit for cleanup.
"""

import uuid
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from type_map import proto_type_to_st, bytes_type_for_field, json_method_for_type
from naming import (
    proto_name_to_fb,
    proto_name_to_interface,
    proto_name_to_enum,
    proto_field_to_st,
    proto_field_to_json_key,
)
from loader import resolve_type_ref
from xml_helpers import AUTO_GEN_COMMENT


def _new_guid() -> str:
    return f"{{{uuid.uuid4()}}}"


# Maximum number of elements in a repeated field array
MAX_REPEATED = 100


def _classify_field(field: dict, current_package: str, ast: dict) -> dict:
    """Classify a proto field into its ST representation.

    Returns a dict with:
        - proto_name: original proto field name
        - st_name: Hungarian-prefixed camelCase variable name
        - st_type: Structured Text type
        - json_key: camelCase JSON key
        - kind: 'scalar', 'enum', 'message', 'bytes', 'repeated_scalar',
                'repeated_message'
        - is_repeated: bool
        - message_fb: FB name (for message types)
        - message_itf: interface name (for message types)
        - enum_name: enum ST name (for enum types)
        - json_method: JSON serializer method (for scalars)
    """
    proto_name = field["name"]
    proto_type = field["type"]
    cardinality = field.get("cardinality")
    is_repeated = cardinality == "REPEATED"

    result = {
        "proto_name": proto_name,
        "json_key": proto_field_to_json_key(proto_name),
        "is_repeated": is_repeated,
    }

    # Check if it's a scalar type
    st_type = proto_type_to_st(proto_type)

    if proto_type == "bytes":
        st_type = bytes_type_for_field(proto_name)
        result["st_type"] = st_type
        result["st_name"] = proto_field_to_st(proto_name, "ARRAY")
        result["kind"] = "bytes"
        return result

    if st_type is not None:
        # Scalar type
        if is_repeated:
            arr_type = f"ARRAY[0..{MAX_REPEATED - 1}] OF {st_type}"
            result["st_type"] = arr_type
            result["st_name"] = proto_field_to_st(proto_name, "ARRAY")
            result["kind"] = "repeated_scalar"
            result["element_st_type"] = st_type
            result["json_method"] = json_method_for_type(st_type)
        else:
            result["st_type"] = st_type
            result["st_name"] = proto_field_to_st(proto_name, st_type)
            result["kind"] = "scalar"
            result["json_method"] = json_method_for_type(st_type)
        return result

    # Non-scalar: resolve the type reference to determine if enum or message
    try:
        file_key, type_name = resolve_type_ref(proto_type, current_package)
    except KeyError:
        # If we can't resolve, treat as message (best guess)
        file_key = None
        type_name = proto_type.rsplit(".", 1)[-1] if "." in proto_type else proto_type

    # Check if it's an enum in the AST (top-level or nested inside messages)
    is_enum = False
    if file_key and ast:
        from loader import find_elements
        enums = find_elements(ast, file_key, "Enum")
        is_enum = any(e["name"] == type_name for e in enums)
        if not is_enum:
            # Also check enums nested inside messages
            messages = find_elements(ast, file_key, "Message")
            for msg in messages:
                for elem in msg.get("elements", []):
                    if elem is not None and elem.get("_type") == "Enum" and elem.get("name") == type_name:
                        is_enum = True
                        break
                if is_enum:
                    break

    if is_enum:
        enum_st_name = proto_name_to_enum(type_name)
        result["st_type"] = enum_st_name
        result["st_name"] = proto_field_to_st(proto_name, enum_st_name)
        result["kind"] = "enum"
        result["enum_name"] = enum_st_name
        return result

    # AnyValue is a special oneof type — use the interface, not a concrete FB
    if type_name == "AnyValue":
        itf_name = "I_OtlpAnyValue"
        if is_repeated:
            arr_type = f"ARRAY[0..{MAX_REPEATED - 1}] OF POINTER TO {itf_name}"
            result["st_type"] = arr_type
            result["st_name"] = proto_field_to_st(proto_name, "ARRAY")
            result["kind"] = "repeated_message"
            result["message_fb"] = itf_name  # used for __NEW — but AnyValue variants are created externally
            result["message_itf"] = itf_name
            result["count_name"] = proto_field_to_st(proto_name + "_count", "UDINT")
        else:
            ptr_type = f"POINTER TO {itf_name}"
            result["st_type"] = ptr_type
            result["st_name"] = proto_field_to_st(proto_name, ptr_type)
            result["kind"] = "message"
            result["message_fb"] = itf_name
            result["message_itf"] = itf_name
        return result

    # It's a message type
    fb_name = proto_name_to_fb(type_name)
    itf_name = proto_name_to_interface(type_name)

    if is_repeated:
        # repeated message → ARRAY OF POINTER TO interface + count
        arr_type = f"ARRAY[0..{MAX_REPEATED - 1}] OF POINTER TO {fb_name}"
        result["st_type"] = arr_type
        result["st_name"] = proto_field_to_st(proto_name, "ARRAY")
        result["kind"] = "repeated_message"
        result["message_fb"] = fb_name
        result["message_itf"] = itf_name
        result["count_name"] = proto_field_to_st(proto_name + "_count", "UDINT")
    else:
        # Single message → POINTER TO FB
        ptr_type = f"POINTER TO {fb_name}"
        result["st_type"] = ptr_type
        result["st_name"] = proto_field_to_st(proto_name, ptr_type)
        result["kind"] = "message"
        result["message_fb"] = fb_name
        result["message_itf"] = itf_name

    return result


def _build_var_section(fields: list[dict]) -> str:
    """Build the VAR block for the FB declaration."""
    lines = ["VAR"]
    for f in fields:
        if f["kind"] == "repeated_message":
            lines.append(f"\t_{f['st_name']} : {f['st_type']};")
            lines.append(f"\t_{f['count_name']} : UDINT;")
        elif f["kind"] == "repeated_scalar":
            lines.append(f"\t_{f['st_name']} : {f['st_type']};")
            count_name = proto_field_to_st(f["proto_name"] + "_count", "UDINT")
            lines.append(f"\t_{count_name} : UDINT;")
        else:
            lines.append(f"\t_{f['st_name']} : {f['st_type']};")
    if _has_keyvalue_attributes(fields):
        lines.append(f"\t_arrStringAttrValues : ARRAY[0..{MAX_REPEATED - 1}] OF POINTER TO FB_OtlpStringValue;")
        lines.append(f"\t_arrStringAttrInterfaces : ARRAY[0..{MAX_REPEATED - 1}] OF I_OtlpAnyValue;")
        lines.append(f"\t_nStringAttrValuesCount : UDINT;")
    lines.append("END_VAR")
    return "\n".join(lines)


def _build_serialize_to_proto_json_method(fb_name: str, fields: list[dict]) -> str:
    """Build the SerializeToProtoJson method."""
    method_id = _new_guid()

    body_lines = []

    # Determine which temp vars we need
    needs_i = False
    needs_elem = False
    needs_arr = False
    needs_obj = False
    needs_sTemp = False

    for f in fields:
        if f["kind"] in ("repeated_message", "repeated_scalar"):
            needs_i = True
            needs_elem = True
            needs_arr = True
        if f["kind"] == "message":
            needs_obj = True
        if f["kind"] == "bytes":
            needs_sTemp = True

    var_lines = ["VAR"]
    if needs_i:
        var_lines.append("\ti : UDINT;")
    if needs_arr:
        var_lines.append("\tarrNode : SJsonValue;")
    if needs_elem:
        var_lines.append("\telemNode : SJsonValue;")
    if needs_obj:
        var_lines.append("\tobjNode : SJsonValue;")
    if needs_sTemp:
        var_lines.append("\tsTemp : STRING(255);")
    var_lines.append("END_VAR")
    var_decl = "\n".join(var_lines)

    for f in fields:
        json_key = f["json_key"]

        if f["kind"] == "scalar":
            method = f["json_method"]
            st_name = f["st_name"]
            # For enum cast, use TO_DINT
            body_lines.append(f"parser.{method}(node, '{json_key}', THIS^._{st_name});")
            body_lines.append("")

        elif f["kind"] == "enum":
            st_name = f["st_name"]
            body_lines.append(f"parser.AddIntMember(node, '{json_key}', TO_DINT(THIS^._{st_name}));")
            body_lines.append("")

        elif f["kind"] == "bytes":
            # Bytes fields in OTLP/JSON are lowercase hex-encoded strings.
            # We use the helper function F_BytesToHex to convert.
            st_name = f["st_name"]
            st_type = f["st_type"]  # e.g. "ARRAY[0..15] OF BYTE"
            import re
            m = re.search(r"ARRAY\[0\.\.(\d+)\]", st_type)
            if m:
                num_bytes = int(m.group(1)) + 1
                body_lines.append(f"sTemp := F_BytesToHex(pBytes := ADR(THIS^._{st_name}), nLen := {num_bytes});")
                body_lines.append(f"parser.AddStringMember(node, '{json_key}', sTemp);")
            else:
                body_lines.append(f"// TODO: serialize bytes field '{json_key}' (unknown size)")
            body_lines.append("")

        elif f["kind"] == "message":
            st_name = f["st_name"]
            body_lines.append(f"IF THIS^._{st_name} <> 0 THEN")
            body_lines.append(f"\tobjNode := parser.AddObjectMember(node, '{json_key}');")
            body_lines.append(f"\tTHIS^._{st_name}^.SerializeToProtoJson(parser, objNode);")
            body_lines.append("END_IF")
            body_lines.append("")

        elif f["kind"] == "repeated_message":
            st_name = f["st_name"]
            count_name = f["count_name"]
            body_lines.append(f"IF THIS^._{count_name} > 0 THEN")
            body_lines.append(f"\tarrNode := parser.AddArrayMember(node, '{json_key}', 0);")
            body_lines.append(f"\tFOR i := 0 TO THIS^._{count_name} - 1 DO")
            body_lines.append(f"\t\telemNode := parser.PushbackJsonValue(arrNode, '{{}}');")
            body_lines.append(f"\t\tTHIS^._{st_name}[i]^.SerializeToProtoJson(parser, elemNode);")
            body_lines.append(f"\tEND_FOR")
            body_lines.append("END_IF")
            body_lines.append("")

        elif f["kind"] == "repeated_scalar":
            st_name = f["st_name"]
            count_name = proto_field_to_st(f["proto_name"] + "_count", "UDINT")
            element_type = f["element_st_type"]
            # Determine the Pushback method for array elements
            pushback_map = {
                "AddStringMember": "PushbackStringValue",
                "AddBoolMember": "PushbackBoolValue",
                "AddIntMember": "PushbackIntValue",
                "AddUintMember": "PushbackUintValue",
                "AddInt64Member": "PushbackInt64Value",
                "AddUint64Member": "PushbackUint64Value",
                "AddRealMember": "PushbackDoubleValue",
                "AddLrealMember": "PushbackDoubleValue",
            }
            pushback_method = pushback_map.get(f["json_method"], "PushbackIntValue")
            body_lines.append(f"IF THIS^._{count_name} > 0 THEN")
            body_lines.append(f"\tarrNode := parser.AddArrayMember(node, '{json_key}', 0);")
            body_lines.append(f"\tFOR i := 0 TO THIS^._{count_name} - 1 DO")
            body_lines.append(f"\t\tparser.{pushback_method}(arrNode, THIS^._{st_name}[i]);")
            body_lines.append(f"\tEND_FOR")
            body_lines.append("END_IF")
            body_lines.append("")

    body = "\n".join(body_lines).rstrip()

    return f"""\
    <Method Name="SerializeToProtoJson" Id="{method_id}">
      <Declaration><![CDATA[{AUTO_GEN_COMMENT}
METHOD SerializeToProtoJson
VAR_INPUT
\tparser : REFERENCE TO FB_JsonDynDomParser;
\tnode   : SJsonValue;
END_VAR
{var_decl}
]]></Declaration>
      <Implementation>
        <ST><![CDATA[{body}]]></ST>
      </Implementation>
    </Method>"""


def _build_fb_exit(fb_name: str, fields: list[dict]) -> str:
    """Build the FB_exit method for cleanup of dynamic allocations."""
    method_id = _new_guid()

    body_lines = []
    needs_i = False
    has_string_attrs = _has_keyvalue_attributes(fields)
    attributes_field = next(
        (
            f
            for f in fields
            if f["kind"] == "repeated_message"
            and f["message_fb"] == "FB_OtlpKeyValue"
            and f["proto_name"] == "attributes"
        ),
        None,
    )

    if has_string_attrs:
        needs_i = True
        # Clear KeyValue.pValue pointers first so they never reference freed AnyValue
        # objects while this FB is tearing down.
        if attributes_field is not None:
            body_lines.append(f"IF THIS^._{attributes_field['count_name']} > 0 THEN")
            body_lines.append(f"\tFOR i := 0 TO THIS^._{attributes_field['count_name']} - 1 DO")
            body_lines.append(f"\t\tIF THIS^._{attributes_field['st_name']}[i] <> 0 THEN")
            body_lines.append(f"\t\t\tTHIS^._{attributes_field['st_name']}[i]^.pValue := 0;")
            body_lines.append(f"\t\tEND_IF")
            body_lines.append("\tEND_FOR")
            body_lines.append("END_IF")
            body_lines.append("")

        body_lines.append("IF THIS^._nStringAttrValuesCount > 0 THEN")
        body_lines.append("\tFOR i := 0 TO THIS^._nStringAttrValuesCount - 1 DO")
        body_lines.append("\t\tIF THIS^._arrStringAttrValues[i] <> 0 THEN")
        body_lines.append("\t\t\t__DELETE(THIS^._arrStringAttrValues[i]);")
        body_lines.append("\t\tEND_IF")
        body_lines.append("\tEND_FOR")
        body_lines.append("END_IF")
        body_lines.append("")

    for f in fields:
        if f["kind"] == "message":
            st_name = f["st_name"]
            body_lines.append(f"IF THIS^._{st_name} <> 0 THEN")
            body_lines.append(f"\t__DELETE(THIS^._{st_name});")
            body_lines.append("END_IF")
            body_lines.append("")
        elif f["kind"] == "repeated_message":
            needs_i = True
            st_name = f["st_name"]
            count_name = f["count_name"]
            if has_string_attrs and f["proto_name"] == "attributes":
                body_lines.append(f"IF THIS^._{count_name} > 0 THEN")
                body_lines.append(f"\tFOR i := 0 TO THIS^._{count_name} - 1 DO")
                body_lines.append(f"\t\tIF THIS^._{st_name}[i] <> 0 THEN")
                body_lines.append(f"\t\t\tTHIS^._{st_name}[i]^.pValue := 0;")
                body_lines.append(f"\t\t\t__DELETE(THIS^._{st_name}[i]);")
                body_lines.append(f"\t\tEND_IF")
                body_lines.append("\tEND_FOR")
                body_lines.append("END_IF")
                body_lines.append("")
            else:
                body_lines.append(f"IF THIS^._{count_name} > 0 THEN")
                body_lines.append(f"\tFOR i := 0 TO THIS^._{count_name} - 1 DO")
                body_lines.append(f"\t\tIF THIS^._{st_name}[i] <> 0 THEN")
                body_lines.append(f"\t\t\t__DELETE(THIS^._{st_name}[i]);")
                body_lines.append(f"\t\tEND_IF")
                body_lines.append("\tEND_FOR")
                body_lines.append("END_IF")
                body_lines.append("")

    if not body_lines:
        return ""

    var_decl = ""
    if needs_i:
        var_decl = "\nVAR\n\ti : UDINT;\nEND_VAR"

    body = "\n".join(body_lines).rstrip()

    return f"""\
    <Method Name="FB_exit" Id="{method_id}">
      <Declaration><![CDATA[{AUTO_GEN_COMMENT}
METHOD FB_exit : BOOL
VAR_INPUT
\tbInCopyCode : BOOL;
END_VAR{var_decl}
]]></Declaration>
      <Implementation>
        <ST><![CDATA[{body}]]></ST>
      </Implementation>
    </Method>"""


def _build_properties(fields: list[dict]) -> str:
    """Build property Get/Set elements for all fields."""
    props = []
    for f in fields:
        prop_id = _new_guid()
        get_id = _new_guid()
        set_id = _new_guid()
        st_name = f["st_name"]

        if f["kind"] == "repeated_message":
            # For repeated fields, expose the count as a property
            count_name = f["count_name"]
            count_prop_id = _new_guid()
            count_get_id = _new_guid()
            props.append(f"""\
    <Property Name="{count_name}" Id="{count_prop_id}">
      <Declaration><![CDATA[{AUTO_GEN_COMMENT}
PROPERTY {count_name} : UDINT]]></Declaration>
      <Get Name="Get" Id="{count_get_id}">
        <Declaration><![CDATA[VAR
END_VAR
]]></Declaration>
        <Implementation>
          <ST><![CDATA[{count_name} := THIS^._{count_name};]]></ST>
        </Implementation>
      </Get>
    </Property>""")
        elif f["kind"] == "repeated_scalar":
            count_name = proto_field_to_st(f["proto_name"] + "_count", "UDINT")
            count_prop_id = _new_guid()
            count_get_id = _new_guid()
            props.append(f"""\
    <Property Name="{count_name}" Id="{count_prop_id}">
      <Declaration><![CDATA[{AUTO_GEN_COMMENT}
PROPERTY {count_name} : UDINT]]></Declaration>
      <Get Name="Get" Id="{count_get_id}">
        <Declaration><![CDATA[VAR
END_VAR
]]></Declaration>
        <Implementation>
          <ST><![CDATA[{count_name} := THIS^._{count_name};]]></ST>
        </Implementation>
      </Get>
    </Property>""")
        else:
            # Standard property with Get and Set
            if f["kind"] == "message":
                prop_type = f["st_type"]  # POINTER TO FB_*
            else:
                prop_type = f["st_type"]

            props.append(f"""\
    <Property Name="{st_name}" Id="{prop_id}">
      <Declaration><![CDATA[{AUTO_GEN_COMMENT}
PROPERTY {st_name} : {prop_type}]]></Declaration>
      <Get Name="Get" Id="{get_id}">
        <Declaration><![CDATA[VAR
END_VAR
]]></Declaration>
        <Implementation>
          <ST><![CDATA[{st_name} := THIS^._{st_name};]]></ST>
        </Implementation>
      </Get>
      <Set Name="Set" Id="{set_id}">
        <Declaration><![CDATA[VAR
END_VAR
]]></Declaration>
        <Implementation>
          <ST><![CDATA[THIS^._{st_name} := {st_name};]]></ST>
        </Implementation>
      </Set>
    </Property>""")

    return "\n".join(props)


def _build_add_method(f: dict) -> str:
    """Build an Add* method for repeated fields."""
    method_id = _new_guid()

    if f["kind"] == "repeated_message":
        fb_name = f["message_fb"]
        st_name = f["st_name"]
        count_name = f["count_name"]
        # Method name: Add + field name in PascalCase
        parts = f["proto_name"].split("_")
        method_name = "Add" + "".join(p.capitalize() for p in parts)

        return f"""\
    <Method Name="{method_name}" Id="{method_id}">
      <Declaration><![CDATA[{AUTO_GEN_COMMENT}
METHOD {method_name} : POINTER TO {fb_name}
VAR
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[IF THIS^._{count_name} < {MAX_REPEATED} THEN
\t{method_name} := __NEW({fb_name});
\tTHIS^._{st_name}[THIS^._{count_name}] := {method_name};
\tTHIS^._{count_name} := THIS^._{count_name} + 1;
END_IF]]></ST>
      </Implementation>
    </Method>"""

    return ""


def _has_keyvalue_attributes(fields: list[dict]) -> bool:
    """Check if any field is a repeated KeyValue named 'attributes'."""
    return any(
        f["kind"] == "repeated_message"
        and f["message_fb"] == "FB_OtlpKeyValue"
        and f["proto_name"] == "attributes"
        for f in fields
    )


def _build_add_string_attribute_method() -> str:
    """Build AddStringAttribute convenience method for FBs with repeated KeyValue attributes.

    This method manages the full lifecycle of the KeyValue + StringValue pair,
    preventing dangling pointers by owning the FB_OtlpStringValue internally.
    """
    method_id = _new_guid()

    return f"""\
    <Method Name="AddStringAttribute" Id="{method_id}">
      <Declaration><![CDATA[{AUTO_GEN_COMMENT}
METHOD AddStringAttribute
VAR_INPUT
\tsKey : STRING(255);
\tsValue : STRING(255);
END_VAR
VAR
\tpKv : POINTER TO FB_OtlpKeyValue;
\tpStrVal : POINTER TO FB_OtlpStringValue;
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[IF THIS^._nStringAttrValuesCount >= {MAX_REPEATED} THEN
\tRETURN;
END_IF

pStrVal := __NEW(FB_OtlpStringValue);
IF pStrVal = 0 THEN
\tRETURN;
END_IF

pKv := THIS^.AddAttributes();
IF pKv = 0 THEN
\t__DELETE(pStrVal);
\tRETURN;
END_IF

pKv^.sKey := sKey;

pStrVal^.sValue := sValue;
THIS^._arrStringAttrValues[THIS^._nStringAttrValuesCount] := pStrVal;

THIS^._arrStringAttrInterfaces[THIS^._nStringAttrValuesCount] := pStrVal^;
pKv^.pValue := ADR(THIS^._arrStringAttrInterfaces[THIS^._nStringAttrValuesCount]);

THIS^._nStringAttrValuesCount := THIS^._nStringAttrValuesCount + 1;]]></ST>
      </Implementation>
    </Method>"""


def generate_fb(
    message_node: dict,
    fb_name: str,
    interface_name: str,
    current_package: str,
    ast: dict,
) -> str:
    """Generate a TcPOU function block XML string for a proto message.

    Args:
        message_node: AST dict for a Message element.
        fb_name: The ST function block name (e.g. "FB_OtlpLogRecord").
        interface_name: The interface this FB implements (e.g. "I_OtlpLogRecord").
        current_package: The proto package of the file containing this message.
        ast: The full AST dict for cross-file type resolution.

    Returns:
        Complete XML string for the .TcPOU file.
    """
    pou_id = _new_guid()

    # Extract fields (skip Reserved, Comment, None, nested Messages, etc.)
    raw_fields = [
        e for e in message_node["elements"]
        if e is not None and e.get("_type") == "Field"
    ]

    # Classify each field
    fields = [_classify_field(f, current_package, ast) for f in raw_fields]

    # Build declaration
    implements = f" IMPLEMENTS I_OtlpSerializable"
    var_section = _build_var_section(fields)
    declaration = f"{AUTO_GEN_COMMENT}\n{{attribute 'enable_dynamic_creation'}}\nFUNCTION_BLOCK {fb_name}{implements}\n{var_section}\n"

    # Build methods
    methods = []

    # SerializeToProtoJson
    methods.append(_build_serialize_to_proto_json_method(fb_name, fields))

    # FB_exit (only if there are dynamic allocations)
    fb_exit = _build_fb_exit(fb_name, fields)
    if fb_exit:
        methods.append(fb_exit)

    # Add methods for repeated fields
    for f in fields:
        if f["kind"] == "repeated_message":
            methods.append(_build_add_method(f))

    # AddStringAttribute convenience method for FBs with repeated KeyValue attributes
    if _has_keyvalue_attributes(fields):
        methods.append(_build_add_string_attribute_method())

    # Properties
    props = _build_properties(fields)

    methods_xml = "\n".join(methods)

    xml = f"""\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="{fb_name}" Id="{pou_id}" SpecialFunc="None">
    <Declaration><![CDATA[{declaration}]]></Declaration>
    <Implementation>
      <ST><![CDATA[]]></ST>
    </Implementation>
{methods_xml}
{props}
  </POU>
</TcPlcObject>"""

    return xml
