import re
from typing import Iterator
target_file = "test/_test_align.v"


def fread(file: str) -> str:
    with open(file=file, encoding="utf-8", mode="r") as f:
        return f.read()


def fwrite(file: str, content) -> int:
    with open(file=file, encoding="utf-8", mode="w") as f:
        return f.write(content)


def get_branch_loc(value: str) -> int:
    if value == "" or '\'' not in value:
        return 4  # usually it 2 but it must has smart way to get it
    bch_loc = 0
    while value[bch_loc] != '\'':
        bch_loc += 1
    return bch_loc


def rm_blank(target_str: str):
    blank_char: list = ["\t", " "]
    for blank in blank_char:
        target_str = str(target_str).replace(blank, "")
    return target_str


def rm_blanks(*args: str) -> Iterator:
    for arg in args:
        arg = rm_blank(arg)
        yield arg


def get_max_len(result: list) -> tuple[int, int, int, int]:
    max_len_width: int \
        = len(max([res[1] for res in result], key=len))
    max_len_name: int \
        = len(max([res[2] for res in result], key=len))
    max_len_branch_left: int\
        = max([get_branch_loc(res[3]) for res in result])
    max_len_branch_right: int \
        = max([(len(res[3]) - get_branch_loc(res[3])) for res in result])
    return \
        max_len_width, \
        max_len_name, \
        max_len_branch_left, \
        max_len_branch_right


def align_declaration(content: str) -> str:
    declaration_pattern = r"(reg|wire) +(\[.*\])? *([A-Za-z0-9_]*) *=? *(.*?) *;"
    result:list = re.compile(declaration_pattern).findall(content)

    """ there is no explicit declaration """
    if len(result) == 0:
        # print("no explicit declaration found in file, skip this step...")
        return content
    
    max_name_len: int = 0
    max_width_len: int = 0
    blank = " "
    seq = ";"
    eq = "="

    """ get max info that use to align """
    max_width_len, \
        max_name_len, \
        max_len_branch_left, \
        max_len_branch_right \
        = get_max_len(result)

    # ltype is logic_type short case
    for (ltype, width, name, value) in result:
        """ remove blank char for each part """
        ltype, width, name, value = rm_blanks(
            ltype, width, name, value)

        """ assert that is formatted text """
        width_part = (width + blank) if width != "" else ""

        """ assert that is formatted text """
        init_part = (blank + eq + blank) if value != "" else ""

        """ generate old case """
        old_case \
            = ltype + blank\
            + width_part\
            + name \
            + init_part\
            + value + seq

        """ current branch char("'") location """
        current_branch_loc = get_branch_loc(
            value) if value != "" else 0

        """ such as: 1'b1 before branch is '1' and it's length is current_left """
        """ after "'" is 'b1' and it's length is current_right """
        current_left = current_branch_loc
        current_right = len(value) - current_left - 1

        """ if 'reg' -> 'reg  ',else 'wire'->'wire ' """
        new_case_ltype_part = ltype + blank if ltype == "wire" else ltype + blank*2

        """ if init is not None : init_part = " = " else "   " """
        new_case_init_part = init_part + blank * \
            len(blank+eq+blank) if eq not in init_part else init_part

        """ eh.. it about a little complicated  """
        """ generally no reg will init as complex expression at the declaration """
        """ but the wire type fuck up """
        """ so, do not init wire as complex expression just do cc """
        new_case_value_part = blank * \
            (max_len_branch_left-current_left) + value\
            + blank * (max_len_branch_right-current_right - 1)

        """ combine new_case """
        new_case \
            = new_case_ltype_part\
            + width + blank*(max_width_len - len(width) + 1)\
            + name + blank*(max_name_len - len(name))\
            + new_case_init_part\
            + new_case_value_part + seq

        """ replace the old to new """
        print(old_case)
        print(new_case)
        content = content.replace(old_case, new_case)
    return content


def align_ins_port(content: str) -> str:

    old_case = \
        re.compile(r"\.[_A-Za-z][_A-Za-z0-9]*\(.*\)").\
        findall(content)
    
    if old_case == []:
        # print("no instance port found in file, skip this step...")
        return content
    
    """ port name """
    p_name = [
        re.compile(r"\.(.*?)\(").findall(case)[0]
        for case in old_case
    ]
    
    """ port connecting connection """
    p_cc = [
        re.compile(name+r'\((.*)\)').findall(case)[0]
        for name, case in zip(p_name, old_case)
    ]

    max_name_len: int = len(max(p_name, key=len))
    max_connection_len: int = len(max(p_cc, key=len))

    new_case = [
        "."
        + f"{name:<{max_name_len}}"
        + "("
        + f"{cc:<{max_connection_len}}"
        + ")"
        for name, cc in
        zip(p_name, p_cc)
    ]

    for old, new in zip(old_case, new_case):
        content = content.replace(old, new, 1) # replace only once
    return content


def align_assignment(content: str) -> str:

    return content



def align_port_list(content: str) -> str:

    return content

def align_module_parameter(content: str) -> str:

    return content

def align_module_local_parameter(content: str) -> str:

    return content

def main():
    content = fread(target_file)
    content = align_declaration(content)
    content = align_ins_port(content)
    fwrite(target_file, content)


if __name__ == "__main__":
    main()
