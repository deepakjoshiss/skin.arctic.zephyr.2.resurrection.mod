#!/usr/bin/env python3
"""Port the live v2 skinshortcuts menu (userdata) into v3 shortcuts/menus.xml."""
import os, re, json, html, collections

UD = os.path.expanduser('~/Library/Application Support/Kodi/userdata/addon_data/script.skinshortcuts')
JELLYCON_ICON = 'special://home/addons/plugin.video.jellycon/icon.png'

def shortcuts(path):
    if not os.path.exists(path): return []
    t = open(path, encoding='utf-8', errors='replace').read()
    out = []
    for m in re.finditer(r'<shortcut>(.*?)</shortcut>', t, re.S):
        b = m.group(1)
        g = lambda k: (re.search(r'<%s>(.*?)</%s>' % (k, k), b, re.S) or [None, ''])[1].strip()
        out.append({'defaultID': g('defaultID'), 'label': g('label'),
                    'icon': g('icon'), 'thumb': g('thumb'), 'action': g('action')})
    return out

def keys_in_order(group):
    """skinshortcuts item keys, in menu order, from the .properties file."""
    p = os.path.join(UD, 'skin.vinelec.properties')
    d = json.load(open(p, encoding='utf-8'))
    seen = []
    for row in d:
        if len(row) >= 2 and row[0] == group and row[1] not in seen:
            seen.append(row[1])
    return seen

def label_of(raw):
    if re.fullmatch(r'\d+', raw): return '$LOCALIZE[%s]' % raw
    m = re.match(r'\$SKIN\[(\d+)\|', raw)
    if m: return '$LOCALIZE[%s]' % m.group(1)
    return html.escape(raw, quote=False)

def art_of(s):
    """Prefer thumb, but drop machine-specific image:// paths."""
    t = s.get('thumb') or ''
    if t.startswith('image://') and 'jellycon' in t.lower(): return JELLYCON_ICON
    if t.startswith('image://'): t = ''
    if t and not t.endswith('/'): return t
    ic = s.get('icon') or ''
    return ic if ic and ic != 'DefaultShortcut.png' else ''

def dequote(action):
    """ActivateWindow(Videos,"plugin://...",return) -> unquoted form.

    skinshortcuts v3 derives <property name="path"> by stripping the
    ActivateWindow wrapper; leaving the quotes makes that path start with a
    literal " and Kodi then parses an empty addon id and segfaults."""
    return re.sub(r'(ActivateWindow\([^,]+,)"([^"]+)"', r'\1\2', action)

def unwrap(action):
    """ActivateWindow(Videos,"plugin://...",return) -> bare plugin url."""
    m = re.match(r'ActivateWindow\([^,]+,"?(.*?)"?(?:,return)?\)\s*$', action, re.S)
    return (m.group(1) if m else action).strip()

def slug(s, fallback):
    s = re.sub(r'[^A-Za-z0-9]+', '-', s).strip('-').lower()
    return s or fallback

def esc(x): return x  # values already XML-escaped in the v2 source

# ---- main menu -------------------------------------------------------
keys = keys_in_order('mainmenu')
items = shortcuts(os.path.join(UD, 'mainmenu.DATA.xml'))
assert len(keys) == len(items), (len(keys), len(items))

L = []
L.append('    <menu name="mainmenu" container="301">')
for key, s in zip(keys, items):
    sub = key if shortcuts(os.path.join(UD, '%s.DATA.xml' % key)) else None
    L.append('        <item name="%s"%s>' % (key, ' submenu="%s"' % key if sub else ''))
    L.append('            <label>%s</label>' % label_of(s['label']))
    if s['action']: L.append('            <action>%s</action>' % dequote(s['action']))
    a = art_of(s)
    if a: L.append('            <icon>%s</icon>' % esc(a))
    L.append('        </item>')
L.append('    </menu>')
mainmenu_block = '\n'.join(L)

# ---- submenus and widget lists --------------------------------------
subs = []
for key in keys:
    entries = shortcuts(os.path.join(UD, '%s.DATA.xml' % key))
    if entries:
        b = ['    <submenu name="%s">' % key]
        for i, s in enumerate(entries, 1):
            b.append('        <item name="%s">' % slug(s['label'], '%s-%d' % (key, i)))
            b.append('            <label>%s</label>' % label_of(s['label']))
            if s['action']: b.append('            <action>%s</action>' % dequote(s['action']))
            a = art_of(s)
            if a: b.append('            <icon>%s</icon>' % esc(a))
            b.append('        </item>')
        b.append('    </submenu>')
        subs.append('\n'.join(b))
    wid = shortcuts(os.path.join(UD, '%s-1.DATA.xml' % key))
    if wid:
        b = ['    <submenu name="%s.widgets" type="widgets">' % key]
        for i, s in enumerate(wid, 1):
            path = unwrap(s['action'])
            b.append('        <item name="%s">' % slug(s['label'], '%s-w%d' % (key, i)))
            b.append('            <label>%s</label>' % label_of(s['label']))
            a = art_of(s)
            if a: b.append('            <icon>%s</icon>' % esc(a))
            b.append('            <property name="widgetPath">%s</property>' % esc(path))
            b.append('            <property name="widgetTarget">videos</property>')
            b.append('        </item>')
        b.append('    </submenu>')
        subs.append('\n'.join(b))

# ---- splice into menus.xml ------------------------------------------
p = 'shortcuts/menus.xml'
t = open(p, encoding='utf-8').read()
t2, n = re.subn(r'    <menu name="mainmenu" container="301">.*?\n    </menu>',
                mainmenu_block, t, count=1, flags=re.S)
assert n == 1, 'mainmenu block not found'
t2 = t2.replace('</menus>', '\n    <!-- Ported from the live v2 menu -->\n'
                + '\n\n'.join(subs) + '\n</menus>')
open(p, 'w', encoding='utf-8').write(t2)
print("main menu items :", len(items))
print("submenus/widgets:", len(subs))
