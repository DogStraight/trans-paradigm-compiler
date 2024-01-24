# the purpose of this file is :
#   generate token flow from text file and finish type mark

import pyv_config


class CharIterator:
    def __init__(self, file_path):
        self.file_path = file_path


    def __iter__(self):
        return self

    def __next__(self):
        with open(self.file_path,"r") as f:
            yield f.read(1)


class WordIterator:
    word: str
    last_separator_char: str

    def __init__(self, char_generator):
        self.word = ""
        self.last_separator_char = ""
        self.char_generator = char_generator

    def __iter__(self):
        return self

    def __next__(self):
        if self.last_separator_char:
            last_separator_char = self.last_separator_char
            self.last_separator_char = ""
            return last_separator_char
        for char in self.char_generator:
            if char in pyv_config.separator_char:
                if self.word:
                    word = self.word
                    self.last_separator_char = char
                    self.word = ""
                    return word
                else:
                    return char
            else:
                self.word += char


if __name__ == "__main__":
    char = CharIterator("tests/some_token_example.txt")
    word_iterator = WordIterator(char)
    for word in word_iterator:
        print(word)
