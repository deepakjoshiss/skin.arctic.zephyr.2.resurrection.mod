import xbmc

from constants import ADDON
from constants import ADDON_ID


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
