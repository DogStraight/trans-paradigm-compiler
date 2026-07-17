# module import
import json
import re

from . import predefine as predefine
from . import header_info as header_info


class Header:
    # judge the header is exist in file
    @staticmethod
    def is_exist(file: str) -> bool:
        return re.search(pattern=predefine.regex_header_exist, string=file) is not None

    #  get header from origin file
    @staticmethod
    def get(file: str) -> dict:
        read_header_dict = {}
        read_header: list = re.compile(predefine.regex_header_content).findall(file)
        try:
            read_header[0] = "{" + read_header[0] + "}"
        except IndexError:
            content = "header found in file but can not define \"END_CHAR\" location"
            predefine.fwrite(file="./vlangtools_error.log",content=content,mode="a")
            raise IndexError
        try:
            read_header_dict = json.loads(read_header[0])
        except json.JSONDecodeError:
            content = "header seem not a json form"
            predefine.fwrite(file="./vlangtools_error.log",content=content)
            raise json.JSONDecodeError
        return read_header_dict

    # in this function header will add to target file no matter what
    @staticmethod
    def add(header: dict | str, file: str) -> str:
        # indent is default in 4
        header_to_add = json.dumps(header, indent=4)if isinstance(
            header, dict) else header
        ready_to_write = "/*\n" + header_to_add + "\n*/\n"
        return ready_to_write + file

    # refresh header
    @staticmethod
    def refresh(header: dict, file_path: str, file_content: str, is_update_version: bool) -> dict:

        header_info.load_header(
            file_content=file_content,
            file_path=file_path,
            origin_header=header,
            is_update_version=is_update_version
        )

        return header

    # killer queen 3rd bomb !
    @staticmethod
    def bite_the_dust(file: str) -> str:
        return re.sub(predefine.regex_header_content, "", file)
    
