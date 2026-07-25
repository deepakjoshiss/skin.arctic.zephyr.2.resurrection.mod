#!/usr/bin/env python3
"""
Static validator for the VinELEC Kodi skin.

Kodi fails *silently* on most skin mistakes: a misspelled include, a missing
$VAR, an undefined colour or font, a texture path that does not exist. The
control simply does not render and nothing is logged. This script turns those
silent failures into errors you can iterate against.

Everything is regex-based rather than DOM-based on purpose: two files in this
repo are not well-formed XML, and the checks still need to run on them.

Usage:
    python3 tools/lint.py                 # check, honouring the baseline
    python3 tools/lint.py --all           # ignore the baseline, show everything
    python3 tools/lint.py --json          # machine-readable
    python3 tools/lint.py --update-baseline

Exit codes: 0 = no new findings, 1 = new findings, 2 = bad invocation.
"""

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(ROOT, 'tools', 'lint-baseline.txt')

# Skin XML lives in 1080i/; colours and shortcut definitions live alongside.
XML_DIRS = ['1080i', 'colors', 'shortcuts']

# Files Kodi's helper add-ons generate at runtime. They are gitignored and must
# never be hand-edited, but they DO define includes/variables the hand-written
# XML refers to, so they still count as definition sources.
GENERATED = {
    'script-skinshortcuts-includes.xml',
    'script-skinvariables-includes.xml',
    'script-skinviewtypes-includes.xml',
}

# Tags whose text content is a texture path.
TEXTURE_TAGS = [
    'texture', 'texturefocus', 'texturenofocus', 'texturefocusdown',
    'alttexturefocus', 'alttexturenofocus', 'bordertexture', 'texturebg',
    'lefttexture', 'righttexture', 'midtexture', 'overlaytexture',
    'textureradioonfocus', 'textureradioonnofocus', 'textureradioofffocus',
    'textureradiooffnofocus', 'texturesliderbar', 'texturesliderbarfocus',
    'texturesliderbackground', 'textureslidernib', 'textureslidernibfocus',
    'textureup', 'texturedown', 'textureupfocus', 'texturedownfocus',
    'icon', 'thumb',
]

# Tags whose text content is a colour name or literal AARRGGBB.
COLOR_TAGS = [
    'textcolor', 'focusedcolor', 'disabledcolor', 'selectedcolor',
    'shadowcolor', 'colordiffuse', 'invalidcolor', 'bordercolor',
    'titlecolor', 'headlinecolor', 'textcolorfocus', 'midtexturecolor',
]

# Kodi reserves 31000-31999 for skin strings; everything else resolves against
# Kodi's own strings.po, which we only check when a Kodi install is found.
SKIN_STRING_LO, SKIN_STRING_HI = 31000, 31999

KODI_CANDIDATES = [
    '/Applications/Kodi.app/Contents/Resources/Kodi',
    os.path.expanduser('~/Applications/Kodi.app/Contents/Resources/Kodi'),
    '/usr/share/kodi',
    '/usr/local/share/kodi',
]


def find_kodi():
    env = os.environ.get('KODI_PATH')
    if env and os.path.isdir(env):
        return env
    for p in KODI_CANDIDATES:
        if os.path.isdir(p):
            return p
    return None


def blank_comments(text):
    """Remove XML comments but keep line numbering intact."""
    def repl(m):
        return re.sub(r'[^\n]', ' ', m.group(0))
    return re.sub(r'<!--.*?-->', repl, text, flags=re.S)


def line_of(text, pos):
    return text.count('\n', 0, pos) + 1


def xbt_names(path):
    """Extract texture names from a compiled .xbt bundle.

    The XBT file table stores fixed-width null-padded paths, so scanning for
    image-looking strings recovers the name set without parsing the frame
    records. Used only to *suppress* missing-texture findings, so erring
    towards over-matching is the safe direction.
    """
    try:
        with open(path, 'rb') as fh:
            data = fh.read()
    except OSError:
        return set()
    pat = rb'[\w\-./ ]{3,120}\.(?:png|jpg|jpeg|gif)'
    return {m.decode('utf-8', 'replace') for m in re.findall(pat, data)}


class Linter:
    def __init__(self, root):
        self.root = root
        self.findings = []
        self.files = {}          # relpath -> comment-blanked text
        self.raw = {}            # relpath -> original text
        self.kodi = find_kodi()
        self._load()

    # -- loading ---------------------------------------------------------

    def _load(self):
        for d in XML_DIRS:
            full = os.path.join(self.root, d)
            if not os.path.isdir(full):
                continue
            for name in sorted(os.listdir(full)):
                if not name.endswith('.xml'):
                    continue
                rel = os.path.join(d, name)
                with open(os.path.join(full, name), encoding='utf-8',
                          errors='replace') as fh:
                    text = fh.read()
                self.raw[rel] = text
                self.files[rel] = blank_comments(text)

    def add(self, rule, relpath, line, message):
        self.findings.append({
            'rule': rule,
            'file': relpath,
            'line': line,
            'message': message,
        })

    def hand_written(self):
        """Files a human or agent actually edits."""
        return {k: v for k, v in self.files.items()
                if os.path.basename(k) not in GENERATED}

    # -- definition collection -------------------------------------------

    def collect(self):
        allt = '\n'.join(self.files.values())
        self.inc_defs = set(re.findall(r'<include\s+name="([^"]+)"', allt))
        self.var_defs = set(re.findall(r'<variable\s+name="([^"]+)"', allt))
        self.const_defs = set(re.findall(r'<constant\s+name="([^"]+)"', allt))

        # Font definitions are NOT confined to Font.xml -- e.g. the lyrics
        # fontset is declared inline in Includes_VideoLyrics.xml.
        self.font_defs = set()
        for m in re.finditer(r'<font>\s*<name>([^<]+)</name>', allt):
            self.font_defs.add(m.group(1).strip())
        for m in re.finditer(r'<name>([^<$]+)</name>\s*<filename>', allt):
            self.font_defs.add(m.group(1).strip())

        # Colours: this skin's palettes plus Kodi's built-in named colours.
        self.color_defs = set()
        cdir = os.path.join(self.root, 'colors')
        if os.path.isdir(cdir):
            for name in os.listdir(cdir):
                if name.endswith('.xml'):
                    with open(os.path.join(cdir, name), encoding='utf-8',
                              errors='replace') as fh:
                        self.color_defs |= set(
                            re.findall(r'<color name="([^"]+)"', fh.read()))
        self.core_colors = set()
        if self.kodi:
            core = os.path.join(self.kodi, 'system', 'colors.xml')
            if os.path.isfile(core):
                with open(core, encoding='utf-8', errors='replace') as fh:
                    self.core_colors = set(
                        re.findall(r'<color name="([^"]+)"', fh.read()))

        # Textures: loose files under media/ and themes/*, plus .xbt bundles.
        # Kodi resolves texture paths case-insensitively (TexturePacker
        # lowercases every name when building an .xbt), so the whole set is
        # normalised to lowercase and lookups are too.
        self.texture_names = set()
        for base in [os.path.join(self.root, 'media')] + [
                os.path.join(self.root, 'themes', t)
                for t in _listdir(os.path.join(self.root, 'themes'))]:
            if not os.path.isdir(base):
                continue
            for dirpath, _, names in os.walk(base):
                for n in names:
                    rel = os.path.relpath(os.path.join(dirpath, n), base)
                    self.texture_names.add(rel.replace(os.sep, '/').lower())
        for dirpath, _, names in os.walk(os.path.join(self.root, 'media')):
            for n in names:
                if n.endswith('.xbt'):
                    self.texture_names |= {
                        x.lower() for x in xbt_names(os.path.join(dirpath, n))}

        # Localised strings.
        self.string_ids = set()
        po = os.path.join(self.root, 'language', 'resource.language.en_gb',
                          'strings.po')
        if os.path.isfile(po):
            with open(po, encoding='utf-8', errors='replace') as fh:
                self.string_ids = {int(x) for x in
                                   re.findall(r'msgctxt "#(\d+)"', fh.read())}

    # -- checks ----------------------------------------------------------

    def check_wellformed(self):
        for rel, text in self.raw.items():
            try:
                ET.fromstring(text)
            except ET.ParseError as exc:
                line = exc.position[0] if exc.position else 0
                self.add('xml-parse', rel, line,
                         'not well-formed XML: %s' % exc.msg
                         if hasattr(exc, 'msg') else str(exc))

    def check_includes(self):
        for rel, text in self.hand_written().items():
            for m in re.finditer(
                    r'<include(?![\w])([^>]*?)(?:/>|>([^<]*)</include>)', text):

                attrs, body = m.group(1), (m.group(2) or '')
                if 'file=' in attrs:
                    continue
                names = []
                c = re.search(r'content="([^"]+)"', attrs)
                if c:
                    names.append(c.group(1))
                if body.strip():
                    names.append(body.strip())
                for name in names:
                    if '$' in name:          # runtime-built name, unresolvable
                        continue
                    if name not in self.inc_defs:
                        self.add('unknown-include', rel, line_of(text, m.start()),
                                 'no <include name="%s"> anywhere' % name)

    def check_refs(self, pattern, defs, rule, label):
        for rel, text in self.hand_written().items():
            for m in re.finditer(pattern, text):
                name = m.group(1).strip()
                if '$' in name or not name:
                    continue
                if name not in defs:
                    self.add(rule, rel, line_of(text, m.start()),
                             'no %s named "%s"' % (label, name))

    def check_fonts(self):
        for rel, text in self.hand_written().items():
            for m in re.finditer(r'<font>([^<$]+)</font>', text):
                name = m.group(1).strip()
                if name and name not in self.font_defs:
                    self.add('unknown-font', rel, line_of(text, m.start()),
                             'font "%s" is not defined in any fontset' % name)
        # Font files a fontset points at must exist. <filename> is relative to
        # the skin's fonts/ dir (e.g. "lyrics/BOXING.ttf"), and Kodi also
        # supplies a couple of its own (arial.ttf, teletext.ttf).
        on_disk = set()
        fdir = os.path.join(self.root, 'fonts')
        if os.path.isdir(fdir):
            for dirpath, _, names in os.walk(fdir):
                for n in names:
                    rel = os.path.relpath(os.path.join(dirpath, n), fdir)
                    on_disk.add(rel.replace(os.sep, '/').lower())
        if self.kodi:
            kfonts = os.path.join(self.kodi, 'media', 'Fonts')
            if os.path.isdir(kfonts):
                on_disk |= {n.lower() for n in os.listdir(kfonts)}
        for rel, text in self.files.items():
            for m in re.finditer(r'<filename>([^<$]+)</filename>', text):
                fn = m.group(1).strip()
                if fn and fn.lower() not in on_disk:
                    self.add('missing-font-file', rel, line_of(text, m.start()),
                             'font file "%s" not found in fonts/ or Kodi\'s '
                             'own font dir' % fn)

    def check_colors(self):
        known = self.color_defs | self.core_colors
        literal = re.compile(r'^[0-9a-fA-F]{6,8}$')
        for rel, text in self.hand_written().items():
            for tag in COLOR_TAGS:
                pat = r'<%s(?:\s[^>]*)?>([^<]+)</%s>' % (tag, tag)
                for m in re.finditer(pat, text):
                    val = m.group(1).strip()
                    if not val or '$' in val or literal.match(val):
                        continue
                    if val not in known:
                        self.add('unknown-color', rel, line_of(text, m.start()),
                                 '<%s>%s</%s> is not a skin or Kodi colour'
                                 % (tag, val, tag))

    def check_textures(self):
        skip_prefix = ('special://', 'resource://', 'http://', 'https://',
                       'image://', 'DefaultFolder', '$')
        for rel, text in self.hand_written().items():
            for tag in TEXTURE_TAGS:
                pat = r'<%s(?:\s[^>]*)?>([^<]+)</%s>' % (tag, tag)
                for m in re.finditer(pat, text):
                    val = m.group(1).strip()
                    if not val or val == '-' or '$' in val:
                        continue
                    if val.startswith(skip_prefix):
                        continue
                    if val.lower() in self.texture_names:
                        continue
                    # Paths are relative to media/; "../x" escapes to skin root.
                    resolved = os.path.normpath(
                        os.path.join(self.root, 'media', val))
                    if os.path.isfile(resolved):
                        continue
                    self.add('missing-texture', rel, line_of(text, m.start()),
                             'texture "%s" not found in media/, themes/ or any '
                             '.xbt bundle' % val)

    def check_strings(self):
        for rel, text in self.hand_written().items():
            for m in re.finditer(r'\$LOCALIZE\[(\d+)\]', text):
                sid = int(m.group(1))
                if not (SKIN_STRING_LO <= sid <= SKIN_STRING_HI):
                    continue      # Kodi core string, not ours to define
                if sid not in self.string_ids:
                    self.add('missing-string', rel, line_of(text, m.start()),
                             '$LOCALIZE[%d] has no msgctxt "#%d" in '
                             'language/resource.language.en_gb/strings.po'
                             % (sid, sid))

    def check_duplicates(self):
        for kind, pat in (('include', r'<include\s+name="([^"]+)"'),
                          ('variable', r'<variable\s+name="([^"]+)"'),
                          ('constant', r'<constant\s+name="([^"]+)"')):
            seen = {}
            # Hand-written only: the generated includes are *derived* from
            # shortcuts/skinvariables.xml, so comparing the two always collides.
            for rel, text in self.hand_written().items():
                for m in re.finditer(pat, text):
                    name = m.group(1)
                    where = (rel, line_of(text, m.start()))
                    if name in seen:
                        first = seen[name]
                        self.add('duplicate-definition', where[0], where[1],
                                 '%s "%s" already defined at %s:%d'
                                 % (kind, name, first[0], first[1]))
                    else:
                        seen[name] = where

    def run(self):
        self.collect()
        self.check_wellformed()
        self.check_includes()
        self.check_refs(r'\$VAR\[([^\],]+)', self.var_defs,
                        'unknown-variable', 'variable')
        self.check_refs(r'\$CONST\[([^\]]+)\]', self.const_defs,
                        'unknown-constant', 'constant')
        self.check_fonts()
        self.check_colors()
        self.check_textures()
        self.check_strings()
        self.check_duplicates()
        self.findings.sort(key=lambda f: (f['file'], f['line'], f['rule']))
        return self.findings


def _listdir(path):
    try:
        return os.listdir(path)
    except OSError:
        return []


def key(f):
    """Baseline key, deliberately excluding the line number so that unrelated
    edits shifting a file around do not resurrect a known finding."""
    return '%s|%s|%s' % (f['rule'], f['file'], f['message'])


def load_baseline():
    if not os.path.isfile(BASELINE):
        return set()
    with open(BASELINE, encoding='utf-8') as fh:
        return {ln.rstrip('\n') for ln in fh
                if ln.strip() and not ln.startswith('#')}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--all', action='store_true',
                    help='report every finding, including baselined ones')
    ap.add_argument('--json', action='store_true', help='machine-readable output')
    ap.add_argument('--update-baseline', action='store_true',
                    help='record all current findings as accepted')
    args = ap.parse_args()

    linter = Linter(ROOT)
    findings = linter.run()

    if args.update_baseline:
        with open(BASELINE, 'w', encoding='utf-8') as fh:
            fh.write('# Pre-existing lint findings, accepted as of this commit.\n')
            fh.write('# Regenerate: python3 tools/lint.py --update-baseline\n')
            fh.write('# Anything NOT listed here is a regression.\n')
            for k in sorted({key(f) for f in findings}):
                fh.write(k + '\n')
        print('baseline updated: %d findings recorded' % len({key(f) for f in findings}))
        return 0

    baseline = set() if args.all else load_baseline()
    new = [f for f in findings if key(f) not in baseline]

    if args.json:
        print(json.dumps({'new': new, 'total': len(findings),
                          'baselined': len(findings) - len(new)}, indent=2))
        return 1 if new else 0

    if not new:
        print('lint: clean (%d baselined findings suppressed)'
              % (len(findings)))
        if not linter.kodi:
            print('note: no Kodi install found; colour checks skipped Kodi '
                  'built-ins. Set KODI_PATH to enable.')
        return 0

    by_rule = {}
    for f in new:
        by_rule.setdefault(f['rule'], []).append(f)
    for rule in sorted(by_rule):
        print('\n%s (%d)' % (rule, len(by_rule[rule])))
        for f in by_rule[rule]:
            print('  %s:%d  %s' % (f['file'], f['line'], f['message']))
    print('\n%d new finding(s); %d suppressed by baseline'
          % (len(new), len(findings) - len(new)))
    return 1


if __name__ == '__main__':
    sys.exit(main())
