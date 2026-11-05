"""Small synthetic Office documents; never use uploaded corporate documents in tests."""

import io
from zipfile import ZipFile

import openpyxl


def native_document(extension: str) -> bytes:
    from PIL import Image
    stream = io.BytesIO()
    with Image.new("RGB", (200, 150), "white") as image:
        image.paste("black", (20, 20, 180, 130))
        image.save(stream, format={".pdf": "PDF", ".png": "PNG"}[extension])
    return stream.getvalue()


def office_document(extension: str) -> bytes:
    stream = io.BytesIO()
    if extension == ".xlsx":
        book = openpyxl.Workbook()
        book.active.append(["Local preview", "Operational reference"])
        book.active.append(["Contact", "Example team"])
        book.active["A2"].hyperlink = "https://example.invalid/reference"
        book.save(stream)
        book.close()
        return stream.getvalue()
    relationship_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    office_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with ZipFile(stream, "w") as archive:
        if extension == ".docx":
            part = "word/document.xml"
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
            archive.writestr(part, """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body><w:p><w:r><w:t>Local Word preview</w:t></w:r></w:p><w:sectPr/></w:body></w:document>""")
        elif extension == ".pptx":
            part = "ppt/presentation.xml"
            content_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
            archive.writestr(part, f"""<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="{office_ns}">
              <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
              <p:sldSz cx="9144000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>""")
            archive.writestr("ppt/_rels/presentation.xml.rels", f"""<Relationships xmlns="{relationship_ns}">
              <Relationship Id="rId1" Type="{office_ns}/slide" Target="slides/slide1.xml"/></Relationships>""")
            archive.writestr("ppt/slides/slide1.xml", """<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree>
              <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>
              <p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
              <p:spPr><a:xfrm><a:off x="500000" y="500000"/><a:ext cx="8000000" cy="1000000"/></a:xfrm>
              <a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
              <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="en-US"/><a:t>Local PowerPoint preview</a:t>
              </a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>""")
        else:
            raise ValueError("Unsupported synthetic Office fixture")
        archive.writestr("_rels/.rels", f"""<Relationships xmlns="{relationship_ns}">
          <Relationship Id="rId1" Type="{office_ns}/officeDocument" Target="{part}"/></Relationships>""")
        extra = ('<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
                 if extension == ".pptx" else "")
        archive.writestr("[Content_Types].xml", f"""<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
          <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
          <Default Extension="xml" ContentType="application/xml"/>
          <Override PartName="/{part}" ContentType="{content_type}"/>{extra}</Types>""")
    return stream.getvalue()
