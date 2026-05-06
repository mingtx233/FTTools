import struct

print(struct.unpack("B", b"\x00")[0])
print(struct.unpack("B", b"\x01")[0])

print(0xff)
