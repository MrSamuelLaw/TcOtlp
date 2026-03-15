"""Special handling for the AnyValue oneof → variant FBs.

AnyValue is recursive and uses proto oneof. This generates:
- E_OtlpAnyValueType discriminator enum
- I_OtlpAnyValue interface (extends I_OtlpSerializable)
- Separate FB per variant, each implementing I_OtlpAnyValue:
    FB_OtlpStringValue, FB_OtlpBoolValue, FB_OtlpIntValue,
    FB_OtlpDoubleValue, FB_OtlpBytesValue, FB_OtlpArrayValue,
    FB_OtlpKeyValueList (as AnyValue variant)
"""

import uuid

from .enum_gen import generate_enum
from .interface_gen import generate_interface


def _new_guid() -> str:
    return f"{{{uuid.uuid4()}}}"


# Mapping from oneof field name to variant info
_VARIANT_MAP = {
    "string_value": {
        "fb_name": "FB_OtlpStringValue",
        "enum_value": "STRING_VALUE",
        "st_type": "STRING(255)",
        "json_key": "stringValue",
        "json_method": "AddStringMember",
        "var_name": "sValue",
    },
    "bool_value": {
        "fb_name": "FB_OtlpBoolValue",
        "enum_value": "BOOL_VALUE",
        "st_type": "BOOL",
        "json_key": "boolValue",
        "json_method": "AddBoolMember",
        "var_name": "bValue",
    },
    "int_value": {
        "fb_name": "FB_OtlpIntValue",
        "enum_value": "INT_VALUE",
        "st_type": "LINT",
        "json_key": "intValue",
        "json_method": "AddInt64Member",
        "var_name": "nValue",
    },
    "double_value": {
        "fb_name": "FB_OtlpDoubleValue",
        "enum_value": "DOUBLE_VALUE",
        "st_type": "LREAL",
        "json_key": "doubleValue",
        "json_method": "AddLrealMember",
        "var_name": "fValue",
    },
    "bytes_value": {
        "fb_name": "FB_OtlpBytesValue",
        "enum_value": "BYTES_VALUE",
        "st_type": "ARRAY[0..255] OF BYTE",
        "json_key": "bytesValue",
        "json_method": None,  # needs base64 encoding
        "var_name": "arrValue",
    },
    "array_value": {
        "fb_name": "FB_OtlpArrayValue",
        "enum_value": "ARRAY_VALUE",
        "st_type": None,  # special: holds ARRAY OF I_OtlpAnyValue
        "json_key": "arrayValue",
        "json_method": None,  # recursive
        "var_name": None,
    },
    "kvlist_value": {
        "fb_name": "FB_OtlpKvlistValue",
        "enum_value": "KVLIST_VALUE",
        "st_type": None,  # special: holds ARRAY OF FB_OtlpKeyValue
        "json_key": "kvlistValue",
        "json_method": None,  # recursive
        "var_name": None,
    },
}

# Skip the profiling-only field
_SKIP_FIELDS = {"string_value_strindex"}

MAX_REPEATED = 100


def generate_anyvalue_enum() -> tuple[str, str]:
    """Generate E_OtlpAnyValueType discriminator enum.

    Returns:
        (filename, xml_content) tuple.
    """
    enum_node = {
        "_type": "Enum",
        "name": "AnyValueType",
        "elements": [
            {"_type": "EnumValue", "name": "NONE", "number": 0},
            {"_type": "EnumValue", "name": "STRING_VALUE", "number": 1},
            {"_type": "EnumValue", "name": "BOOL_VALUE", "number": 2},
            {"_type": "EnumValue", "name": "INT_VALUE", "number": 3},
            {"_type": "EnumValue", "name": "DOUBLE_VALUE", "number": 4},
            {"_type": "EnumValue", "name": "ARRAY_VALUE", "number": 5},
            {"_type": "EnumValue", "name": "KVLIST_VALUE", "number": 6},
            {"_type": "EnumValue", "name": "BYTES_VALUE", "number": 7},
        ],
    }
    xml = generate_enum(enum_node, "E_OtlpAnyValueType")
    return ("E_OtlpAnyValueType.TcTLEO", xml)


def generate_anyvalue_interface() -> tuple[str, str]:
    """Generate I_OtlpAnyValue interface extending I_OtlpSerializable.

    Returns:
        (filename, xml_content) tuple.
    """
    props = [
        {"name": "eValueType", "type": "E_OtlpAnyValueType"},
    ]
    xml = generate_interface(
        "I_OtlpAnyValue",
        properties=props,
        extends=["I_OtlpSerializable"],
    )
    return ("I_OtlpAnyValue.TcIO", xml)


def _generate_simple_variant(variant: dict) -> str:
    """Generate a simple variant FB (string, bool, int, double, bytes)."""
    fb_name = variant["fb_name"]
    st_type = variant["st_type"]
    var_name = variant["var_name"]
    json_key = variant["json_key"]
    json_method = variant["json_method"]
    enum_value = variant["enum_value"]

    pou_id = _new_guid()
    serialize_id = _new_guid()
    prop_value_id = _new_guid()
    prop_value_get_id = _new_guid()
    prop_value_set_id = _new_guid()
    prop_type_id = _new_guid()
    prop_type_get_id = _new_guid()

    # Serialize body
    if json_method:
        serialize_body = f"parser.{json_method}(node, '{json_key}', THIS^._{var_name});"
    else:
        serialize_body = f"// TODO: serialize bytes field '{json_key}' (base64 encoding)"

    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="{fb_name}" Id="{pou_id}" SpecialFunc="None">
    <Declaration><![CDATA[{{attribute 'enable_dynamic_creation'}}
FUNCTION_BLOCK {fb_name} IMPLEMENTS I_OtlpAnyValue
VAR
\t_{var_name} : {st_type};
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[]]></ST>
    </Implementation>
    <Method Name="SerializeToProtoJson" Id="{serialize_id}">
      <Declaration><![CDATA[METHOD SerializeToProtoJson
VAR_INPUT
\tparser : REFERENCE TO FB_JsonDynDomParser;
\tnode   : SJsonValue;
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[{serialize_body}]]></ST>
      </Implementation>
    </Method>
    <Property Name="eValueType" Id="{prop_type_id}">
      <Declaration><![CDATA[PROPERTY eValueType : E_OtlpAnyValueType]]></Declaration>
      <Get Name="Get" Id="{prop_type_get_id}">
        <Declaration><![CDATA[VAR
END_VAR
]]></Declaration>
        <Implementation>
          <ST><![CDATA[eValueType := E_OtlpAnyValueType.{enum_value};]]></ST>
        </Implementation>
      </Get>
    </Property>
    <Property Name="{var_name}" Id="{prop_value_id}">
      <Declaration><![CDATA[PROPERTY {var_name} : {st_type}]]></Declaration>
      <Get Name="Get" Id="{prop_value_get_id}">
        <Declaration><![CDATA[VAR
END_VAR
]]></Declaration>
        <Implementation>
          <ST><![CDATA[{var_name} := THIS^._{var_name};]]></ST>
        </Implementation>
      </Get>
      <Set Name="Set" Id="{prop_value_set_id}">
        <Declaration><![CDATA[VAR
END_VAR
]]></Declaration>
        <Implementation>
          <ST><![CDATA[THIS^._{var_name} := {var_name};]]></ST>
        </Implementation>
      </Set>
    </Property>
  </POU>
</TcPlcObject>"""


def _generate_array_value() -> str:
    """Generate FB_OtlpArrayValue — holds ARRAY OF POINTER TO I_OtlpAnyValue."""
    fb_name = "FB_OtlpArrayValue"
    pou_id = _new_guid()
    serialize_id = _new_guid()
    fb_exit_id = _new_guid()
    add_method_id = _new_guid()
    prop_type_id = _new_guid()
    prop_type_get_id = _new_guid()
    prop_count_id = _new_guid()
    prop_count_get_id = _new_guid()

    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="{fb_name}" Id="{pou_id}" SpecialFunc="None">
    <Declaration><![CDATA[{{attribute 'enable_dynamic_creation'}}
FUNCTION_BLOCK {fb_name} IMPLEMENTS I_OtlpAnyValue
VAR
\t_arrValues : ARRAY[0..{MAX_REPEATED - 1}] OF POINTER TO I_OtlpAnyValue;
\t_nValuesCount : UDINT;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[]]></ST>
    </Implementation>
    <Method Name="SerializeToProtoJson" Id="{serialize_id}">
      <Declaration><![CDATA[METHOD SerializeToProtoJson
VAR_INPUT
\tparser : REFERENCE TO FB_JsonDynDomParser;
\tnode   : SJsonValue;
END_VAR
VAR
\tvaluesNode : SJsonValue;
\tarrNode : SJsonValue;
\telemNode : SJsonValue;
\ti : UDINT;
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[valuesNode := parser.AddObjectMember(node, 'arrayValue');
IF THIS^._nValuesCount > 0 THEN
\tarrNode := parser.AddArrayMember(valuesNode, 'values', 0);
\tFOR i := 0 TO THIS^._nValuesCount - 1 DO
\t\telemNode := parser.PushbackJsonValue(arrNode, '{{}}');
\t\tTHIS^._arrValues[i]^^.SerializeToProtoJson(parser, elemNode);
\tEND_FOR
END_IF]]></ST>
      </Implementation>
    </Method>
    <Method Name="FB_exit" Id="{fb_exit_id}">
      <Declaration><![CDATA[METHOD FB_exit : BOOL
VAR_INPUT
\tbInCopyCode : BOOL;
END_VAR
VAR
\ti : UDINT;
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[FOR i := 0 TO THIS^._nValuesCount - 1 DO
\tIF THIS^._arrValues[i] <> 0 THEN
\t\t__DELETE(THIS^._arrValues[i]);
\tEND_IF
END_FOR]]></ST>
      </Implementation>
    </Method>
    <Method Name="AddValue" Id="{add_method_id}">
      <Declaration><![CDATA[METHOD AddValue
VAR_INPUT
\tpValue : POINTER TO I_OtlpAnyValue;
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[IF THIS^._nValuesCount < {MAX_REPEATED} AND pValue <> 0 THEN
\tTHIS^._arrValues[THIS^._nValuesCount] := pValue;
\tTHIS^._nValuesCount := THIS^._nValuesCount + 1;
END_IF]]></ST>
      </Implementation>
    </Method>
    <Property Name="eValueType" Id="{prop_type_id}">
      <Declaration><![CDATA[PROPERTY eValueType : E_OtlpAnyValueType]]></Declaration>
      <Get Name="Get" Id="{prop_type_get_id}">
        <Declaration><![CDATA[VAR
END_VAR
]]></Declaration>
        <Implementation>
          <ST><![CDATA[eValueType := E_OtlpAnyValueType.ARRAY_VALUE;]]></ST>
        </Implementation>
      </Get>
    </Property>
    <Property Name="nValuesCount" Id="{prop_count_id}">
      <Declaration><![CDATA[PROPERTY nValuesCount : UDINT]]></Declaration>
      <Get Name="Get" Id="{prop_count_get_id}">
        <Declaration><![CDATA[VAR
END_VAR
]]></Declaration>
        <Implementation>
          <ST><![CDATA[nValuesCount := THIS^._nValuesCount;]]></ST>
        </Implementation>
      </Get>
    </Property>
  </POU>
</TcPlcObject>"""


def _generate_kvlist_value() -> str:
    """Generate FB_OtlpKvlistValue — holds ARRAY OF POINTER TO FB_OtlpKeyValue."""
    fb_name = "FB_OtlpKvlistValue"
    pou_id = _new_guid()
    serialize_id = _new_guid()
    fb_exit_id = _new_guid()
    add_method_id = _new_guid()
    prop_type_id = _new_guid()
    prop_type_get_id = _new_guid()
    prop_count_id = _new_guid()
    prop_count_get_id = _new_guid()

    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="{fb_name}" Id="{pou_id}" SpecialFunc="None">
    <Declaration><![CDATA[{{attribute 'enable_dynamic_creation'}}
FUNCTION_BLOCK {fb_name} IMPLEMENTS I_OtlpAnyValue
VAR
\t_arrValues : ARRAY[0..{MAX_REPEATED - 1}] OF POINTER TO FB_OtlpKeyValue;
\t_nValuesCount : UDINT;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[]]></ST>
    </Implementation>
    <Method Name="SerializeToProtoJson" Id="{serialize_id}">
      <Declaration><![CDATA[METHOD SerializeToProtoJson
VAR_INPUT
\tparser : REFERENCE TO FB_JsonDynDomParser;
\tnode   : SJsonValue;
END_VAR
VAR
\tkvlistNode : SJsonValue;
\tarrNode : SJsonValue;
\telemNode : SJsonValue;
\ti : UDINT;
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[kvlistNode := parser.AddObjectMember(node, 'kvlistValue');
IF THIS^._nValuesCount > 0 THEN
\tarrNode := parser.AddArrayMember(kvlistNode, 'values', 0);
\tFOR i := 0 TO THIS^._nValuesCount - 1 DO
\t\telemNode := parser.PushbackJsonValue(arrNode, '{{}}');
\t\tTHIS^._arrValues[i]^.SerializeToProtoJson(parser, elemNode);
\tEND_FOR
END_IF]]></ST>
      </Implementation>
    </Method>
    <Method Name="FB_exit" Id="{fb_exit_id}">
      <Declaration><![CDATA[METHOD FB_exit : BOOL
VAR_INPUT
\tbInCopyCode : BOOL;
END_VAR
VAR
\ti : UDINT;
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[FOR i := 0 TO THIS^._nValuesCount - 1 DO
\tIF THIS^._arrValues[i] <> 0 THEN
\t\t__DELETE(THIS^._arrValues[i]);
\tEND_IF
END_FOR]]></ST>
      </Implementation>
    </Method>
    <Method Name="AddValue" Id="{add_method_id}">
      <Declaration><![CDATA[METHOD AddValue : POINTER TO FB_OtlpKeyValue
VAR
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[IF THIS^._nValuesCount < {MAX_REPEATED} THEN
\tAddValue := __NEW(FB_OtlpKeyValue);
\tTHIS^._arrValues[THIS^._nValuesCount] := AddValue;
\tTHIS^._nValuesCount := THIS^._nValuesCount + 1;
END_IF]]></ST>
      </Implementation>
    </Method>
    <Property Name="eValueType" Id="{prop_type_id}">
      <Declaration><![CDATA[PROPERTY eValueType : E_OtlpAnyValueType]]></Declaration>
      <Get Name="Get" Id="{prop_type_get_id}">
        <Declaration><![CDATA[VAR
END_VAR
]]></Declaration>
        <Implementation>
          <ST><![CDATA[eValueType := E_OtlpAnyValueType.KVLIST_VALUE;]]></ST>
        </Implementation>
      </Get>
    </Property>
    <Property Name="nValuesCount" Id="{prop_count_id}">
      <Declaration><![CDATA[PROPERTY nValuesCount : UDINT]]></Declaration>
      <Get Name="Get" Id="{prop_count_get_id}">
        <Declaration><![CDATA[VAR
END_VAR
]]></Declaration>
        <Implementation>
          <ST><![CDATA[nValuesCount := THIS^._nValuesCount;]]></ST>
        </Implementation>
      </Get>
    </Property>
  </POU>
</TcPlcObject>"""


def generate_anyvalue_variants() -> list[tuple[str, str]]:
    """Generate all AnyValue variant FBs.

    Returns:
        List of (filename, xml_content) tuples.
    """
    results = []

    for field_name, variant in _VARIANT_MAP.items():
        if field_name in _SKIP_FIELDS:
            continue

        fb_name = variant["fb_name"]

        if field_name == "array_value":
            xml = _generate_array_value()
        elif field_name == "kvlist_value":
            xml = _generate_kvlist_value()
        else:
            xml = _generate_simple_variant(variant)

        results.append((f"{fb_name}.TcPOU", xml))

    return results
