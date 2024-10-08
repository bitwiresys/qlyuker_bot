import ctypes

# Define necessary structures for console handling
class COORD(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class SMALL_RECT(ctypes.Structure):
    _fields_ = [("Left", ctypes.c_short), ("Top", ctypes.c_short),
                ("Right", ctypes.c_short), ("Bottom", ctypes.c_short)]


class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
    _fields_ = [("dwSize", COORD),
                ("dwCursorPosition", COORD),
                ("wAttributes", ctypes.c_ushort),
                ("srWindow", SMALL_RECT),
                ("dwMaximumWindowSize", COORD)]


# Function to set console size
def set_console_size(width, height):
    # Get the standard output handle (console)
    hConsole = ctypes.windll.kernel32.GetStdHandle(-11)

    # Structure to hold screen buffer info
    csbi = CONSOLE_SCREEN_BUFFER_INFO()
    ctypes.windll.kernel32.GetConsoleScreenBufferInfo(hConsole, ctypes.byref(csbi))

    # Adjust the console window size
    rect = SMALL_RECT()
    rect.Left = 0
    rect.Top = 0
    rect.Right = width - 1  # Set the width
    rect.Bottom = height - 1  # Set the height
    ctypes.windll.kernel32.SetConsoleWindowInfo(hConsole, ctypes.c_bool(True), ctypes.byref(rect))

    # Adjust the buffer size
    size = COORD(width, height)
    ctypes.windll.kernel32.SetConsoleScreenBufferSize(hConsole, size)


# Function to adjust console width based on string length
def adjust_console_width_for_string(s):
    # Get the current console height
    hConsole = ctypes.windll.kernel32.GetStdHandle(-11)
    csbi = CONSOLE_SCREEN_BUFFER_INFO()
    ctypes.windll.kernel32.GetConsoleScreenBufferInfo(hConsole, ctypes.byref(csbi))
    current_height = csbi.srWindow.Bottom - csbi.srWindow.Top + 1

    # Get the length of the string
    string_length = len(s)

    # Adjust console width if string is longer than current console width
    current_width = csbi.srWindow.Right - csbi.srWindow.Left + 1
    if string_length > current_width:
        set_console_size(string_length + 2, current_height)  # +2 for some padding


# Function to print a string and adjust console size
def print_s(s):
    adjust_console_width_for_string(s)  # Adjust the console width before printing
    print(s)