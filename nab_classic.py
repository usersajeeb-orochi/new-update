# nab_classic.py — the original Tk window (kept as a fallback: NAB.exe --classic)
# NAB_entry.pyw — entry point, imports all modules
import os
import shutil
import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox, ttk, simpledialog, Menu, Canvas, Listbox, END, filedialog
from PIL import Image, ImageDraw, ImageFont, ImageGrab, ImageTk, ImageChops, ImageOps, ImageEnhance, ImageFilter
import datetime
import subprocess
import json
import sys
import threading
import time
import concurrent.futures
import zlib
import unicodedata
import re
import logging
import socket
import hashlib
import urllib.request as _urllib_req
import urllib.parse as _urllib_parse
import platform
import traceback
import io
import base64
import struct

# DPI awareness MUST be set before any Tk/CTk window exists, and
# nab_constants creates Tk objects at import time (the missing-file
# messagebox), so this has to come first.
import nab_ui_scale
nab_ui_scale.enable_dpi_awareness()

from nab_constants import *
import nab_constants as _nab_constants_mod
globals().update({k: v for k, v in vars(_nab_constants_mod).items() if not k.startswith('__')})
from nab_telegram import *
import nab_telegram as _nab_telegram_mod
globals().update({k: v for k, v in vars(_nab_telegram_mod).items() if not k.startswith('__')})
from nab_update import *
import nab_update as _nab_update_mod
globals().update({k: v for k, v in vars(_nab_update_mod).items() if not k.startswith('__')})
from nab_access import *
import nab_access as _nab_access_mod
globals().update({k: v for k, v in vars(_nab_access_mod).items() if not k.startswith('__')})
from nab_auth import *
import nab_auth as _nab_auth_mod
globals().update({k: v for k, v in vars(_nab_auth_mod).items() if not k.startswith('__')})
from nab_dialogs import *
import nab_dialogs as _nab_dialogs_mod
globals().update({k: v for k, v in vars(_nab_dialogs_mod).items() if not k.startswith('__')})
from nab_server import *
import nab_server as _nab_server_mod
globals().update({k: v for k, v in vars(_nab_server_mod).items() if not k.startswith('__')})
from nab_bubble import *
import nab_bubble as _nab_bubble_mod
globals().update({k: v for k, v in vars(_nab_bubble_mod).items() if not k.startswith('__')})
from nab_app import *
import nab_app as _nab_app_mod
globals().update({k: v for k, v in vars(_nab_app_mod).items() if not k.startswith('__')})


def run():
    try:
        NewsClipper().mainloop()
    except KeyboardInterrupt:
        pass
