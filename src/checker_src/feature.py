from enum import Enum


class ExpFeature(Enum):
    NoFeature = 0
    GrammarCall = 1
    Optional = 2
    Repeat = 3
    Branch = 4


def is_feature_exp(exp):
    return any(ch in exp for ch in ["|", "{", "@", "["])


def get_exp_features(exp):
    feature_map = {
        "|": ExpFeature.Branch,
        "{": ExpFeature.Repeat,
        "[": ExpFeature.Optional,
        "@": ExpFeature.GrammarCall,
    }
    for ch in exp:
        if ch in feature_map:
            return feature_map[ch]
    return ExpFeature.NoFeature