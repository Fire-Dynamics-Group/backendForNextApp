# base file -> use a template word doce
# receive radiation data from frontend
# send back appendix word file
# LATER: image to be sent from frontend & inserted into word doc
import io
from pathlib import Path
from docxtpl import DocxTemplate


document_name = "Oil Pan Fire Appendix - Template.docx"
document_path = Path(__file__).parent /"Word Templates"/document_name
doc = DocxTemplate(document_path)

def fillWordDoc(CHIP_PAN_ALLOWED=True, HAS_CUSTOM_FIRE_SIZE=False):
    context = {
        "CHIP_PAN_ALLOWED": CHIP_PAN_ALLOWED,
        "HAS_CUSTOM_FIRE_SIZE": HAS_CUSTOM_FIRE_SIZE
    }

    doc.render(context)

    if __name__ == '__main__':
        doc.save("test_rad_doc.docx")

    bytes_io = io.BytesIO()
    doc.save(bytes_io)

    bytes_io.seek(0)    
    return bytes_io

fillWordDoc()