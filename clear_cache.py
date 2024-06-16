import os
from constants import DOCUMENT_DIR_PREFIX


def clear_document_cache():
    """
    Clear the document cache
    """
    for file in os.listdir(DOCUMENT_DIR_PREFIX):
        os.remove(os.path.join(DOCUMENT_DIR_PREFIX, file))
    print("Document cache cleared")    


if __name__ == "__main__":
    clear_document_cache()