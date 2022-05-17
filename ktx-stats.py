#!/usr/bin/env python
import struct
import json
import sys
import os
import gzip


demoname = os.path.basename(sys.argv[1].rstrip(".gz"))

fopen = gzip.open if sys.argv[1].endswith(".gz") else open

with fopen(sys.argv[1], "rb") as fd:
    data = fd.read()

# Hacky zoom-in of correct area, json blob contains demo filename.
offset = data.rfind(demoname.encode())

offset = data[:offset].rfind(b"\x0a\x00\x00\x03\x00\x00\x00\x00")
offset += 2

content = b""

while data[offset:offset + 4] == b"\x00\x03\x00\x00":
    (length,) = struct.unpack("<H", data[offset+10:offset+12])
    start = offset + 18
    end = start + length - 2
    content += data[start:end]
    offset = end

try:
    json.loads(content)
    print("success", sys.argv[1])
    (name, _) = os.path.splitext(sys.argv[1])

    with open(name + ".json", "wb+") as fd:
        fd.write(content)
except:
    print(content)
    print("failed to load", sys.argv[1])
