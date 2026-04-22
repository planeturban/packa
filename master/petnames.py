"""
Petname assignment for workers that register without a human-readable ID.
"""

import re

_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)

_WORDS = [
    "badger", "bat", "bear", "beaver", "bison", "boar", "buck", "bull",
    "capybara", "cheetah", "chipmunk", "cobra", "condor", "coyote", "crane",
    "crow", "deer", "dingo", "dolphin", "dove", "duck", "eagle", "elk",
    "falcon", "ferret", "finch", "flamingo", "fox", "frog", "gecko", "gopher",
    "gorilla", "grouse", "hawk", "heron", "hippo", "hornet", "hyena", "ibis",
    "jaguar", "jay", "kestrel", "kite", "koala", "lark", "lemur", "leopard",
    "lion", "lynx", "magpie", "marten", "mink", "moose", "moth", "mule",
    "newt", "osprey", "otter", "owl", "panda", "panther", "parrot", "puffin",
    "quail", "rabbit", "raven", "robin", "seal", "shrew", "skunk", "sloth",
    "snipe", "sparrow", "stag", "stork", "swan", "swift", "teal", "tiger",
    "toad", "toucan", "viper", "vole", "vulture", "weasel", "wolf", "wombat",
    "wren", "yak", "zebra",
]


def is_uuid(s: str) -> bool:
    return bool(_UUID_RE.match(s))


def pick(used: set[str]) -> str:
    for word in _WORDS:
        if word not in used:
            return word
    # All exhausted — append a number suffix
    i = 2
    for word in _WORDS:
        candidate = f"{word}{i}"
        if candidate not in used:
            return candidate
        i += 1
    return f"worker{len(used) + 1}"
