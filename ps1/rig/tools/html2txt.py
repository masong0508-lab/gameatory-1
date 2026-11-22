#!/usr/bin/env python3
"""html2txt.py IN.html OUT.txt : plain text of the article part of a psx-spx page (pre blocks kept verbatim)."""
import sys
from html.parser import HTMLParser

class P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []; self.skip = 0; self.pre = 0; self.art = 0
    def handle_starttag(self, tag, attrs):
        if tag == 'article': self.art += 1
        if tag in ('script', 'style', 'nav', 'header', 'footer'): self.skip += 1
        if tag == 'pre': self.pre += 1; self.out.append('\n')
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5'): self.out.append('\n\n' + '#' * int(tag[1]) + ' ')
        if tag in ('p', 'br', 'li', 'tr', 'div'): self.out.append('\n')
        if tag in ('td', 'th'): self.out.append(' | ')
    def handle_endtag(self, tag):
        if tag == 'article': self.art -= 1
        if tag in ('script', 'style', 'nav', 'header', 'footer'): self.skip -= 1
        if tag == 'pre': self.pre -= 1; self.out.append('\n')
    def handle_data(self, data):
        if self.skip > 0 or self.art <= 0: return
        self.out.append(data if self.pre else ' '.join(data.split()) + (' ' if data[-1:].isspace() else ''))

p = P(); p.feed(open(sys.argv[1], encoding='utf-8', errors='replace').read())
t = ''.join(p.out)
import re
t = re.sub(r'\n{3,}', '\n\n', t)
open(sys.argv[2], 'w').write(t)
print(sys.argv[2], len(t))
