import re
from .predefine import fwrite, fread

def remove_comment(text, remove_comment_condition: list):
    for condition in remove_comment_condition:
        text = re.compile(condition).sub("", text)
    return text


class VerilogFormatter:
    # blank char
    blank: str = " "
    eq_list: list = ['=', "==", "===", "<="]

    # the beginning location will depend on it
    is_compact: bool = True
    # a flag to show current line is in comment(full in not mixed)
    is_in_comment: bool = False

    # indent describe sign
    indent_deep: int = 0
    indent_level: int = 0

    # for re
    tail_clause_condition: list[str] = [
        r" *if *\(.*\) *(?!.*begin)\s*\n.*;",  # for if segment, include else if
        r" *else(?!.*if)(?!.*begin).*\n.*;"  # for else segment
    ]

    remove_comment_condition: list[str] = [
        r"//.*",  # one line
        r"/\*.*\*/",  # one line block
        r"/\*.*$",  # unclose upper
        r"^.*\*/"  # unclose lower
    ]

    indent_level_plus_condition: dict[str, dict[str, int]] = {"word": {
        "begin":   (+ 1),
        ")begin":  (+ 1),
        "begin\\": (+ 1),
        "begin:":  (+ 1),
    }, "char": {
        "(":       (+ 1),
        "[":       (+ 1),
        "{":       (+ 1),
    }}

    indent_level_reduce_condition: dict[str, dict[str, int]] = {"word": {
        "end":     (- 1),
        "end\\":   (- 1),
    }, "char": {
        ")":       (- 1),
        "]":       (- 1),
        "}":       (- 1),
    }}

    def __init__(
        self, indent_deep: int = 4, 
        is_compact: bool = True) -> None:
        
        self.is_compact = is_compact
        self.indent_deep =\
            indent_deep \
            if 8 >= indent_deep >= 1 \
            else 8 \
            if indent_deep > 8 \
            else 1  # if indent_deep < 1

    def _create_indent(self, current: str) -> str:
        if self.is_in_comment is True:
            return current

        # CLRC : current line remove comment
        CLRC:  str = remove_comment(current, self.remove_comment_condition)
        # CLRW : current line remove comment and left words after splitted by space
        CLRW: list = CLRC.split(" ")
        # PLCC : plus indent level case [char]
        PLCC: dict = self.indent_level_plus_condition["char"]
        # plus indent level case [word]
        PLCW: dict = self.indent_level_plus_condition["word"]
        # reduce indent level case [char]
        RLCC: dict = self.indent_level_reduce_condition["char"]
        # reduce indent level case [word]
        RLCW: dict = self.indent_level_reduce_condition["word"]

        # remove blank first
        current = re.compile(r"^ *").sub("", current)
        current = re.compile(r" +").sub(" ", current)
        current = self.blank * self.indent_deep * self.indent_level + current

        # regenerate indent_level
        for char in CLRC:
            self.indent_level \
                += (0 if char not in PLCC else PLCC[char]) \
                + (0 if char not in RLCC else RLCC[char])
            if char not in RLCC:
                continue
            pattern = self.blank * self.indent_deep + char
            current = current.replace(pattern, char)

        for word in CLRW:
            self.indent_level \
                += (0 if word not in PLCW else PLCW[word]) \
                + (0 if word not in RLCW else RLCW[word])
            if word not in RLCW:
                continue
            pattern = self.blank * self.indent_deep + word
            current = current.replace(pattern, word)

        # regenerate blank line protect for block
        if self.indent_level == 0 and "end" in [word for word in CLRW]:
            current += "\n\n"

        return current

    def _judge_comment(self, current: str) -> None:
        if "/*" in current and "*/" not in current:
            self.is_in_comment = True
        if "*/" in current and self.is_in_comment is True:
            self.is_in_comment = False

    def _preprocess_target(self, target: str) -> str:
        # ! reshape "begin" location don't touch !!!
        target = re.compile(r" *begin").sub(" begin", target)

        # ! file tail end line handle don't touch !!!
        target = re.compile(r"\n+$").sub("", target)

        # ! replace file table case don't touch !!!
        target = re.compile(r"\t").sub(" ", target)

        # ! handle compact affair don't touch !!!
        if self.is_compact is True:
            target = re.compile(r"\n[\s]*begin").sub(" begin", target)
        else :
            target = re.compile(r"([A-Za-z0-0_\);])[\s]*begin").sub(r"\1\nbegin", target)

        # ^ the blank line handle may be it is unnecessary
        target = re.compile(r"\n\n+").sub("\n", target)

        # ^ the inline blank handle may be it is unnecessary
        target = re.compile(r" *;").sub(";", target)

        # * ':' location handle
        target = re.compile(
            r"([a-zA-z]) *: *([a-zA-z])").sub(r"\1: \2", target)
        target = re.compile(r"([0-9]) *: *([0-9])").sub(r"\1:\2", target)

        # * '=',"==","===" location handle
        for eq in self.eq_list:
            target = re.compile(
                r"([a-zA-z0-9]) *%s *([a-zA-z0-9])" % eq).sub(r"\1 %s \2" % eq, target)

        # * "]" location handle
        target = re.compile(r"([a-zA-z0-9]) *\] *([a-zA-z0-9])").sub(r"\1] \2", target)

        return target

    def _reprocess_target(self, new_target: str) -> str:
        # nested function : tail_clause
        def tail_clause(new_target: str) -> str:
            """ 
            this function will add one level indent to those line which is 
            be match as tail clause, and is only has a line cross. this is a 
            very special case.
            example : 
            '''verilog
            if (some_condition)
            some_thing <= some_value;
            else
            some_thing <= some_value;
            '''
            covert to:
            '''verilog
            if (some_condition)
                some_thing <= some_value;
            else 
                some_thing <= some_value;
            '''
            """
            # prepare tail clause indent
            tail_indent: str = self.indent_deep * self.blank
            for trigger in self.tail_clause_condition:
                target_case: list[str] = re.compile(trigger).findall(new_target)
                """
                if any no good enough form comes up this function will not
                work which case is like:
                '''verilog
                /* case 1 : tail line comment */
                if (some_condition) // some comment 
                some_thing <= some_value;
                ...
                /* case 2 : multiple line crossing segment */
                if (
                    condition_1
                    && condition_2
                    && ...
                )  
                some_thing <= some_value;
                ...
                '''
                the tail line comment and multiple line crossing condition segment
                will not be match as tail clause. if you have to write like that
                make sure you segment has 'begin' and 'end' to show segment scope
                """
                target_case_add_indent: list = [target_case[_].replace(
                    "\n", "\n" + tail_indent) for _ in range(len(target_case))]
                for (old_case, new_case) in zip(target_case, target_case_add_indent):
                    new_target = new_target.replace(old_case, new_case)
            return new_target
        # ! handle tail clause don't touch !!!
        new_target = tail_clause(new_target)
        return new_target

    def format_file(self, file: str) -> None:
        # open verilog source file
        target_str = fread(file)
        target_str = self._preprocess_target(target_str)
        target_lines = re.compile(r"\n").split(target_str)

        # new_target
        new_target: str = ""

        # format one line by one line
        for i in range(len(target_lines)):
            current = target_lines[i]
            self._judge_comment(current)
            current = self._create_indent(current)
            new_target += current + "\n"

        # reprocess
        new_target = self._reprocess_target(new_target)

        # rewrite file
        fwrite(file, new_target)

    def format(self, file_list: list[str]) -> None:
        # open verilog source file list
        for file in file_list:
            self.format_file(file)


if __name__ == "__main__":
    vf = VerilogFormatter()
    target_file = "test/_test_align.v"
    vf.format([target_file])
