"""PDF export. The pure layers (options, colors, print CSS, geometry) and the
pypdf imposition are tested without a browser; the full Chromium master render is
exercised by one end-to-end test that skips when Chromium isn't installed.
"""

import importlib.util
import io

import pytest

from lectern.config import PdfConfig
from lectern.errors import ConfigError
from lectern.pdf import colors, geometry, impose, options, printcss

# The pure layers (options/colors/printcss/geometry) need nothing extra; the
# imposition tests need the [pdf] extra (pypdf + reportlab), and the e2e test
# additionally needs a Chromium browser. Both degrade to skips when absent.
_HAVE_PDF_LIBS = all(
    importlib.util.find_spec(m) is not None for m in ("pypdf", "reportlab")
)
needs_pdf_libs = pytest.mark.skipif(
    not _HAVE_PDF_LIBS, reason="pdf extra (pypdf/reportlab) not installed"
)


# --------------------------------------------------------------------------- #
# cache location (lives under build_dir, not out_dir)
# --------------------------------------------------------------------------- #
def test_cache_dir_under_build_dir(tmp_path):
    from lectern.config import Config
    from lectern.pdf.pipeline import _cache_dir

    cfg = Config(build_dir="build")
    assert _cache_dir(tmp_path, cfg) == tmp_path / "build" / ".lectern-cache"
    # a custom (relative) build_dir is honored, resolved against the deck root
    assert _cache_dir(tmp_path, Config(build_dir="cache")).parent.name == "cache"


# --------------------------------------------------------------------------- #
# options
# --------------------------------------------------------------------------- #
def test_defaults_resolve():
    o = options.resolve(PdfConfig())
    assert o.layout == "2up-notes" and o.color == "color" and o.backgrounds is True
    assert o.tagged is True  # tagged PDF on by default


def test_ink_saver_expands():
    o = options.resolve(PdfConfig(ink_saver=True))
    assert o.bw is True and o.backgrounds is False and o.light_inverse is True


def test_4up_normalizes_to_2x2():
    assert options.resolve(PdfConfig(layout="4up")).layout == "2x2"


def test_invalid_option_raises():
    with pytest.raises(ConfigError):
        options.resolve(PdfConfig(layout="9up"))
    with pytest.raises(ConfigError):
        options.resolve(PdfConfig(color="sepia"))


# --------------------------------------------------------------------------- #
# colors (token grayscale)
# --------------------------------------------------------------------------- #
def test_parse_and_gray_extremes():
    assert colors.to_gray("#ffffff") == "#ffffff"
    assert colors.to_gray("#000000") == "#000000"
    assert colors.to_gray("not-a-color") is None
    # shorthand hex expands
    assert colors.to_gray("#fff") == "#ffffff"


def test_gray_is_monotonic_in_luminance():
    # a brighter color maps to a lighter gray
    light = int(colors.to_gray("#cccccc")[1:3], 16)
    dark = int(colors.to_gray("#333333")[1:3], 16)
    assert light > dark


def test_distinct_hues_stay_distinct():
    # teal accent vs near-white bg become clearly different grays (not mud)
    bg = colors.to_gray("#fbfbfd")
    accent = colors.to_gray("#0e7c86")
    assert bg != accent
    assert int(bg[1:3], 16) > int(accent[1:3], 16)


def test_gray_token_overrides_from_theme():
    css = ":root { --bg: #fbfbfd; --accent: #0e7c86; --font-body: Inter; }"
    grays = colors.gray_token_overrides(css)
    assert set(grays) == {"--bg", "--accent"}  # the font token is not a color


# --------------------------------------------------------------------------- #
# print stylesheet
# --------------------------------------------------------------------------- #
_THEME = ":root { --bg: #ffffff; --fg: #111111; --accent: #0e7c86; }"


def test_plain_color_master_has_no_print_css():
    assert printcss.build(options.resolve(PdfConfig()), _THEME) == ""


def test_no_backgrounds_hides_and_flips_inverse():
    css = printcss.build(options.resolve(PdfConfig(backgrounds=False)), _THEME)
    assert "background-image: none" in css
    assert "section.slide.inverse" in css


def test_light_inverse_only_flips():
    css = printcss.build(options.resolve(PdfConfig(light_inverse=True)), _THEME)
    assert "section.slide.inverse" in css
    assert "background-image: none" not in css  # backgrounds still kept


def test_bw_tokens_injects_root_grays():
    css = printcss.build(options.resolve(PdfConfig(color="bw")), _THEME)
    assert ":root {" in css and "--accent:" in css


def test_bw_ghostscript_does_not_touch_tokens():
    css = printcss.build(
        options.resolve(PdfConfig(color="bw", bw_engine="ghostscript")), _THEME
    )
    assert "--accent:" not in css  # gs recolors post-hoc, not via tokens


# --------------------------------------------------------------------------- #
# geometry
# --------------------------------------------------------------------------- #
def test_length_units():
    assert geometry.length_to_pt("72pt") == 72
    assert geometry.length_to_pt("1in") == 72
    assert round(geometry.length_to_pt("25.4mm"), 2) == 72.0
    assert round(geometry.length_to_pt("96px"), 2) == 72.0
    with pytest.raises(ConfigError):
        geometry.length_to_pt("wide")


def test_sheet_size_named_and_orientation():
    assert geometry.sheet_size("letter", "portrait", (800, 600)) == (612.0, 792.0)
    w, h = geometry.sheet_size("a4", "landscape", (800, 600))
    assert w > h  # landscape
    # deck uses the master size as-is (already portrait here)
    assert geometry.sheet_size("deck", "portrait", (600, 800)) == (600, 800)


def test_sheet_size_auto_matches_deck_aspect():
    # auto -> landscape for a wide master, portrait for a tall one
    w, h = geometry.sheet_size("letter", "auto", (960, 540))
    assert w > h and {round(w), round(h)} == {612, 792}
    w, h = geometry.sheet_size("letter", "auto", (540, 960))
    assert h > w


def test_auto_orientation_follows_grid_not_just_deck():
    wide = (960, 540)  # 16:9 deck
    # two stacked 16:9 slides want a tall page; a 2x2 grid wants a wide one
    assert geometry.auto_orientation("2up", wide) == "portrait"
    assert geometry.auto_orientation("2x2", wide) == "landscape"
    assert geometry.auto_orientation("2up-notes", wide) == "landscape"


def test_sheet_size_wxh_pixels_to_points():
    # 1280x720 px -> *0.75 -> 960x540 pt, oriented landscape
    w, h = geometry.sheet_size("1280x720", "landscape", (0, 0))
    assert (round(w), round(h)) == (960, 540)


def test_per_page_counts():
    assert geometry.per_page("2up-notes") == 2
    assert geometry.per_page("2x2") == 4
    assert geometry.per_page("6up") == 6
    assert geometry.per_page("1up") == 1


def test_grid_cells_within_bounds_and_count():
    sheet = (612.0, 792.0)
    cells = geometry.page_cells("2x2", sheet, margin=36, gutter=18)
    assert len(cells) == 4
    for c in cells:
        assert c.x >= 36 - 1e-9 and c.y >= 36 - 1e-9
        assert c.x + c.width <= sheet[0] - 36 + 1e-9
        assert c.y + c.height <= sheet[1] - 36 + 1e-9
        assert c.notes is None
    # top row is above bottom row
    assert cells[0].y > cells[2].y


def test_notes_layout_has_notes_box_beside_slide():
    cells = geometry.page_cells("2up-notes", (612.0, 792.0), margin=36, gutter=18)
    assert len(cells) == 2
    for c in cells:
        assert c.notes is not None
        nx, _ny, _nw, _nh = c.notes
        assert nx > c.x + c.width - 1e-6  # notes sit to the right of the slide


def test_fit_contain_preserves_aspect_centered():
    cell = geometry.Cell(0, 0, 200, 200)
    p = geometry.fit_contain(cell, 400, 200)  # 2:1 into a square
    assert round(p.width) == 200 and round(p.height) == 100
    assert round(p.scale, 3) == 0.5
    assert round(p.y) == 50  # vertically centered
    assert round(p.x) == 0


# --------------------------------------------------------------------------- #
# imposition (pypdf, no browser) — synthesize a vector master with reportlab
# --------------------------------------------------------------------------- #
def _make_master(n: int, w: float = 320, h: float = 240) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    for i in range(n):
        c.drawString(20, 20, f"SLIDE-{i}")
        c.showPage()
    c.save()
    return buf.getvalue()


def _pages(pdf: bytes):
    from pypdf import PdfReader

    return PdfReader(io.BytesIO(pdf)).pages


@needs_pdf_libs
def test_1up_deck_is_passthrough():
    master = _make_master(3)
    out = impose.impose(
        _make_master(3),
        options=options.resolve(PdfConfig(layout="1up", paper="deck")),
        notes=[[], [], []],
        title="T",
        date="2026-06-10",
    )
    assert len(_pages(out)) == 3
    assert len(_pages(out)) == len(_pages(master))


@needs_pdf_libs
def test_2up_notes_sheet_count_and_notes_text():
    out = impose.impose(
        _make_master(3),
        options=options.resolve(PdfConfig(layout="2up-notes", paper="letter")),
        notes=[["first note"], ["second note here"], ["third"]],
        title="My Talk",
        date="2026-06-10",
    )
    pages = _pages(out)
    assert len(pages) == 2  # 3 slides, 2 per sheet
    # letter sheet (auto-oriented landscape for the wide synthetic master)
    assert sorted(round(float(x)) for x in pages[0].mediabox) == [0, 0, 612, 792]
    text = pages[0].extract_text()
    assert "first note" in text and "second note here" in text


# --------------------------------------------------------------------------- #
# CJK notes — a CID font (not Helvetica) so Kanji/kana/Hangul don't tofu
# --------------------------------------------------------------------------- #
@needs_pdf_libs
def test_cjk_script_selection_prefers_lang_then_content():
    # Han-only text is ambiguous (JP kanji vs CN share code points); default JP.
    assert impose._cjk_font("量子 (ryōshi)") == "HeiseiKakuGo-W5"
    # An explicit document language disambiguates.
    assert impose._cjk_font("量子", lang="zh") == "STSong-Light"
    assert impose._cjk_font("量子", lang="zh-Hant") == "MSung-Light"
    # Content heuristic when there's no lang hint: kana ⇒ JP, Hangul ⇒ KR.
    assert impose._cjk_font("こんにちは") == "HeiseiKakuGo-W5"
    assert impose._cjk_font("생체") == "HYGothic-Medium"
    # No CJK ⇒ no special font (Helvetica is used).
    assert impose._cjk_font("plain english", lang="en") is None


def test_reflow_joins_soft_wraps_keeps_paragraph_breaks():
    # A paragraph hard-wrapped in the source reflows to one line (soft newline =>
    # space), so the handout fills the column instead of echoing source wraps.
    note = ["The stamp reads 量子 (ryōshi) — the", "Japanese word for quantum."]
    assert impose._reflow(note) == (
        "The stamp reads 量子 (ryōshi) — the Japanese word for quantum."
    )
    # A blank line separates paragraphs; runs of blanks collapse to one break.
    flowed = impose._reflow(["one", "two", "", "", "three"])
    assert flowed == "one two\n\nthree"


@needs_pdf_libs
def test_wrap_breaks_long_cjk_run_between_characters():
    # CJK has no spaces; a long run must still wrap rather than overflow the box.
    run = "量子" * 30
    lines = impose._wrap(run, "HeiseiKakuGo-W5", 8.5, 60.0)
    assert len(lines) > 1  # it wrapped
    assert "".join(lines) == run  # no characters lost, none invented
    # Latin still wraps on whitespace, unchanged.
    assert impose._wrap("the quick brown fox", "Helvetica", 8.5, 60.0) == [
        "the quick brown",
        "fox",
    ]


@needs_pdf_libs
def test_cjk_notes_render_as_extractable_text():
    out = impose.impose(
        _make_master(2),
        options=options.resolve(PdfConfig(layout="2up-notes", paper="letter")),
        notes=[["reads 量子 (ryōshi) — the Japanese word; 生体認証 too."], ["plain"]],
        title="量子 Talk",
        date="2026-06-25",
        lang="ja",
    )
    text = _pages(out)[0].extract_text()
    # The Kanji survive into the PDF as real text (proves a CJK font drew them,
    # not Helvetica's missing-glyph boxes), and so does the macron ō.
    assert "量子" in text and "生体認証" in text and "ryōshi" in text


@needs_pdf_libs
def test_4up_fits_on_one_sheet_with_footer():
    out = impose.impose(
        _make_master(4),
        options=options.resolve(PdfConfig(layout="4up", paper="a4")),
        notes=[[]] * 4,
        title="Deck",
        date="2026-06-10",
    )
    pages = _pages(out)
    assert len(pages) == 1
    # footer template expands {title}/{page}/{pages}
    assert "Deck" in pages[0].extract_text()


@needs_pdf_libs
def test_header_footer_template_expansion():
    cfg = PdfConfig(
        layout="2up", paper="letter", header="{title}", footer="{page}/{pages}"
    )
    out = impose.impose(
        _make_master(4),
        options=options.resolve(cfg),
        notes=[[]] * 4,
        title="Hdr",
        date="2026-06-10",
    )
    pages = _pages(out)
    assert len(pages) == 2
    t0 = pages[0].extract_text()
    assert "Hdr" in t0 and "1/2" in t0


# --------------------------------------------------------------------------- #
# end-to-end (Chromium) — skips cleanly when the browser isn't installed
# --------------------------------------------------------------------------- #
def _chromium_available() -> bool:
    try:
        from lectern.pdf.master import ensure_available

        ensure_available()
        return True
    except Exception:
        return False


HAVE_CHROMIUM = _chromium_available()


@needs_pdf_libs
def test_slide_notes_exclude_presenter_notes(fixtures, tmp_path):
    # The handout pipeline reads `lowered.notes` only, so `notes:presenter`
    # blocks never reach the printed PDF (this needs no browser).
    from lectern.config import resolve_source
    from lectern.pdf.pipeline import _slide_notes
    from lectern.preprocess import assemble_resolved

    resolved = resolve_source(fixtures / "render-deck")
    deck = assemble_resolved(resolved)
    flat = [
        line
        for slide in _slide_notes(deck, resolved.config, tmp_path)
        for line in slide
    ]
    assert "A speaker note for the builds slide." in flat
    assert "A presenter-only reminder, kept out of handouts." not in flat


@pytest.mark.skipif(not HAVE_CHROMIUM, reason="Chromium/Playwright not installed")
def test_end_to_end_pdf_build(fixtures, tmp_path):
    from lectern.config import resolve_source
    from lectern.preprocess import assemble_resolved
    from lectern.render import get_renderer

    resolved = resolve_source(
        fixtures / "render-deck",
        # keep the master cache out of the shared fixture tree (build_dir is the
        # deck root by default) — point it at the test's tmp dir instead.
        cli_overrides={
            "pdf": {"layout": "2up-notes"},
            "build_dir": str(tmp_path / "build"),
        },
    )
    deck = assemble_resolved(resolved)
    result = get_renderer("reveal").render(deck, resolved.config, tmp_path, "pdf")
    assert result.output == tmp_path / "index.pdf"

    pages = _pages(result.output.read_bytes())
    assert len(pages) == 2  # 3 slides, 2-up
    text = pages[0].extract_text()
    assert "Hero Slide" in text
    assert "A speaker note for the builds slide." in text  # notes carried to handout
    # presenter-only notes stay in the speaker view, never the printed handout.
    assert "presenter-only reminder" not in text.lower()
    # master was cached for reuse across subsequent layout/color changes —
    # under the deck's build_dir (here redirected to tmp), not the out_dir.
    assert (tmp_path / "build" / ".lectern-cache").is_dir()
    assert not (tmp_path / ".lectern-cache").exists()


@needs_pdf_libs
@pytest.mark.skipif(not HAVE_CHROMIUM, reason="Chromium/Playwright not installed")
def test_tagged_1up_pdf(fixtures, tmp_path):
    from pypdf import PdfReader

    from lectern.config import resolve_source
    from lectern.preprocess import assemble_resolved
    from lectern.render import get_renderer

    resolved = resolve_source(
        fixtures / "render-deck",
        cli_overrides={
            "pdf": {"layout": "1up"},  # 1up passthrough preserves the tagged master
            "build_dir": str(tmp_path / "build"),
        },
    )
    deck = assemble_resolved(resolved)
    out = get_renderer("reveal").render(deck, resolved.config, tmp_path, "pdf").output

    root = PdfReader(out).trailer["/Root"]
    assert bool(root.get("/MarkInfo", {}).get("/Marked"))  # tagged
    assert "/StructTreeRoot" in root  # has a structure tree
    assert str(root.get("/Lang")).startswith("en")  # <html lang> -> /Lang
