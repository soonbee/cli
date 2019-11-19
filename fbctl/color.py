DEFAULT = '\033[39m'
BLACK = '\033[30m'
RED = '\033[31m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
BLUE = '\033[34m'
MAGENTA = '\033[35m'
CYAN = '\033[36m'
LIGHTGRAY = '\033[37m'
DARKGRAY = '\033[90m'
LIGHTRED = '\033[91m'
LIGHTGREEN = '\033[92m'
LIGHTYELLOW = '\033[93m'
LIGHTBLUE = '\033[94m'
LIGHTMAGENTA = '\033[95m'
LIGHTCYAN = '\033[96m'
WHITE = '\033[97m'

ENDC = '\033[0m'
BOLD = '\033[1m'
UNDERLINE = '\033[4m'


def green(msg):
    return GREEN + msg + ENDC


def red(msg):
    return RED + msg + ENDC


def yellow(msg):
    return YELLOW + msg + ENDC


def blue(msg):
    return BLUE + msg + ENDC


def cyan(msg):
    return CYAN + msg + ENDC


def magenta(msg):
    return MAGENTA + msg + ENDC


def white(msg):
    return WHITE + msg + ENDC
