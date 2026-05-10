import io, struct, zipfile, hashlib

class CompressorPlain:
    @staticmethod
    def compress(data: bytes) -> bytes:
        size = struct.pack("I", len(data))
        checksum = hashlib.md5(data).digest()
        return size + checksum + data

    @staticmethod
    def decompress(zip_data: bytes) -> bytes:
        header_len = struct.calcsize("I16s")
        size, checksum = struct.unpack("I16s", zip_data[:header_len])
        data = zip_data[header_len:]
        if len(data) != size:
            raise Exception("Incorrect data size")
        elif hashlib.md5(data).digest() != checksum:
            raise Exception("Incorrect data")
        return data


class CompressorZip:
    @staticmethod
    def compress(data: bytes) -> bytes:
        data_list: list[tuple[str, bytes]] = [
            ("size", struct.pack("I", len(data))),
            ("checksum", hashlib.md5(data).digest()),
            ("data", data)
        ]
        
        mem_zip = io.BytesIO() # Create an in-memory binary stream
        with zipfile.ZipFile(mem_zip, mode = 'w',
                            compression = zipfile.ZIP_DEFLATED) as zf:
            for filename, data in data_list:
                zf.writestr(filename, data)

        return mem_zip.getvalue()

    @staticmethod
    def decompress(zip_data: bytes) -> bytes:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            for item_name in zf.namelist():
                with zf.open(item_name) as zitem:
                    content = zitem.read()
                
                if item_name == "size":
                    item_size, = struct.unpack("I", content)
                elif item_name == "checksum":
                    item_checksum = content
                elif item_name == "data":
                    item_data = content
            
            if len(item_data) != item_size:
                raise Exception("Incorrect data size")
            if hashlib.md5(item_data).hexdigest() != item_checksum:
                raise Exception("Incorrect data")
            return item_data


#Compressor = CompressorPlain
Compressor = CompressorZip
