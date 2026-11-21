"""Unit tests for PDF classification policy."""

def classify_pdf_counts(total_pages: int, text_pages: int, size_mb: float, max_mb: float = 20.0):
    if size_mb > max_mb:
        return "too_large"
    if text_pages == total_pages and total_pages > 0:
        return "text"
    if text_pages == 0:
        return "image"
    return "mixed"

def test_pdf_classification():
    assert classify_pdf_counts(5, 5, 2.0) == "text"
    assert classify_pdf_counts(5, 0, 1.5) == "image"
    assert classify_pdf_counts(5, 3, 4.0) == "mixed"
    assert classify_pdf_counts(10, 10, 25.0) == "too_large"

if __name__ == "__main__":
    test_pdf_classification()
    print("test_pdf_classify: ALL PASSED")
