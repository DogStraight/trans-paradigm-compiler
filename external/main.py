
# to explain how this script or those scripts run ,
# check out this flow of process.
#
# header management process flow {
#     if(header which is can be detected exist):
#         [get] -> header ---> ...
#         [re cfg] -> header_info ---> ...
#         [write] -> target_file
#     else if(header is detected):
#         [get] -> header_info ---> ...
#         [refresh] -> header_info ---> ...
#         [write] -> target_file
#     else :
#         [message] -> "error parameter" ---> ...
#         [exit] -> process.this
#     additional module:
#         verilog_formatter : only format .v file
# }

# this script provide an interface name 'bite_the_dust' to remove this form of header.
# for some reason, some header information is impossible be known by the script's writer.
# So you can complete it or just ignore.

# WARMING : before use this script, make sure you have backup to keep
#     src file safety.

import argparse

from . import predefine as predefine
from . import header_action as header_action
from . import header_info as header_info
from . import verilog_formatter as vf


def add_header(file_content: str, file_path: str, args: dict) -> str:
    # find vlangtools header in file
    is_header_exist = header_action.Header.is_exist(file=file_content)

    if is_header_exist is True:
        current_header = header_action.Header.get(file=file_content)
        assert (current_header is not {})

        after_refresh_header = header_action.Header.refresh(
            header=current_header,
            file_path=file_path,
            file_content=file_content,
            is_update_version=args["is_update_version"]
        )
        # remove file header
        file_content = header_action.Header.bite_the_dust(file=file_content)

        # header_added_file : after header add file content
        header_added_file = header_action.Header.add(
            header=after_refresh_header, file=file_content)

    else:  # there is no vlangtools header in this file
        header_added_file = header_action.Header.add(
            header=header_info.load_header(
                file_content=file_content,
                file_path=file_path,
                origin_header=header_info.header_preload,
                is_update_version=args["is_update_version"]
            ),
            file=file_content
        )

    return header_added_file


def load_header_main_args() -> dict:
    parser = argparse.ArgumentParser(
        description='Generate header for verilog source file.')

    #! IMPORTANT : this argument is necessary
    parser.add_argument(
        '--file', "-f", type=str, nargs="+",
        help="target file path string")

    # version control flag
    parser.add_argument('--update_version', type=bool, default=False)

    args = parser.parse_args()
    return {
        "file": args.file,
        "is_update_version": args.update_version
    }


def load_format_main_args():
    parser = argparse.ArgumentParser(
        description='format for verilog source file.')

    parser.add_argument(
        '--file', "-f", type=str, nargs=1,
        help="target file path string"
    )
    args = parser.parse_args()
    target = args.file
    return target


def header_main():
    args = load_header_main_args()
    file_path = args["file"][0]
    file_content = predefine.fread(file_path)
    header_added_file = add_header(file_content, file_path, args)
    predefine.fwrite(file_path, header_added_file)


def format_main():
    target = load_format_main_args()
    vf_ins = vf.VerilogFormatter()
    vf_ins.format(target)


def test_main():
    # testing only
    target_file = "test/_test_indent.v"
    args = {
        "file": target_file,
        "is_update_version": False
    }
    file_path = target_file
    file_content = predefine.fread(file_path)
    header_added_file = add_header(file_content, file_path, args)
    predefine.fwrite(file_path, header_added_file)
    formatter = vf.VerilogFormatter()
    formatter.format([file_path])

if __name__ == '__main__':
    # main()
    test_main()
    pass
