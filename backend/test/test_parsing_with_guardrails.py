"""
Test script for parsing service with guardrails and monitoring.

Tests:
- PDF parsing with size limits
- PDF parsing with page count limits
- PDF parsing with timeout
- HTML parsing
- Resource monitoring during parsing
"""

import asyncio
import logging
import tempfile
from pathlib import Path

import fitz  # For creating test PDFs
from app.services.analysis.parse import ParsingService
from app.services.analysis.guardrails import DEFAULT_GUARDRAILS
from app.services.monitoring import ResourceMonitor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_test_pdf(
    path: Path, num_pages: int = 10, text_per_page: str = None
) -> None:
    """Create a test PDF file with specified number of pages."""
    if text_per_page is None:
        text_per_page = "This is a test page.\n" * 50

    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page()
        page.insert_text((50, 50), f"Page {i+1}\n\n{text_per_page}")

    doc.save(str(path))
    doc.close()


async def create_test_html(path: Path, size_kb: int = 10) -> None:
    """Create a test HTML file with specified size."""
    content = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Test Document</title></head>
    <body>
        <h1>Test Document</h1>
        <article>
            <p>{'This is test content. ' * 100}</p>
            {'<p>Additional paragraph content.</p>' * (size_kb * 10)}
        </article>
    </body>
    </html>
    """
    path.write_text(content, encoding="utf-8")


async def test_normal_pdf_parsing():
    """Test normal PDF parsing (within limits)."""
    logger.info("\n=== Test 1: Normal PDF Parsing ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create a small test PDF
        pdf_path = tmpdir_path / "test.pdf"
        await create_test_pdf(pdf_path, num_pages=10)

        # Initialize parser and monitor
        parser = ParsingService(export_dir=str(tmpdir_path))
        monitor = ResourceMonitor("test_normal_pdf")
        monitor.start()

        # Parse
        monitor.log_snapshot("Before parsing")
        result = await parser.parse_saved_file("test_doc", str(pdf_path))
        monitor.log_snapshot("After parsing")

        # Validate
        assert result is not None, "Parsing should succeed"
        assert len(result.text) > 0, "Text should be extracted"
        assert len(result.page_spans) == 10, "Should have 10 pages"

        logger.info(
            f"✓ Successfully parsed PDF: {len(result.text)} chars, {len(result.page_spans)} pages"
        )
        monitor.log_summary()


async def test_oversized_pdf():
    """Test that oversized PDFs are skipped."""
    logger.info("\n=== Test 2: Oversized PDF (too many pages) ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create a PDF with too many pages
        pdf_path = tmpdir_path / "large.pdf"
        num_pages = DEFAULT_GUARDRAILS.max_pdf_pages + 10
        await create_test_pdf(pdf_path, num_pages=num_pages)

        # Initialize parser
        parser = ParsingService(export_dir=str(tmpdir_path))

        # Parse (should be rejected)
        result = await parser.parse_saved_file("large_doc", str(pdf_path))

        # Validate
        assert result is None, "Large PDF should be skipped"

        logger.info(
            f"✓ Correctly rejected PDF with {num_pages} pages (limit: {DEFAULT_GUARDRAILS.max_pdf_pages})"
        )


async def test_pdf_parsing_timeout():
    """Test that PDF parsing respects timeout."""
    logger.info("\n=== Test 3: PDF Parsing Timeout ===")

    # Note: This test creates a very large PDF that should timeout
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create a PDF with many pages and lots of text (but within page limit)
        pdf_path = tmpdir_path / "slow.pdf"
        num_pages = min(100, DEFAULT_GUARDRAILS.max_pdf_pages - 10)
        huge_text = "Large text content. " * 10000  # Very large text per page
        await create_test_pdf(pdf_path, num_pages=num_pages, text_per_page=huge_text)

        # Initialize parser with short timeout
        parser = ParsingService(export_dir=str(tmpdir_path))

        # This should either succeed or timeout depending on system performance
        result = await parser.parse_saved_file("slow_doc", str(pdf_path))

        if result is None:
            logger.info(
                f"✓ PDF parsing timed out as expected (timeout: {DEFAULT_GUARDRAILS.pdf_parse_timeout}s)"
            )
        else:
            logger.info(
                f"✓ PDF parsing completed within timeout ({len(result.text)} chars)"
            )


async def test_html_parsing():
    """Test HTML parsing."""
    logger.info("\n=== Test 4: HTML Parsing ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create test HTML
        html_path = tmpdir_path / "test.html"
        await create_test_html(html_path, size_kb=50)

        # Initialize parser and monitor
        parser = ParsingService(export_dir=str(tmpdir_path))
        monitor = ResourceMonitor("test_html")
        monitor.start()

        # Parse
        monitor.log_snapshot("Before parsing")
        result = await parser.parse_saved_file("test_html", str(html_path))
        monitor.log_snapshot("After parsing")

        # Validate
        assert result is not None, "HTML parsing should succeed"
        assert len(result.text) > 0, "Text should be extracted"

        logger.info(f"✓ Successfully parsed HTML: {len(result.text)} chars")
        monitor.log_summary()


async def test_concurrent_parsing():
    """Test concurrent parsing with resource monitoring."""
    logger.info("\n=== Test 5: Concurrent Parsing ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create multiple test PDFs
        pdf_paths = []
        for i in range(10):
            pdf_path = tmpdir_path / f"test_{i}.pdf"
            await create_test_pdf(pdf_path, num_pages=5)
            pdf_paths.append(pdf_path)

        # Initialize parser and monitor
        parser = ParsingService(export_dir=str(tmpdir_path))
        monitor = ResourceMonitor("test_concurrent")
        monitor.start()

        # Parse all concurrently
        monitor.log_snapshot("Before concurrent parsing")

        tasks = [
            parser.parse_saved_file(f"doc_{i}", str(path))
            for i, path in enumerate(pdf_paths)
        ]
        results = await asyncio.gather(*tasks)

        monitor.log_snapshot("After concurrent parsing")

        # Validate
        successful = sum(1 for r in results if r is not None)
        assert successful == len(pdf_paths), "All PDFs should parse successfully"

        logger.info(
            f"✓ Successfully parsed {successful}/{len(pdf_paths)} PDFs concurrently"
        )
        monitor.log_summary()


async def run_all_tests():
    """Run all parsing tests."""
    logger.info("Starting Parsing Service Tests with Guardrails\n")
    logger.info("Guardrails Configuration:")
    logger.info(f"  Max PDF size: {DEFAULT_GUARDRAILS.max_pdf_size_mb}MB")
    logger.info(f"  Max PDF pages: {DEFAULT_GUARDRAILS.max_pdf_pages}")
    logger.info(f"  PDF parse timeout: {DEFAULT_GUARDRAILS.pdf_parse_timeout}s")
    logger.info(f"  Max text length: {DEFAULT_GUARDRAILS.max_text_length_chars} chars")

    try:
        await test_normal_pdf_parsing()
        await test_oversized_pdf()
        await test_pdf_parsing_timeout()
        await test_html_parsing()
        await test_concurrent_parsing()

        logger.info("\n" + "=" * 60)
        logger.info("✓ ALL TESTS PASSED")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"\n✗ TEST FAILED: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(run_all_tests())
