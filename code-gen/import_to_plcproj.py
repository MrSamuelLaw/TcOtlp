"""Import generated TwinCAT files into the PLC project.

Copies files from the generated/ directory into TcOtlp/test/OTEL/AUTO_GENERATED/
and updates the .plcproj MSBuild XML to register them.

Preserves:
  - MAIN.TcPOU, PlcTask.TcTTO, test.tmc
  - TEST_OTEL/ entries (Compile + Folder)
  - PlaceholderReference (library) entries
  - ProjectExtensions
  - All non-OTEL Folder entries

Usage:
    uv run python import_to_plcproj.py [--generated-dir DIR] [--dry-run]
"""

import argparse
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "http://schemas.microsoft.com/developer/msbuild/2003"
ET.register_namespace("", NS)

# Subdirectory mapping: generated subdir -> OTEL/AUTO_GENERATED subdir + file extension
ROOT = Path("OTEL/AUTO_GENERATED")
SUBDIRS_EXT_MAP = {
    "ENUMS": ".TcTLEO",
    "INTERFACES": ".TcIO",
    "FUNCTION_BLOCKS": ".TcPOU",
}


def copy_files(generated_dir: Path, target_dir: Path, dry_run: bool) -> list[str]:
    """Copy generated files into TcOtlp/test/OTEL/AUTO_GENERATED/, overwriting existing files."""
    # Clean up old OTEL subdirectories before copying new files
    dst_dir = target_dir / ROOT
    if not dry_run and dst_dir.exists():
        shutil.rmtree(dst_dir)
    if not dry_run:
        shutil.copytree(generated_dir, dst_dir, dirs_exist_ok=True)
    return [f for f in generated_dir.rglob("*") if f.is_file()]
    
    
def update_plcproj(plcproj_path: Path, generated_entries: list[Path], dry_run: bool) -> None:
    """Update the .plcproj XML to register generated files.

    Strategy:
      1. Scan the filesystem for non-AUTO_GENERATED code files and directories.
      2. Remove all existing AUTO_GENERATED Compile entries (they'll be regenerated).
      3. Re-include any missing non-AUTO_GENERATED Compile/Folder entries discovered
         on disk (e.g. MAIN.TcPOU, PlcTask.TcTTO, TEST_OTEL\\...) in case they were
         accidentally removed from the XML.
      4. Add Compile entries for each generated file.
      5. Ensure AUTO_GENERATED folder entries exist; keep all other Folder entries.
      6. Leave PlaceholderReference and ProjectExtensions untouched.
    """
    tree = ET.parse(plcproj_path)
    root = tree.getroot()

    auto_gen_prefix = str(ROOT).replace("/", "\\")

    # Find the Compile ItemGroup (first one with Compile children)
    compile_ig = None
    folder_ig = None
    for ig in root.findall(f"{{{NS}}}ItemGroup"):
        children_tags = [c.tag.split("}")[-1] if "}" in c.tag else c.tag for c in ig]
        if "Compile" in children_tags and compile_ig is None:
            compile_ig = ig
        elif "Folder" in children_tags and folder_ig is None:
            folder_ig = ig

    if compile_ig is None or folder_ig is None:
        raise RuntimeError("Could not find Compile or Folder ItemGroup in .plcproj")

    # --- Discover expected non-AUTO_GENERATED entries from the filesystem ---
    plcproj_dir = plcproj_path.parent

    expected_compiles: dict[str, str] = {}  # Include path -> SubType
    for f in plcproj_dir.rglob("*"):
        if not f.is_file():
            continue
        rel = str(f.relative_to(plcproj_dir)).replace("/", "\\")
        # Skip AUTO_GENERATED files (managed separately) and non-code files
        if rel.startswith(auto_gen_prefix):
            continue
        if f.suffix in (".TcPOU", ".TcTTO", ".TcIO", ".TcTLEO"):
            expected_compiles[rel] = "Code"

    expected_folders: set[str] = set()
    for d in plcproj_dir.rglob("*"):
        if not d.is_dir():
            continue
        rel = str(d.relative_to(plcproj_dir)).replace("/", "\\")
        if rel.startswith(auto_gen_prefix):
            continue
        # Only include directories that contain code files or subdirectories with code
        has_code = any(
            cf.suffix in (".TcPOU", ".TcTTO", ".TcIO", ".TcTLEO")
            for cf in d.rglob("*") if cf.is_file()
        )
        if has_code:
            expected_folders.add(rel)

    # --- Remove all AUTO_GENERATED Compile entries (they'll be regenerated) ---
    to_remove = []
    for elem in compile_ig.findall(f"{{{NS}}}Compile"):
        include = elem.get("Include", "")
        if include.startswith(auto_gen_prefix):
            to_remove.append(elem)
    for elem in to_remove:
        compile_ig.remove(elem)

    # --- Re-include any missing non-AUTO_GENERATED Compile entries ---
    existing_compiles = {
        elem.get("Include", "")
        for elem in compile_ig.findall(f"{{{NS}}}Compile")
    }
    for include_path in sorted(expected_compiles):
        if include_path not in existing_compiles:
            compile_elem = ET.SubElement(compile_ig, f"{{{NS}}}Compile")
            compile_elem.set("Include", include_path)
            subtype = ET.SubElement(compile_elem, f"{{{NS}}}SubType")
            subtype.text = expected_compiles[include_path]

    # --- Add new AUTO_GENERATED Compile entries, sorted for determinism ---
    for include_path in sorted(generated_entries):
        include_path = str(include_path).replace("/", "\\")
        compile_elem = ET.SubElement(compile_ig, f"{{{NS}}}Compile")
        compile_elem.set("Include", include_path)
        subtype = ET.SubElement(compile_elem, f"{{{NS}}}SubType")
        subtype.text = "Code"

    # --- Remove old AUTO_GENERATED folder entries (they'll be regenerated) ---
    old_otel_folders = [str(ROOT / k).replace("/", "\\") for k in SUBDIRS_EXT_MAP.keys()]
    to_remove_folders = []
    for elem in folder_ig.findall(f"{{{NS}}}Folder"):
        folder_include = elem.get("Include", "")
        if folder_include in old_otel_folders:
            to_remove_folders.append(elem)
    for elem in to_remove_folders:
        folder_ig.remove(elem)

    # --- Re-include any missing non-AUTO_GENERATED Folder entries ---
    existing_folders = {
        elem.get("Include", "")
        for elem in folder_ig.findall(f"{{{NS}}}Folder")
    }
    for folder in sorted(expected_folders):
        if folder not in existing_folders:
            folder_elem = ET.SubElement(folder_ig, f"{{{NS}}}Folder")
            folder_elem.set("Include", folder)

    # --- Ensure AUTO_GENERATED folder entries exist ---
    existing_folders = {
        elem.get("Include", "")
        for elem in folder_ig.findall(f"{{{NS}}}Folder")
    }
    for subdir in SUBDIRS_EXT_MAP.keys():
        folder = str(ROOT / subdir).replace("/", "\\")
        if folder not in existing_folders:
            folder_elem = ET.SubElement(folder_ig, f"{{{NS}}}Folder")
            folder_elem.set("Include", folder)

    if not dry_run:
        # Write with XML declaration matching the original
        tree.write(plcproj_path, xml_declaration=True, encoding="utf-8")
        # ElementTree doesn't produce pretty output; reformat
        _reformat_xml(plcproj_path)


def _reformat_xml(path: Path) -> None:
    """Reformat XML with proper indentation."""
    import xml.dom.minidom
    raw = path.read_text(encoding="utf-8")
    dom = xml.dom.minidom.parseString(raw)
    pretty = dom.toprettyxml(indent="  ", encoding="utf-8")
    # Remove extra XML declaration line that minidom adds, keep first one
    lines = pretty.decode("utf-8").splitlines(keepends=True)
    # minidom adds <?xml ...?> on first line, which we want to keep
    # Remove blank lines between elements for cleaner output
    cleaned = []
    for line in lines:
        if line.strip():
            cleaned.append(line)
    path.write_text("".join(cleaned), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Import generated files into TcOtlp PLC project")
    parser.add_argument(
        "--generated-dir",
        default="generated",
        help="Path to generated output directory (default: generated)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    generated_dir = project_root / args.generated_dir
    plcproj_dir = project_root / "TcOtlp" / "test"
    plcproj_path = plcproj_dir / "test.plcproj"

    if not generated_dir.exists():
        print(f"Error: Generated directory not found: {generated_dir}")
        print("Run generate.py first.")
        return 1

    if not plcproj_path.exists():
        print(f"Error: .plcproj not found: {plcproj_path}")
        return 1

    # Copy files
    print(f"\n{'[DRY RUN] Would copy' if args.dry_run else 'Copying'} files to {plcproj_dir / 'OTEL' / 'AUTO_GENERATED'}...")
    copied = copy_files(generated_dir, plcproj_dir, args.dry_run)
    for c in copied:
        print(f"  {c}")

    # Update .plcproj
    print(f"\n{'[DRY RUN] Would update' if args.dry_run else 'Updating'} {plcproj_path}...")
    entries = [str(ROOT / c.relative_to(generated_dir)) for c in copied]
    update_plcproj(plcproj_path, entries, args.dry_run)

    print("\nDone!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
