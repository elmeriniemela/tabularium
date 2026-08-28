import re

from lxml import etree, html


BULLETS = '*+-'
DROP_TAGS = frozenset({'head', 'script', 'style', 'template'})
WHITESPACE_RE = re.compile(r'\s+')
EXCESS_BLANK_LINES_RE = re.compile(r'\n{3,}')


def _text(value):
    value = WHITESPACE_RE.sub(' ', value or '')
    return value.replace('*', r'\*').replace('_', r'\_')


def _chomp(value):
    prefix = ' ' if value.startswith(' ') else ''
    suffix = ' ' if value.endswith(' ') else ''
    return prefix, suffix, value.strip()


def _children(element):
    parts = [_text(element.text)]
    for child in element:
        parts.append(_render(child))
        parts.append(_text(child.tail))
    return ''.join(parts)


def _inline_markup(value, marker):
    prefix, suffix, value = _chomp(value)
    if not value:
        return ''
    return f'{prefix}{marker}{value}{marker}{suffix}'


def _title_part(title):
    if not title:
        return ''
    escaped_title = title.replace('"', r'\"')
    return f' "{escaped_title}"'


def _list_depth(element):
    depth = -1
    current = element
    while current is not None:
        if current.tag == 'ul':
            depth += 1
        current = current.getparent()
    return depth


def _list_item(element, value):
    value = value.strip()
    if not value:
        return '\n'

    parent = element.getparent()
    if parent is not None and parent.tag == 'ol':
        start = parent.get('start', '1')
        start = int(start) if start.isnumeric() else 1
        preceding_items = len(element.xpath('preceding-sibling::li'))
        bullet = f'{start + preceding_items}. '
    else:
        bullet = f'{BULLETS[_list_depth(parent) % len(BULLETS)]} '

    indent = ' ' * len(bullet)
    lines = value.splitlines()
    rendered = [f'{bullet}{lines[0]}']
    rendered.extend(f'{indent}{line}' if line else '' for line in lines[1:])
    return '\n'.join(rendered) + '\n'


def _render(element):
    tag = element.tag.lower() if isinstance(element.tag, str) else ''
    if tag in DROP_TAGS:
        return ''

    value = _children(element)
    if tag == 'a':
        prefix, suffix, label = _chomp(value)
        if not label:
            return ''
        href = element.get('href')
        title = element.get('title')
        unescaped_label = label.replace(r'\*', '*').replace(r'\_', '_')
        if href and unescaped_label == href and not title:
            return f'<{href}>'
        if not href:
            return label
        return f'{prefix}[{label}]({href}{_title_part(title)}){suffix}'
    if tag in {'b', 'strong'}:
        return _inline_markup(value, '**')
    if tag in {'em', 'i'}:
        return _inline_markup(value, '*')
    if tag in {'del', 's', 'strike'}:
        return _inline_markup(value, '~~')
    if tag in {'code', 'kbd', 'samp'}:
        return _inline_markup(value, '`')
    if tag == 'br':
        return '  \n'
    if tag in {'div', 'p', 'article', 'section'}:
        value = value.strip()
        return f'\n\n{value}\n\n' if value else ''
    if tag in {'ul', 'ol'}:
        value = value.rstrip()
        if element.getparent() is not None and element.getparent().tag == 'li':
            return f'\n{value}'
        return f'\n\n{value}\n'
    if tag == 'li':
        return _list_item(element, value)
    if tag in {'h1', 'h2'}:
        value = value.strip()
        underline = '=' if tag == 'h1' else '-'
        return f'\n\n{value}\n{underline * len(value)}\n\n' if value else ''
    if tag in {'h3', 'h4', 'h5', 'h6'}:
        value = WHITESPACE_RE.sub(' ', value).strip()
        return f'\n\n{"#" * int(tag[1])} {value}\n\n' if value else ''
    if tag == 'blockquote':
        value = value.strip()
        quoted = '\n'.join(f'> {line}' if line else '>' for line in value.splitlines())
        return f'\n{quoted}\n\n' if quoted else ''
    if tag == 'pre':
        value = ''.join(element.itertext()).strip('\n')
        return f'\n\n```\n{value}\n```\n\n' if value else ''
    if tag == 'hr':
        return '\n\n---\n\n'
    if tag == 'img':
        source = element.get('src') or ''
        alt = element.get('alt') or ''
        return f'![{alt}]({source}{_title_part(element.get("title"))})'
    return value


def html_to_markdown(value):
    """Convert an HTML fragment to stable Markdown for readable diffs."""
    if not value or not value.strip():
        return ''
    try:
        root = html.fragment_fromstring(value, create_parent='div')
    except (etree.ParserError, etree.XMLSyntaxError, ValueError):
        return value
    markdown = _children(root).replace('\xa0', ' ')
    markdown = EXCESS_BLANK_LINES_RE.sub('\n\n', markdown)
    return markdown.strip()
