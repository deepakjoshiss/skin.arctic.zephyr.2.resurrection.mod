#!/usr/bin/env python3
"""
Drive the running Kodi instance so a skin change can actually be *seen*.

This repo IS the installed skin -- editing a file under 1080i/ changes the
live UI as soon as the skin reloads. That makes a closed loop possible:

    edit XML  ->  tools/kodi.py reload  ->  tools/kodi.py shot  ->  look at the PNG

Talks to Kodi's JSON-RPC over the local TCP socket (port 9090), which is
enabled by default via Settings > Services > Control > "Allow programs on this
system to control Kodi". No HTTP web server or password required.

Commands:
    check              is Kodi up, which skin is loaded, which window is showing
    reload             reload the skin, then report any new errors in the log
    shot [name]        capture a screenshot, print its path
    go <window>        activate a window (Home, Videos, Settings, ...)
    log [n]            last n skin-relevant log lines (default 40)
    errors [n]         only errors/warnings worth reading
    rpc <method> [json-params]     raw JSON-RPC escape hatch
"""

import argparse
import difflib
import json
import os
import re
import socket
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_ID = 'skin.vinelec'
SHOT_DIR = os.path.join(ROOT, '.dev', 'screenshots')

HOST = os.environ.get('KODI_RPC_HOST', '127.0.0.1')
PORT = int(os.environ.get('KODI_RPC_PORT', '9090'))

LOG_CANDIDATES = [
    os.path.expanduser('~/Library/Logs/kodi.log'),
    os.path.expanduser('~/.kodi/temp/kodi.log'),
    os.path.expanduser('~/Library/Application Support/Kodi/temp/kodi.log'),
]

# Third-party add-on chatter that drowns out anything skin-related.
NOISE = re.compile(
    r'left several classes in memory'
    r'|is deprecated and might be removed'
    r'|CPythonInvoker'
    r'|Skipped \d+ duplicate messages',
)


class RpcError(Exception):
    pass


def rpc(method, params=None, timeout=10):
    payload = json.dumps({'jsonrpc': '2.0', 'id': 1,
                          'method': method, 'params': params or {}})
    try:
        sock = socket.create_connection((HOST, PORT), timeout)
    except OSError as exc:
        raise RpcError(
            'cannot reach Kodi JSON-RPC at %s:%d (%s).\n'
            'Is Kodi running? Enable Settings > Services > Control >\n'
            '"Allow programs on this system to control Kodi".' % (HOST, PORT, exc))
    try:
        sock.sendall(payload.encode())
        sock.settimeout(timeout)
        buf = b''
        while True:
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
            try:
                return json.loads(buf.decode())
            except ValueError:
                continue          # response spans multiple reads
    finally:
        sock.close()
    if not buf:
        raise RpcError('no response from Kodi for %s' % method)
    return json.loads(buf.decode())


def result_of(method, params=None):
    resp = rpc(method, params)
    if 'error' in resp:
        raise RpcError('%s: %s' % (method, json.dumps(resp['error'])))
    return resp.get('result')


def log_path():
    for p in LOG_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def read_log_from(offset=0):
    p = log_path()
    if not p:
        return '', 0
    with open(p, encoding='utf-8', errors='replace') as fh:
        fh.seek(offset)
        text = fh.read()
        return text, fh.tell()


def log_size():
    p = log_path()
    return os.path.getsize(p) if p else 0


SKIN_TROUBLE = re.compile(
    r'unable to load|failed to load|error loading|missing.*(texture|font)'
    r'|invalid.*(control|include)|unknown control|could not create control'
    r'|texture.*not found|error parsing|unmatched|<skin>',
    re.I)


def interesting(lines, level='errors'):
    out = []
    for ln in lines:
        if not ln.strip() or NOISE.search(ln):
            continue
        if level == 'errors':
            if re.search(r'\s(error|fatal)\s|<general>: Error', ln, re.I):
                out.append(ln)
            elif 'warning' in ln.lower() and re.search(
                    r'skin|include|texture|font|control|xml', ln, re.I):
                out.append(ln)
        else:
            out.append(ln)
    return out


def split_skin_errors(lines):
    """Separate 'the skin itself is broken' from ambient add-on chatter.

    A reload almost always logs weather/scraper/shortcut errors that have
    nothing to do with the edit being tested, so only genuine skin-loading
    failures should fail the command.
    """
    skin, ambient = [], []
    for ln in lines:
        (skin if SKIN_TROUBLE.search(ln) else ambient).append(ln)
    return skin, ambient


# -- commands -----------------------------------------------------------

def cmd_check(args):
    try:
        ver = result_of('JSONRPC.Version')
    except RpcError as exc:
        print('DOWN: %s' % exc)
        return 1
    props = result_of('GUI.GetProperties',
                      {'properties': ['currentwindow', 'skin', 'fullscreen']})
    print('kodi json-rpc : %s:%d (api %s)'
          % (HOST, PORT, ver['version']['major']))
    print('active skin   : %s (%s)'
          % (props['skin']['name'], props['skin']['id']))
    if props['skin']['id'] != ADDON_ID:
        print('  WARNING: %s is not the active skin -- your edits will not show'
              % ADDON_ID)
    print('current window: %s (id %s)'
          % (props['currentwindow']['label'], props['currentwindow']['id']))
    lp = log_path()
    print('log file      : %s' % (lp or 'not found'))
    return 0


def cmd_reload(args):
    before = log_size()
    result_of('Addons.ExecuteAddon',
              {'addonid': ADDON_ID, 'params': ['reload=true']})
    # Wait for the skin to come back up rather than guessing at a sleep.
    deadline = time.time() + 20
    while time.time() < deadline:
        time.sleep(0.6)
        text, _ = read_log_from(before)
        if 'Loading skin file: Home.xml' in text or 'Skin Loaded' in text:
            break
    else:
        print('reload requested, but no skin-load marker appeared in the log')
    time.sleep(1.0)
    text, _ = read_log_from(before)
    skin, ambient = split_skin_errors(interesting(text.splitlines(), 'errors'))
    if skin:
        print('reloaded WITH SKIN ERRORS (%d):' % len(skin))
        for ln in skin[-args.lines:]:
            print('  ' + ln.strip())
    else:
        print('reloaded; no skin errors')
    if ambient:
        print('(%d unrelated add-on/runtime line(s); '
              'see tools/kodi.py errors)' % len(ambient))
    return 1 if skin else 0


def cmd_shot(args):
    os.makedirs(SHOT_DIR, exist_ok=True)
    result_of('Settings.SetSettingValue',
              {'setting': 'debug.screenshotpath', 'value': SHOT_DIR + os.sep})
    existing = set(os.listdir(SHOT_DIR))
    result_of('Input.ExecuteAction', {'action': 'screenshot'})
    deadline = time.time() + 10
    new = None
    while time.time() < deadline:
        time.sleep(0.4)
        found = set(os.listdir(SHOT_DIR)) - existing
        found = {f for f in found if f.lower().endswith('.png')}
        if found:
            new = os.path.join(SHOT_DIR, sorted(found)[-1])
            # Wait for the write to settle.
            size = -1
            while size != os.path.getsize(new):
                size = os.path.getsize(new)
                time.sleep(0.2)
            break
    if not new:
        print('no screenshot appeared in %s' % SHOT_DIR)
        return 1
    if args.name:
        dest = os.path.join(SHOT_DIR, args.name
                            if args.name.endswith('.png')
                            else args.name + '.png')
        os.replace(new, dest)
        new = dest
    print(new)
    return 0


def valid_windows():
    """The window names GUI.ActivateWindow accepts, straight from Kodi."""
    try:
        schema = result_of('JSONRPC.Introspect',
                           {'filter': {'id': 'GUI.ActivateWindow',
                                       'type': 'method'}})
        # The param is a $ref; the actual enum lives in the type table.
        return schema['types']['GUI.Window']['enums']
    except (RpcError, KeyError, TypeError):
        return []


def cmd_go(args):
    # Kodi's enum is lowercase ("home", "videos", "skinsettings").
    window = args.window.lower()
    # "parameters" must be a non-empty array of non-empty strings, so it is
    # omitted entirely rather than padded when there is nothing to pass.
    params = {'window': window}
    if args.parameters:
        params['parameters'] = args.parameters
    try:
        result_of('GUI.ActivateWindow', params)
    except RpcError:
        names = valid_windows()
        near = difflib.get_close_matches(window, names, n=6, cutoff=0.6)
        print('unknown window %r.' % args.window, file=sys.stderr)
        if near:
            print('did you mean: %s' % ', '.join(near[:10]), file=sys.stderr)
        elif names:
            print('valid: %s ...' % ', '.join(names[:25]), file=sys.stderr)
        return 1
    time.sleep(1.0)
    props = result_of('GUI.GetProperties', {'properties': ['currentwindow']})
    print('now showing: %s (id %s)' % (props['currentwindow']['label'],
                                       props['currentwindow']['id']))
    return 0


def cmd_log(args):
    text, _ = read_log_from(0)
    lines = [ln for ln in text.splitlines()
             if ln.strip() and not NOISE.search(ln)]
    for ln in lines[-args.lines:]:
        print(ln)
    return 0


def cmd_errors(args):
    text, _ = read_log_from(0)
    bad = interesting(text.splitlines(), 'errors')
    if not bad:
        print('no errors in %s' % (log_path() or 'log'))
        return 0
    for ln in bad[-args.lines:]:
        print(ln)
    return 0


def cmd_rpc(args):
    params = json.loads(args.params) if args.params else None
    print(json.dumps(rpc(args.method, params), indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd')

    sub.add_parser('check').set_defaults(fn=cmd_check)

    p = sub.add_parser('reload')
    p.add_argument('-n', '--lines', type=int, default=20)
    p.set_defaults(fn=cmd_reload)

    p = sub.add_parser('shot')
    p.add_argument('name', nargs='?', help='save as this filename')
    p.set_defaults(fn=cmd_shot)

    p = sub.add_parser('go')
    p.add_argument('window')
    p.add_argument('parameters', nargs='*')
    p.set_defaults(fn=cmd_go)

    p = sub.add_parser('log')
    p.add_argument('lines', nargs='?', type=int, default=40)
    p.set_defaults(fn=cmd_log)

    p = sub.add_parser('errors')
    p.add_argument('lines', nargs='?', type=int, default=40)
    p.set_defaults(fn=cmd_errors)

    p = sub.add_parser('rpc')
    p.add_argument('method')
    p.add_argument('params', nargs='?')
    p.set_defaults(fn=cmd_rpc)

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return 2
    try:
        return args.fn(args)
    except RpcError as exc:
        print('error: %s' % exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
