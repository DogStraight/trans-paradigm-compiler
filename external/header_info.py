import re
import time
import os


from . import version_control as version_control
from . import predefine as predefine


# name
company: str = ""
author: str = ""
file_name: str = ""
module_name: str = ""
project_name: str = ""

# combination of name dict
name: dict = {
    "company": company,
    "project": project_name,
    "file": file_name,
    "module": module_name,
}

# description
purpose: str = ""
authors_email: str = ""
clock_frequency: str = "auto"
reset_polarity: str = "reset on '1'"
instantiation: str = ""

# combination of description dict
description: dict = {
    "purpose": purpose,
    "clock frequency": clock_frequency,
    "reset polarity": reset_polarity,
}

# dependencies
files: list = []
tool_version: str = ""
target_device: str = ""
dependence: dict = {
    "files": files,
    "tool version": tool_version,
    "target device": target_device
}
# waveform
wave: list = []


# time relative
created_time: str = ""
least_changed_time: str = ""
u_time: dict = {
    "created": created_time,
    "changed": least_changed_time
}
# vision relative
version: str = "0.0.0.0"

header_preload: dict = {
    "vlangtools file header": {
        "name": name,
        "description": description,
        "dependence": dependence,
        # "waveform": wave,
        "time": u_time,
        "version": version,
    }
}


def get_module_name(file_content) -> str:
    module_name = re.compile(predefine.regex_module_name).findall(file_content)
    # watch out here there have a huge bug because 
    try:
        return module_name
    except IndexError:
        return "no module found in this file"


def get_file_name(file_path) -> str:
    file_name = re.compile(predefine.regex_file_name).findall(file_path)
    return file_name[0]


def get_file_created_time(file_path: str) -> str:
    time_format_str: str = predefine.time_format_str
    return time.strftime(time_format_str, time.localtime(os.path.getctime(file_path)))


def get_file_change_time(file_path: str):
    time_format_str: str = predefine.time_format_str
    return time.strftime(time_format_str, time.localtime(os.path.getmtime(file_path)))


def load_header(file_content: str, file_path: str, origin_header: dict, is_update_version: bool) -> dict:
    current_header: dict = origin_header

    # name
    current_header["file header"]["name"]["file"] = get_file_name(file_path)
    current_header["file header"]["name"]["module"] = get_module_name(
        file_content)

    # description

    # version
    if is_update_version is True:
        current_header["file header"]["version"] = version_control.version_action(
            origin_header["file header"]["version"])

    # time
    current_header["file header"]["time"]["created"] = get_file_created_time(
        file_path)
    current_header["file header"]["time"]["changed"] = get_file_change_time(
        file_path)
    return current_header
