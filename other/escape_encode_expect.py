#!/usr/bin/env python3
# MIT License
"""
Converts the bgw.exp script to a Python-ready string with proper escaping.
Only escapes braces OUTSIDE the template variables section.
Also creates a compressed and BASE64 encoded version.
Usage: python3 escape_encode_expect.py bgw.exp
"""

import base64
import sys
import textwrap
import zlib

def enclose_script(script):
    """
    Encloses all curly braces EXCEPT in the template variables section.
    
    Args:
        script: The Expect script as a string
        
    Returns:
        The script with curly braces escaped (doubled) everywhere except
        in the template variables section
    """
    # Find the template variables section
    template_start = script.find("############################# Template Variables #############################")
    template_end = script.find("############################## Expect Variables ##############################")
    
    if template_start == -1 or template_end == -1:
        raise ValueError("Could not find template variable markers in script")
    
    # Split the script into three parts
    before_template = script[:template_start]
    template_section = script[template_start:template_end]
    after_template = script[template_end:]
    
    # Function to escape braces by doubling them
    def escape_braces(text):
        return text.replace('{', '{{').replace('}', '}}')
    
    # Escape braces only in non-template sections
    before_escaped = escape_braces(before_template)
    after_escaped = escape_braces(after_template)
    
    # Keep template section as-is (no escaping)
    # Combine all parts
    return before_escaped + template_section + after_escaped

def compress_and_wrap(input_string, column_width=78):
    compressed_bytes = zlib.compress(input_string.encode('utf-8'))
    base64_bytes = base64.b64encode(compressed_bytes)
    wrapped = textwrap.fill(base64_bytes.decode('utf-8'), width=column_width)
    return wrapped

def unwrap_and_decompress(wrapped_text):
    base64_str = wrapped_text.replace('\n', '')
    compressed_bytes = base64.b64decode(base64_str)
    original_string = zlib.decompress(compressed_bytes).decode('utf-8')
    return original_string

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 expect_to_python.py <expect_script.exp>", 
              file=sys.stderr)
        print("\nConverts an Expect script to a Python string with proper escaping.",
              file=sys.stderr)
        print("Output can be copied directly into Python source code.",
              file=sys.stderr)
        sys.exit(1)
    
    # Read the input script
    input_file = sys.argv[1]
    try:
        with open(input_file, 'r') as f:
            script = f.read()
    except FileNotFoundError:
        print(f"Error: File '{input_file}' not found", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Enclose the script
    try:
        enclosed_script = enclose_script(script)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Output Python code with the string
    print("EXPECT_SCRIPT = '''\\")
    print(enclosed_script, end='')
    print("'''")
    # Compressed and wrapped version
    print("\n# Compressed and base64-encoded version:")
    wrapped = compress_and_wrap(enclosed_script)
    print("COMPRESSED_EXPECT_SCRIPT = '''\\")
    print(wrapped)
    print("'''")    
    unwrapped = unwrap_and_decompress(wrapped)
    assert unwrapped == enclosed_script

if __name__ == "__main__":
    main()
