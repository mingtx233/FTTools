import numpy as np

from Utils.Utils import Random

def _form_data_map(rand: Random, data_map: np.ndarray) -> np.ndarray:
    tmp_list = list(range(256))
    for i in range(255):
        pos_id = rand.randint(0, 256 - i)
        data_map[i] = tmp_list.pop(pos_id)
    data_map[255] = tmp_list[0]
    return data_map

def _form_inv_data_map(data_map: np.ndarray, inv_data_map: np.ndarray) -> np.ndarray:
    for i in range(256):
        inv_data_map[data_map[i]] = i
    return inv_data_map


class ConvertorPlain:
    def __init__(self, passwd: bytes):
        pass
    
    def forward(self, data: bytearray) -> bytearray:
        return data

    def backward(self, data: bytearray) -> bytearray:
        return data


class ConvertorSimple:
    def __init__(self, passwd: bytes):
        rand = Random(int.from_bytes(passwd, byteorder = "little"))
        self.data_map = _form_data_map(rand, np.zeros(256, dtype = int))
        self.inv_data_map = _form_inv_data_map(self.data_map, np.zeros(256, dtype = int))
    
    def forward(self, data: bytearray) -> bytearray:
        data_num = len(data)
        res_data = bytearray(data_num)
        for i in range(data_num):
            res_data[i] = self.data_map[data[i]]
        return res_data

    def backward(self, data: bytearray) -> bytearray:
        data_num = len(data)
        res_data = bytearray(data_num)
        
        for i in range(data_num):
            res_data[i] = self.inv_data_map[data[i]]
        return res_data


class ConvertorSafe:
    def __init__(self, passwd: bytes):
        self.passwd = int.from_bytes(passwd, byteorder = "little")
        self.seed_rand = Random()
    
    def forward(self, data: bytearray) -> bytearray:
        self.seed_rand.seed(self.passwd)
        data_num = len(data)
        res_data = bytearray(data_num)
        data_map = np.zeros(256, dtype = int)
        for i in range(data_num):
            rand = Random(self.seed_rand.extract_number())
            _form_data_map(rand, data_map)
            res_data[i] = data_map[data[i]]
        return res_data

    def backward(self, data: bytearray) -> bytearray:
        self.seed_rand.seed(self.passwd)
        data_num = len(data)
        res_data = bytearray(data_num)
        data_map = np.zeros(256, dtype = int)
        inv_data_map = np.zeros(256, dtype = int)
        for i in range(data_num):
            rand = Random(self.seed_rand.extract_number())
            _form_data_map(rand, data_map)
            _form_inv_data_map(data_map, inv_data_map)
            res_data[i] = inv_data_map[data[i]]
        return res_data


class ConvertorBalance:
    def __init__(self, passwd: bytes, map_num: int = 1024):
        self.passwd = int.from_bytes(passwd, byteorder = "little")
        self.map_num = map_num
        self.seed_rand = Random(self.passwd)
        
        self.data_map = np.zeros([ map_num, 256 ], dtype = int)
        self.inv_data_map = np.zeros([ map_num, 256 ], dtype = int)
        for map_id in range(map_num):
            rand = Random(self.seed_rand.extract_number())
            _form_data_map(rand, self.data_map[map_id, :])
            _form_inv_data_map(self.data_map[map_id, :], self.inv_data_map[map_id, :])
    
    def forward(self, data: bytearray) -> bytearray:
        self.seed_rand.seed(self.passwd)
        data_num = len(data)
        res_data = bytearray(data_num)
        for i in range(data_num):
            map_id = self.seed_rand.randint(0, self.map_num)
            res_data[i] = self.data_map[map_id, data[i]]
        return res_data

    def backward(self, data: bytearray) -> bytearray:
        self.seed_rand.seed(self.passwd)
        data_num = len(data)
        res_data = bytearray(data_num)
        for i in range(data_num):
            map_id = self.seed_rand.randint(0, self.map_num)
            res_data[i] = self.inv_data_map[map_id, data[i]]
        return res_data


Convertor = ConvertorPlain
#Convertor = ConvertorSimple
#Convertor = ConvertorSafe
#Convertor = ConvertorBalance
