"""Remove hidden PDF text without redacting visible content."""

from io import BytesIO

import pymupdf as fitz
from PIL import Image, ImageChops
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, NameObject, DictionaryObject, DecodedStreamObject


COMPACT_PDF_SAVE_OPTIONS = dict(garbage=4, deflate=True, deflate_images=True,
                                deflate_fonts=True, use_objstms=1)


def remove_page_annotations(page) -> None:
    """Remove PDF markup and links while keeping body text and form values."""
    for annotation in list(page.annots() or ()):
        page.delete_annot(annotation)
    for link in page.get_links():
        page.delete_link(link)


def insert_compact_background(target, pixmap) -> None:
    """Encode rebuilt pixels compactly; existing PDF images use the copy path."""
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    red, green, blue = image.split()
    if ImageChops.difference(red, green).getbbox() is None and ImageChops.difference(red, blue).getbbox() is None:
        image = red
        colors = image.getcolors(maxcolors=2)
        if colors is not None and all(color in (0, 255) for _count, color in colors):
            image = image.convert("1", dither=Image.Dither.NONE)
    png = BytesIO()
    image.save(png, format="PNG")
    data = png.getvalue()
    if image.mode != "1":
        jpeg = BytesIO()
        image.save(jpeg, format="JPEG", quality=95, optimize=True, subsampling=0)
        if jpeg.tell() < len(data):
            data = jpeg.getvalue()
    target.insert_image(target.rect, stream=data)


def strip_hidden_text(pdf_bytes: bytes) -> bytes:
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.append(reader)
    active_forms = set()

    def rewrite(container, resources, initial=(0, 1.0, 1.0)):
        resources = DictionaryObject(resources.get_object())
        xobjects = DictionaryObject(resources.get('/XObject', DictionaryObject()).get_object())
        resources[NameObject('/XObject')] = xobjects
        state = initial
        stack = []
        contents = container.get('/Contents') if container.get('/Type') == '/Page' else container
        if contents is None:
            return
        stream = ContentStream(contents, writer)
        output = []
        pending_advance = False
        in_text = False
        for operands, operator in stream.operations:
            if operator == b'q':
                stack.append(state)
            elif operator == b'Q':
                state = stack.pop() if stack else initial
            elif operator == b'BT':
                in_text = True
            elif operator == b'ET':
                in_text = False
            elif operator == b'Tr':
                state = (int(operands[0]), state[1], state[2])
            elif operator == b'gs':
                ext = resources.get('/ExtGState', DictionaryObject()).get_object().get(operands[0])
                if ext is not None:
                    ext = ext.get_object()
                    state = (state[0], float(ext.get('/ca', state[1])), float(ext.get('/CA', state[2])))
            if operator in (b'BT', b'Td', b'TD', b'Tm', b'T*', b"'", b'"'):
                pending_advance = False
            if operator == b'Do':
                obj = xobjects.get(operands[0])
                if obj is not None:
                    obj = obj.get_object()
                    if obj.get('/Subtype') == '/Form':
                        if id(obj) in active_forms:
                            raise ValueError('PDF 包含循环引用的 Form，无法清理隐藏文字。')
                        active_forms.add(id(obj))
                        rewritten = rewrite(obj, obj.get('/Resources', resources), state)
                        active_forms.remove(id(obj))
                        name = NameObject(f'/CWForm{len(xobjects)}')
                        xobjects[name] = writer._add_object(rewritten)
                        operands = [name]
            if in_text and operator in (b'Tj', b'TJ', b"'", b'"'):
                mode, fill, stroke = state
                hidden = mode == 3 or (mode == 0 and fill <= 1e-6) or (mode == 1 and stroke <= 1e-6) or (mode == 2 and max(fill, stroke) <= 1e-6)
                if hidden:
                    if operator == b'"':
                        output.extend([([operands[0]], b'Tw'), ([operands[1]], b'Tc')])
                    if operator in (b"'", b'"'):
                        output.append(([], b'T*'))
                    else:
                        pending_advance = True
                    continue
                if pending_advance:
                    raise ValueError('隐藏文字与可见文字共用连续字距；请使用栅格化模式重新识别此页。')
            output.append((operands, operator))
        stream.operations = output
        if container.get('/Type') == '/Page':
            container[NameObject('/Contents')] = writer._add_object(stream)
            container[NameObject('/Resources')] = resources
        else:
            result = DecodedStreamObject()
            result.update({key: value for key, value in container.items() if key not in ('/Filter', '/DecodeParms', '/Length', '/Resources')})
            result[NameObject('/Resources')] = resources
            result.set_data(stream.get_data())
            return result

    for page in writer.pages:
        rewrite(page, page.get('/Resources', DictionaryObject()))
    result = BytesIO()
    writer.write(result)
    return result.getvalue()


def searchable_background(target, source, page_index: int, *, dpi: int = 144,
                          remove_annotations: bool = True) -> None:
    """Keep the page picture, with exactly one extractable OCR text layer."""
    page = source[page_index]
    if remove_annotations:
        remove_page_annotations(page)
    visible = any(trace['type'] in (0, 1) and trace.get('opacity', 1) > 0 for trace in page.get_texttrace())
    if visible or page.first_widget is not None or page.first_annot is not None:
        # Render before removing any text: native text must stay in the picture.
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        insert_compact_background(target, pix)
    else:
        with fitz.open() as single:
            single.insert_pdf(source, from_page=page_index, to_page=page_index)
            with fitz.open(stream=strip_hidden_text(single.tobytes()), filetype='pdf') as clean:
                clean[0].clean_contents()
                if clean[0].get_text().strip():
                    # Clipping text contributes to the picture and cannot be
                    # deleted as a text-show instruction. Preserve its pixels.
                    pix = page.get_pixmap(dpi=dpi, alpha=False)
                    insert_compact_background(target, pix)
                elif clean[0].get_bboxlog():
                    # Map the unrotated crop box into the displayed orientation.
                    rotation = clean[0].rotation
                    clean[0].set_rotation(0)
                    target.show_pdf_page(target.rect, clean, 0, rotate=-rotation)
