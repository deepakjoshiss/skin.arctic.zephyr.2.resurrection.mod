import xbmc
import xbmcgui

from constants import ADDON
from constants import ADDON_ID


class HomeWindow:
    """
        xbmcgui.Window(10000) with add-on id prefixed to keys
    """

    def __init__(self):
        self.id_string = ADDON_ID + '-%s'
        self.window = xbmcgui.Window(10000)

    def get_property(self, key):
        key = self.id_string % key
        value = self.window.getProperty(key)
        return value

    def set_property(self, key, value):
        key = self.id_string % key
        log(">>>>>>> generating fonts {0} key".format(key))
        self.window.setProperty(key, value)

    def clear_property(self, key):
        key = self.id_string % key
        self.window.clearProperty(key)

def log(txt):
        if isinstance(txt, bytes):
            txt = txt.decode('utf-8')

        message = '%s -- %s' % (ADDON_ID, txt)
        xbmc.log(msg=message, level=xbmc.LOGINFO)


def read_file(filename, mode='r'):
    encoding = None
    if 'b' not in mode:
        encoding = 'utf-8'
    with open(filename, mode, encoding=encoding) as file_handle:
        return file_handle.read()


def write_file(filename, contents, mode='w'):
    encoding = None
    if 'b' not in mode:
        encoding = 'utf-8'
    with open(filename, mode, encoding=encoding) as file_handle:
        file_handle.write(contents)
