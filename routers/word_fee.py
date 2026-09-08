"""Fee proposal for the Word add-in task pane (fd-toolstation app/addin/word).

Deliberately self-contained (fee generator + python-docx only) so it can ship to master
ahead of the rest of the Word add-in backend (routers/word_addin.py).
"""
from io import BytesIO

from docx import Document
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from models.fee_proposal_models import FeeProposalRequest
from services.fee_document_service import generate_proposal

router = APIRouter()
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.post("/fee-proposal/render")
def render_fee_proposal(data: FeeProposalRequest):
    """The letter as a docx fragment for insertFileFromBase64.

    Word merges an inserted file's last paragraph into the paragraph it lands in, taking
    that paragraph's style, so a sacrificial empty paragraph is appended to absorb it.
    createDocument (the "New document" path) is unaffected by the extra paragraph.
    """
    try:
        doc = Document(generate_proposal(data))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    doc.add_paragraph("")
    out = BytesIO()
    doc.save(out)
    return Response(content=out.getvalue(), media_type=DOCX)
