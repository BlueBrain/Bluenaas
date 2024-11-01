import hashlib
import json


def get_hash(obj: any) -> str:
    data_str = json.dumps(obj, sort_keys=True)

    hash_object = hashlib.sha256(data_str.encode())
    hash_hex = hash_object.hexdigest()

    return hash_hex
