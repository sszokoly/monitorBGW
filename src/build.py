#!/usr/bin/env python
# -*- encoding: utf-8 -*-

import os
from script import compress_and_wrap

MODULES = [
    "config",
    "storage",
    "script",
    "layout",
    "filter",
    "bgw",
    "rtpparser",
    "ahttp",
    "aloop",
    "workspace",
    "utils",
]

def read_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

def read_module_doc(module_name, folder="src"):
    doc_path = f"{folder}/{module_name}.py"
    if os.path.exists(doc_path):
        return read_file(doc_path)
    return ""

def extract_marker_indexes(marker_name, content):
    marker_name = marker_name.upper()   
    start_marker = f"### BEGIN {marker_name}"
    end_marker = f"### END {marker_name} "

    lines = content.splitlines()
    start_lines = [x for x in range(len(lines)) if start_marker in lines[x]]
    end_lines = [x for x in range(len(lines)) if end_marker in lines[x]]

    if start_lines and end_lines:
        return start_lines[0], end_lines[0]
    return -1, -1

def extract_lines(marker_name, content):
    start_idx, end_idx = extract_marker_indexes(marker_name, content)
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        lines = content.splitlines()
        return lines[start_idx:end_idx + 1]

def extract_module(module_name):
    module_doc = read_module_doc(module_name)
    if not module_doc:
        return ""
    extracted_lines = extract_lines(module_name, module_doc)
    if extracted_lines:
        return extracted_lines
    return ""

def build_python_script(main_module="main", output_file="monitorBGW.py"):
    module_doc = read_module_doc(main_module)
    
    import_marker_indexes = extract_marker_indexes("IMPORTS", module_doc)
    module_marker_indexes = extract_marker_indexes("MODULES", module_doc)

    if module_marker_indexes == (-1, -1):
        print("No MODULES markers found in main.py")
        return

    _, imports_end_idx = import_marker_indexes
    _, module_end_idx = module_marker_indexes
    main_module_lines = module_doc.splitlines()
    imports = main_module_lines[:imports_end_idx + 1]
    after_modules = main_module_lines[module_end_idx + 1:]

    with open(output_file, "w", encoding="utf-8") as out_file:
        for line in imports:
            out_file.write(line + "\n")
        for module in MODULES:
            module_doc = read_module_doc(module)
            if module_doc:
                extracted_content = extract_module(module)
                if extracted_content:
                    for line in extracted_content:
                        out_file.write(line + "\n")
        for line in after_modules:
            out_file.write(line + "\n")

    os.chmod(output_file, 0o755)

def build_compacted_bash_script(input_file="monitorBGW.py", output_file="monitorBGW"):
    content = read_file(input_file)
    compacted_script = compress_and_wrap(content)
    with open(output_file, "w", encoding="utf-8", ) as out_file:
        out_file.write("#!/usr/bin/env python\n")
        out_file.write("##########################################################\n")
        out_file.write("## Name: monitorBGW\n")
        out_file.write("## Purpose: This tool monitors Avaya G4xx Branch gateways\n")
        out_file.write("## Author: sszokoly@protonmail.com\n")
        out_file.write("## License: MIT\n")
        out_file.write("## Version: 0.1\n")
        out_file.write("## Source: https://github.com/sszokoly/monitorBGW\n")
        out_file.write("##########################################################\n\n")
        out_file.write("import base64\n")
        out_file.write("import zlib\n\n")
        out_file.write("COMPRESSED_SCRIPT = '''\\\n")
        out_file.write(compacted_script)
        out_file.write("\n'''\n\n")
        out_file.write("def unwrap_and_decompress(wrapped_text):\n")
        out_file.write("    \"\"\"Unwraps, base64 decodes and decompresses string\"\"\"\n")
        out_file.write("    base64_str = wrapped_text.replace(\"\\n\", \"\")\n")
        out_file.write("    compressed_bytes = base64.b64decode(base64_str)\n")
        out_file.write("    original_string = zlib.decompress(compressed_bytes).decode(\"utf-8\")\n")
        out_file.write("    return original_string\n\n")
        out_file.write("if __name__ == \"__main__\":\n")
        out_file.write("    script_content = unwrap_and_decompress(COMPRESSED_SCRIPT)\n")
        out_file.write("    try:\n")
        out_file.write("        exec(script_content)\n")
        out_file.write("    except Exception as e:\n")
        out_file.write("        print(f\"Unhandled exception executing script: {e}\")\n")
        out_file.write("\n")

    os.chmod(output_file, 0o755)

if __name__ == "__main__":
    build_python_script()
    build_compacted_bash_script()
