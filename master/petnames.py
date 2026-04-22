"""
Petname assignment for workers that register without a human-readable ID.
"""

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


def pick(used: set[str]) -> str:
    import random
    available = [w for w in _WORDS if w not in used]
    if available:
        return random.choice(available)
    i = 2
    while True:
        candidates = [f"{w}{i}" for w in _WORDS if f"{w}{i}" not in used]
        if candidates:
            return random.choice(candidates)
        i += 1
