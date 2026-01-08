#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS ##################################

import base64
import zlib

############################## END IMPORTS ####################################
############################## BEGIN SCRIPT ###################################

COMPRESSED_EXPECT_SCRIPT = '''\
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
'''

def unwrap_and_decompress(wrapped_text):
    """Unwraps, base64 decodes and decompresses string"""
    base64_str = wrapped_text.replace("\n", "")
    compressed_bytes = base64.b64decode(base64_str)
    original_string = zlib.decompress(compressed_bytes).decode("utf-8")
    return original_string

EXPECT_SCRIPT = unwrap_and_decompress(COMPRESSED_EXPECT_SCRIPT)

############################## END SCRIPT #####################################

def compress_and_wrap(input_string, column_width=78):
    """Compresses, base64 encodes and wraps text"""
    import textwrap
    compressed_bytes = zlib.compress(input_string.encode("utf-8"))
    base64_bytes = base64.b64encode(compressed_bytes)
    wrapped = textwrap.fill(base64_bytes.decode("utf-8"), width=column_width)
    return wrapped

if __name__ == "__main__":
    wrapped = compress_and_wrap(EXPECT_SCRIPT)
    print(EXPECT_SCRIPT)
    assert wrapped == COMPRESSED_EXPECT_SCRIPT
