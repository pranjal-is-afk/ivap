"""ANPR text validation — rejects OCR garbage, accepts real plate shapes."""
from app.pipeline.anpr import clean_plate_text, is_valid_indian_plate


def test_clean_strips_noise():
    assert clean_plate_text("mh 12 ab 1234") == "MH12AB1234"
    assert clean_plate_text("ka-01-ab-1234!!") == "KA01AB1234"
    assert clean_plate_text("") == ""


def test_valid_plates_pass():
    assert is_valid_indian_plate("MH12AB1234")
    assert is_valid_indian_plate("DL01CA1234")
    assert is_valid_indian_plate("KA01AB123")


def test_garbage_fails():
    assert not is_valid_indian_plate("12345678")  # no letters
    assert not is_valid_indian_plate("ABCDEFGH")  # no digits
    assert not is_valid_indian_plate("AB1")  # too short
    assert not is_valid_indian_plate("MH12AB123456789")  # too long
    assert not is_valid_indian_plate("")  # empty
    assert not is_valid_indian_plate("MH1A")  # too few digits


def test_ocr_common_confusion_shapes():
    # raw OCR often gives these; cleaned text still must respect shape rules
    assert not is_valid_indian_plate("MHI2AB123O")  # contains I, O → 11 chars anyway fails length? (10 chars, but I/O not stripped by clean)
