"""CLI entry point for the TcOtlp code generator.

Generates TwinCAT Structured Text files (.TcPOU, .TcTLEO, .TcIO)
from the proto AST, following bottom-up dependency order for logs.

Usage:
    uv run python -m code-gen.generate [--output-dir OUTPUT]
"""

import argparse
import os
import sys
from pathlib import Path

# Add parent dir to path so we can import sibling modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from loader import load_ast, find_elements, get_package
from naming import proto_name_to_fb, proto_name_to_interface, proto_name_to_enum
from generators.enum_gen import generate_enum
from generators.interface_gen import generate_serializable_interface, generate_interface
from generators.fb_gen import generate_fb
from generators.anyvalue_gen import (
    generate_anyvalue_enum,
    generate_anyvalue_interface,
    generate_anyvalue_variants,
)

# Proto file keys in the AST
COMMON_KEY = "opentelemetry\\proto\\common\\v1\\common.proto"
RESOURCE_KEY = "opentelemetry\\proto\\resource\\v1\\resource.proto"
LOGS_KEY = "opentelemetry\\proto\\logs\\v1\\logs.proto"


def _write_file(output_dir: Path, subdir: str, filename: str, content: str) -> None:
    """Write a generated file to the appropriate subdirectory."""
    dir_path = output_dir / subdir
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / filename
    file_path.write_text(content, encoding="utf-8")
    print(f"  {subdir}/{filename}")


def generate_logs(ast: dict, output_dir: Path) -> None:
    """Generate all TwinCAT files for the logs signal, bottom-up."""
    print("Generating logs pipeline...\n")

    # ── Step 1: I_OtlpSerializable (base interface) ─────────────────
    print("[1/7] I_OtlpSerializable")
    xml = generate_serializable_interface()
    _write_file(output_dir, "INTERFACES", "I_OtlpSerializable.TcIO", xml)

    # ── Step 2: AnyValue discriminator enum ──────────────────────────
    print("[2/7] E_OtlpAnyValueType")
    filename, xml = generate_anyvalue_enum()
    _write_file(output_dir, "ENUMS", filename, xml)

    # ── Step 3: I_OtlpAnyValue interface ─────────────────────────────
    print("[3/7] I_OtlpAnyValue")
    filename, xml = generate_anyvalue_interface()
    _write_file(output_dir, "INTERFACES", filename, xml)

    # ── Step 4: AnyValue variant FBs ─────────────────────────────────
    print("[4/7] AnyValue variant FBs")
    for filename, xml in generate_anyvalue_variants():
        _write_file(output_dir, "FUNCTION_BLOCKS", filename, xml)

    # ── Step 5: common.proto messages (KeyValue, InstrumentationScope) ──
    print("[5/7] common.proto messages")
    common_pkg = get_package(ast, COMMON_KEY)
    common_messages = find_elements(ast, COMMON_KEY, "Message")
    for msg in common_messages:
        name = msg["name"]
        # Skip AnyValue (handled specially), ArrayValue, KeyValueList
        # (generated as AnyValue variants)
        if name in ("AnyValue", "ArrayValue", "KeyValueList", "EntityRef"):
            continue
        fb_name = proto_name_to_fb(name)
        itf_name = proto_name_to_interface(name)
        xml = generate_fb(msg, fb_name, itf_name, common_pkg, ast)
        _write_file(output_dir, "FUNCTION_BLOCKS", f"{fb_name}.TcPOU", xml)

    # ── Step 6: resource.proto ───────────────────────────────────────
    print("[6/7] resource.proto")
    resource_pkg = get_package(ast, RESOURCE_KEY)
    resource_messages = find_elements(ast, RESOURCE_KEY, "Message")
    for msg in resource_messages:
        name = msg["name"]
        fb_name = proto_name_to_fb(name)
        itf_name = proto_name_to_interface(name)
        xml = generate_fb(msg, fb_name, itf_name, resource_pkg, ast)
        _write_file(output_dir, "FUNCTION_BLOCKS", f"{fb_name}.TcPOU", xml)

    # ── Step 7: logs.proto (enums + messages) ────────────────────────
    print("[7/7] logs.proto")
    logs_pkg = get_package(ast, LOGS_KEY)

    # Enums
    logs_enums = find_elements(ast, LOGS_KEY, "Enum")
    for enum_node in logs_enums:
        enum_st_name = proto_name_to_enum(enum_node["name"])
        xml = generate_enum(enum_node, enum_st_name)
        _write_file(output_dir, "ENUMS", f"{enum_st_name}.TcTLEO", xml)

    # Messages
    logs_messages = find_elements(ast, LOGS_KEY, "Message")
    for msg in logs_messages:
        name = msg["name"]
        fb_name = proto_name_to_fb(name)
        itf_name = proto_name_to_interface(name)
        xml = generate_fb(msg, fb_name, itf_name, logs_pkg, ast)
        _write_file(output_dir, "FUNCTION_BLOCKS", f"{fb_name}.TcPOU", xml)

    print(f"\nDone! Output in: {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="TcOtlp Code Generator")
    parser.add_argument(
        "--ast",
        default="proto_ast.json",
        help="Path to proto_ast.json (default: proto_ast.json)",
    )
    parser.add_argument(
        "--output-dir",
        default="generated",
        help="Output directory for generated files (default: generated)",
    )
    args = parser.parse_args()

    # Resolve paths relative to project root
    project_root = Path(__file__).parent.parent
    ast_path = project_root / args.ast
    output_dir = project_root / args.output_dir

    if not ast_path.exists():
        print(f"Error: AST file not found: {ast_path}")
        print("Run dump_proto_ast.py first to generate it.")
        sys.exit(1)

    ast = load_ast(str(ast_path))
    generate_logs(ast, output_dir)


if __name__ == "__main__":
    main()
