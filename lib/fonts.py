import xbmc

from constants import ADDON, SKIN_PATH, ADDON_ID
from common import log
import xml.etree.ElementTree as ET

def generatefonts():
    log(">>>>>>> generating fonts")
    tree = ET.parse(SKIN_PATH +'/1080i/Font.xml')
    root = tree.getroot()
    for child in root:
        log(">>>>>>>> tag is {0}".format(child.tag))
        if(child.tag == 'fontset'):
            log(">>>>>>>> atte is {0}".format(child.attrib))
            if(child.attrib.get('id') == 'Default'):
                log(">>>>>>>> got child {0}".format(child.attrib))
                # child.set('id', "Defultnew")
                for font in child.findall('font'):
                    name = font.find('name').text
                    # log(">>>>>>>> found font {0}".format(name))
                    if(name == 'font_topbar_medium'):
                        size = font.find('size')
                        size.text = '46'
            else: 
                log(">>>>>>>> remove child{0}".format(child.attrib))
                child.tag = 'oldfontset'
    for oldset in root.findall('oldfontset'):
        root.remove(oldset)

        roboto = ET.Element('fontset')
        roboto.set('id', oldset.get('id'))
        roboto.set('unicode', 'true')
        to_font = ET.SubElement(roboto, 'font')
        name = ET.SubElement(to_font, 'name')
        name.text = 'font_topbar_small'
        filename = ET.SubElement(to_font, 'filename')
        filename.text = 'arialbd.ttf'
        size = ET.SubElement(to_font, 'size')
        size.text = '44'
        root.append(roboto)
    
    ET.indent(tree, space='    ', level=0)
    # Removed file writing
    # tree.write(SKIN_PATH +'/1080i/Font.xml')

