import ast
import base64
import copy
import hashlib
import io
import re
import struct
from collections.abc import Mapping
from urllib.parse import unquote
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

from odoo.tools.safe_eval import safe_eval


DRAW_NS = "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
MANIFEST_NS = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
SVG_NS = "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
TABLE_NS = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
XLINK_NS = "http://www.w3.org/1999/xlink"

NS = {
    "draw": DRAW_NS,
    "table": TABLE_NS,
    "text": TEXT_NS,
    "xlink": XLINK_NS,
}

LOOP_RE = re.compile(r'^for=["\']([A-Za-z_]\w*)\s+in\s+(.+)["\']$')
FUNCTION_RE = re.compile(r'^py3o://function=["\'](.+)["\']$')
IMAGE_TYPES = {
    "gif": "image/gif",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "svg": "image/svg+xml",
    "svg+xml": "image/svg+xml",
}
MEASUREMENT_RE = re.compile(r'^([+-]?(?:\d+(?:\.\d*)?|\.\d+))([a-zA-Z]+)$')


class AttrDict(dict):
    """Mapping that supports the dotted access used in ODT template fields."""

    __getattr__ = dict.__getitem__


def _template_value(value):
    if isinstance(value, Mapping) and not isinstance(value, AttrDict):
        return AttrDict((key, _template_value(item)) for key, item in value.items())
    if isinstance(value, list):
        return [_template_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_template_value(item) for item in value)
    return value


def _evaluate(expression, context):
    return safe_eval(expression, context, mode="eval")


def _directive(node):
    href = unquote(node.get(etree.QName(XLINK_NS, "href"), ""))
    if not href.startswith("py3o://"):
        return None
    directive = href[len("py3o://"):]
    if directive == "/for":
        return "end", None
    match = LOOP_RE.match(directive)
    if match:
        return "for", match.groups()
    return None


def _append_text(parent, index, value):
    if not value:
        return
    if index:
        sibling = parent[index - 1]
        sibling.tail = (sibling.tail or "") + value
    else:
        parent.text = (parent.text or "") + value


def _replace_inline(node, value):
    parent = node.getparent()
    index = parent.index(node)
    tail = node.tail or ""
    parent.remove(node)

    is_markup = hasattr(value, "__html__")
    value = "" if value is None or value is False else str(value)
    if is_markup:
        try:
            wrapper = etree.fromstring(
                f'<root xmlns:text="{TEXT_NS}">{value}</root>'.encode()
            )
        except etree.XMLSyntaxError:
            _append_text(parent, index, value)
        else:
            _append_text(parent, index, wrapper.text)
            for child in list(wrapper):
                wrapper.remove(child)
                parent.insert(index, child)
                index += 1
    else:
        _append_text(parent, index, value)

    _append_text(parent, index, tail)


def _image_dimensions(data, file_type):
    if file_type == 'png' and data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) >= 24:
        return struct.unpack('>II', data[16:24])
    if file_type == 'gif' and data[:6] in {b'GIF87a', b'GIF89a'} and len(data) >= 10:
        return struct.unpack('<HH', data[6:10])
    if file_type in {'jpg', 'jpeg'} and data.startswith(b'\xff\xd8'):
        offset = 2
        start_of_frame = {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
        }
        while offset + 9 <= len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            marker = data[offset + 1]
            if marker in start_of_frame:
                height, width = struct.unpack('>HH', data[offset + 5:offset + 9])
                return width, height
            if marker in {0xD8, 0xD9}:
                offset += 2
                continue
            if offset + 4 > len(data):
                break
            segment_length = struct.unpack('>H', data[offset + 2:offset + 4])[0]
            if segment_length < 2:
                break
            offset += segment_length + 2
    if file_type in {'svg', 'svg+xml'}:
        try:
            root = etree.fromstring(data)
        except etree.XMLSyntaxError:
            return None
        view_box = root.get('viewBox')
        if view_box:
            values = view_box.replace(',', ' ').split()
            if len(values) == 4:
                return float(values[2]), float(values[3])
        width = MEASUREMENT_RE.match(root.get('width', ''))
        height = MEASUREMENT_RE.match(root.get('height', ''))
        if width and height:
            return float(width.group(1)), float(height.group(1))
    return None


def _scale_measurement(measurement, factor):
    match = MEASUREMENT_RE.match(str(measurement))
    if not match:
        return None
    return f'{float(match.group(1)) * factor:.3f}{match.group(2)}'


class OdtTemplateRenderer:
    def __init__(self, content, context, images=None):
        self.root = etree.fromstring(content)
        self.context = {
            key: _template_value(value)
            for key, value in context.items()
        }
        self.images = images if images is not None else []

    def render(self):
        self._render_loops()
        self._render_fields(self.root, self.context)
        self._render_functions(self.root, self.context)
        self._render_images(self.root, self.context)
        return etree.tostring(
            self.root,
            encoding="UTF-8",
            xml_declaration=True,
        )

    def _render_loops(self):
        while True:
            start_link = next((
                link
                for link in self.root.xpath('.//text:a', namespaces=NS)
                if (_directive(link) or (None,))[0] == "for"
            ), None)
            if start_link is None:
                return

            _, (variable, expression) = _directive(start_link)
            start_rows = start_link.xpath('ancestor::table:table-row[1]', namespaces=NS)
            if not start_rows:
                raise ValueError("An ODT for directive must be placed in a table row")
            start_row = start_rows[0]
            parent = start_row.getparent()
            rows = list(parent)
            start_index = rows.index(start_row)

            end_index = None
            for index, row in enumerate(rows[start_index + 1:], start_index + 1):
                directives = [
                    _directive(link)
                    for link in row.xpath('.//text:a', namespaces=NS)
                ]
                if any(item and item[0] == "end" for item in directives):
                    end_index = index
                    break
            if end_index is None:
                raise ValueError("An ODT for directive is missing its closing /for row")

            template_rows = rows[start_index + 1:end_index]
            values = _evaluate(expression, self.context) or []
            insertion_index = start_index
            for value in values:
                local_context = dict(self.context, **{variable: _template_value(value)})
                for template_row in template_rows:
                    rendered_row = copy.deepcopy(template_row)
                    self._render_fields(rendered_row, local_context)
                    self._render_functions(rendered_row, local_context)
                    self._render_images(rendered_row, local_context)
                    parent.insert(insertion_index, rendered_row)
                    insertion_index += 1

            for row in rows[start_index:end_index + 1]:
                parent.remove(row)

    def _render_fields(self, root, context):
        fields = root.xpath('.//text:user-field-get', namespaces=NS)
        if root.tag == etree.QName(TEXT_NS, "user-field-get"):
            fields.insert(0, root)
        for field in fields:
            name = field.get(etree.QName(TEXT_NS, "name"), "")
            if name.startswith("py3o."):
                _replace_inline(field, _evaluate(name[len("py3o."):], context))

    def _render_functions(self, root, context):
        inputs = root.xpath('.//text:text-input', namespaces=NS)
        if root.tag == etree.QName(TEXT_NS, "text-input"):
            inputs.insert(0, root)
        for input_node in inputs:
            description = input_node.get(etree.QName(TEXT_NS, "description"), "")
            match = FUNCTION_RE.match(description)
            if match:
                _replace_inline(input_node, _evaluate(match.group(1), context))

    def _render_images(self, root, context):
        frames = root.xpath('.//draw:frame[starts-with(@draw:name, "py3o.image(")]', namespaces=NS)
        if root.tag == etree.QName(DRAW_NS, "frame"):
            name = root.get(etree.QName(DRAW_NS, "name"), "")
            if name.startswith("py3o.image("):
                frames.insert(0, root)

        for frame in frames:
            expression = frame.get(etree.QName(DRAW_NS, "name"))
            call = ast.parse(expression, mode="eval").body
            if not isinstance(call, ast.Call) or len(call.args) < 2:
                raise ValueError(f"Invalid ODT image expression: {expression}")

            data = _evaluate(ast.unparse(call.args[0]), context)
            file_type = str(_evaluate(ast.unparse(call.args[1]), context)).lower()
            options = {
                keyword.arg: _evaluate(ast.unparse(keyword.value), context)
                for keyword in call.keywords
                if keyword.arg
            }
            if not data:
                frame.attrib.clear()
                for child in list(frame):
                    frame.remove(child)
                etree.SubElement(frame, etree.QName(DRAW_NS, "image"))
                continue
            if options.get("isb64"):
                data = base64.b64decode(data)
            elif isinstance(data, str):
                data = data.encode()

            extension = "svg" if file_type == "svg+xml" else file_type
            if extension not in IMAGE_TYPES:
                raise ValueError(f"Unsupported ODT image type: {file_type}")
            data = bytes(data)
            image_path = f"Pictures/{hashlib.sha256(data).hexdigest()}"
            if not any(path == image_path for path, _data, _media_type in self.images):
                self.images.append((image_path, data, IMAGE_TYPES[file_type]))

            if options.get("height"):
                frame.set(etree.QName(SVG_NS, "height"), str(options["height"]))
            if options.get("width"):
                frame.set(etree.QName(SVG_NS, "width"), str(options["width"]))
            dimensions = _image_dimensions(data, file_type)
            if options.get("keep_ratio") and dimensions:
                width, height = dimensions
                if width and height and options.get("height") and not options.get("width"):
                    scaled_width = _scale_measurement(options["height"], width / height)
                    if scaled_width:
                        frame.set(etree.QName(SVG_NS, "width"), scaled_width)
                elif width and height and options.get("width") and not options.get("height"):
                    scaled_height = _scale_measurement(options["width"], height / width)
                    if scaled_height:
                        frame.set(etree.QName(SVG_NS, "height"), scaled_height)
            for child in list(frame):
                frame.remove(child)
            image = etree.SubElement(frame, etree.QName(DRAW_NS, "image"))
            image.set(etree.QName(XLINK_NS, "href"), image_path)
            image.set(etree.QName(XLINK_NS, "type"), "simple")


def _add_images_to_manifest(manifest, images):
    root = etree.fromstring(manifest)
    existing_paths = {
        node.get(etree.QName(MANIFEST_NS, "full-path"))
        for node in root
    }
    for path, _data, media_type in images:
        if path in existing_paths:
            continue
        entry = etree.SubElement(root, etree.QName(MANIFEST_NS, "file-entry"))
        entry.set(etree.QName(MANIFEST_NS, "full-path"), path)
        entry.set(etree.QName(MANIFEST_NS, "media-type"), media_type)
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True)


def render_odt_template(template, context):
    """Render the field, table-loop and image markers used by our ODT files."""
    source = io.BytesIO(template)
    target = io.BytesIO()
    with ZipFile(source) as input_zip:
        images = []
        rendered_members = {}
        for member in ("content.xml", "styles.xml"):
            renderer = OdtTemplateRenderer(input_zip.read(member), context, images=images)
            rendered_members[member] = renderer.render()
        manifest = _add_images_to_manifest(
            input_zip.read("META-INF/manifest.xml"),
            images,
        )

        infos = input_zip.infolist()
        existing_members = {info.filename for info in infos}
        infos.sort(key=lambda info: info.filename != "mimetype")
        with ZipFile(target, "w") as output_zip:
            for info in infos:
                data = input_zip.read(info.filename)
                if info.filename in rendered_members:
                    data = rendered_members[info.filename]
                elif info.filename == "META-INF/manifest.xml":
                    data = manifest
                output_zip.writestr(info, data)
            for path, data, _media_type in images:
                if path not in existing_members:
                    output_zip.writestr(path, data, compress_type=ZIP_DEFLATED)
    return target.getvalue()
