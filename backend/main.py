import os
import csv
import io
import tempfile
from pathlib import Path

import anthropic
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

app = FastAPI(title="Requirements Extractor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SUPPORTED_TYPES = {
    "text/plain",
    "text/markdown",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/rtf",
    "text/rtf",
}


def extract_text(file_bytes: bytes, content_type: str, filename: str) -> str:
    """Extract plain text from the uploaded file."""
    ext = Path(filename).suffix.lower()

    if content_type == "application/pdf" or ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if content_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ) or ext in (".docx", ".doc"):
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs)

    # Plain text / markdown / rtf (treat rtf as plain text fallback)
    return file_bytes.decode("utf-8", errors="replace")


SYSTEM_PROMPT = """You are an expert requirements analyst. Your task is to extract all requirements from the provided document and return them as a structured list.

For each requirement you identify:
1. Assign a unique ID (REQ-001, REQ-002, etc.)
2. Identify the type: Functional, Non-Functional, Constraint, or Business
3. Write a concise title (5-10 words)
4. Write the full requirement description
5. Assign a priority: High, Medium, or Low

Return ONLY a valid CSV with these exact columns (no extra text before or after):
id,type,title,description,priority

Rules:
- Escape any commas inside fields by wrapping the field in double quotes
- Escape internal double quotes by doubling them ("")
- Every row must have exactly 5 fields
- Do not include markdown formatting or code fences
- Extract ALL requirements, both explicit and implicit"""


@app.post("/api/extract")
async def extract_requirements(file: UploadFile = File(...)):
    if file.content_type not in SUPPORTED_TYPES and not file.filename.endswith(
        (".txt", ".md", ".pdf", ".docx", ".doc", ".rtf")
    ):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}",
        )

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    try:
        document_text = extract_text(file_bytes, file.content_type or "", file.filename or "")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read file: {e}")

    if not document_text.strip():
        raise HTTPException(status_code=422, detail="File appears to be empty or unreadable")

    # Truncate very long documents to avoid context limits
    if len(document_text) > 80_000:
        document_text = document_text[:80_000] + "\n\n[Document truncated for processing]"

    try:
        with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Extract all requirements from the following document:\n\n{document_text}",
                }
            ],
        ) as stream:
            response = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid Anthropic API key")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="Rate limit exceeded, please try again later")
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {e}")

    csv_text = next(
        (block.text for block in response.content if block.type == "text"),
        "",
    ).strip()

    # Validate the CSV has at least a header + one row
    lines = [l for l in csv_text.splitlines() if l.strip()]
    if len(lines) < 2:
        raise HTTPException(
            status_code=500,
            detail="Model returned no requirements. Try with a different document.",
        )

    # Stream CSV back to the client
    output = io.BytesIO(csv_text.encode("utf-8"))
    stem = Path(file.filename or "document").stem
    out_filename = f"{stem}_requirements.csv"

    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{out_filename}"'},
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}
