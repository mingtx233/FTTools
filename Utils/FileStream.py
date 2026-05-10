import os

class ReadFileStream:
    def __init__(self, file_path: str):
        if not os.path.exists(file_path):
            raise Exception("%s does not exist." % file_path)
        self.file_size = os.path.getsize(file_path)
        self.file = open(file_path, "rb")

    def read(self, file_pos: int, chunk_size: int) -> bytes:
        self.file.seek(file_pos, 0)
        return self.file.read(chunk_size)
    
    def close(self) -> None:
        self.file.close()

class WriteFileStream:
    def __init__(self, file_path: str, file_len: int):
        self.file_path = file_path
        self.mid_file_path = file_path + ".bin"

        folder_path = os.path.dirname(self.mid_file_path)
        if not os.path.isdir(folder_path):
            os.makedirs(folder_path)
        
        if os.path.exists(self.mid_file_path):
            self.cur_file_size = os.path.getsize(self.mid_file_path)
            self.file = open(self.mid_file_path, "ab")
        else:
            self.cur_file_size = 0
            self.file = open(self.mid_file_path, "wb")
        
        self.file_len = file_len

    # Return: current size of file, -1 if file written completed
    def write(self, data: bytes) -> int:
        self.file.write(data)
        self.cur_file_size += len(data)

        # Completed writing the hold file
        if self.cur_file_size >= self.file_len:
            self.file.close()
            self.file = None
            if os.path.exists(self.file_path):
                file_id = 1
                root, extension = os.path.splitext(self.file_path)
                new_file_path = root + "_%d" % file_id + extension
                while os.path.exists(new_file_path):
                    file_id += 1
                    new_file_path = root + "_%d" % file_id + extension
                self.file_path = new_file_path
            os.rename(self.mid_file_path, self.file_path)

        return self.cur_file_size
    
    def close(self) -> None:
        if self.file is not None:
            self.file.close()
        self.file = None
    
    def is_completed(self) -> bool:
        return self.file is None
