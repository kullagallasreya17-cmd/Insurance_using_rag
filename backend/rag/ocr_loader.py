from pathlib import Path

from langchain_core.documents import Document


def load_image_document(file_path: Path):
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "OCR dependencies are missing. Install pillow and pytesseract."
        ) from exc

    text = pytesseract.image_to_string(Image.open(file_path)).strip()
    if not text:
        raise RuntimeError("No readable text was found in the uploaded image.")

    return [
        Document(
            page_content=text,
            metadata={
                "source": str(file_path),
                "page": 1,
            },
        )
    ]
