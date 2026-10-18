"""Plain question text with explicit markup, preserving literal comparisons."""
from html.parser import HTMLParser
import re


class _Text(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.parts = []
        # Parsed platform questions already contain plain text plus img tags.
        # Only strip paired formatting markup, never arbitrary < y ... > math.
        self.paired = {tag.lower() for tag in re.findall(r'</(p|div|span|b|strong|em|i|u|sup|sub|code|pre|a)\s*>', source, re.I)}

    def handle_starttag(self, tag, attrs):
        if tag == 'br':
            self.parts.append('\n')
        elif tag != 'img' and tag not in self.paired:
            self.parts.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag not in self.paired:
            self.parts.append('</' + tag + '>')

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value):
    source = str(value)
    parser = _Text(source)
    parser.feed(source)
    parser.close()
    return ''.join(parser.parts)
