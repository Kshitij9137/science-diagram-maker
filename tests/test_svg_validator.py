from app.services.svg_validator import all_passed, failure_messages, validate_svg

GOOD_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600">
  <title>Test diagram</title>
  <style>
    @keyframes pulse { from { opacity: 0.4; } to { opacity: 1; } }
    .dot { animation: pulse 1s infinite alternate; }
  </style>
  <rect x="0" y="0" width="800" height="600" fill="#f5f5f5"/>
  <circle class="dot" cx="400" cy="300" r="50" fill="blue"/>
  <text x="400" y="60" text-anchor="middle" font-size="24">Title text</text>
  <text x="100" y="500" font-size="16">Label one</text>
  <text x="600" y="500" font-size="16">Label two</text>
</svg>"""


def failed(svg):
    """Names of the checks that failed for this SVG."""
    checks = validate_svg(svg)
    return {name for name, c in checks.items() if not c["passed"]}


def test_good_svg_passes_everything():
    checks = validate_svg(GOOD_SVG)
    assert all_passed(checks), failure_messages(checks)


def test_broken_xml_fails_check_1():
    assert "valid_xml" in failed(GOOD_SVG.replace("</svg>", ""))


def test_not_svg_root_fails():
    assert "valid_xml" in failed("<html><body>hello</body></html>")


def test_doctype_is_rejected():
    bad = '<!DOCTYPE svg [<!ENTITY x "y">]>' + GOOD_SVG
    assert "valid_xml" in failed(bad)


def test_circle_outside_viewbox_fails():
    bad = GOOD_SVG.replace('cx="400" cy="300" r="50"', 'cx="780" cy="300" r="50"')
    assert failed(bad) == {"viewbox_bounds"}


def test_text_outside_viewbox_fails():
    bad = GOOD_SVG.replace('x="600" y="500"', 'x="790" y="500"')
    assert "viewbox_bounds" in failed(bad)


def test_translate_moves_shape_outside():
    bad = GOOD_SVG.replace(
        '<circle class="dot"', '<g transform="translate(500,0)"><circle class="dot"'
    ).replace('fill="blue"/>', 'fill="blue"/></g>')
    assert "viewbox_bounds" in failed(bad)


def test_path_is_counted_not_failed():
    svg = GOOD_SVG.replace("</svg>", '<path d="M 0 0 L 5000 5000"/></svg>')
    checks = validate_svg(svg)
    assert checks["viewbox_bounds"]["passed"]
    assert "not checked" in checks["viewbox_bounds"]["reason"]


def test_missing_title_fails():
    bad = GOOD_SVG.replace("<title>Test diagram</title>", "")
    assert failed(bad) == {"title_and_labels"}


def test_only_two_labels_fails():
    bad = GOOD_SVG.replace('<text x="600" y="500" font-size="16">Label two</text>', "")
    assert failed(bad) == {"title_and_labels"}


def test_no_animation_fails():
    bad = GOOD_SVG.replace("<style>", "<!--").replace("</style>", "-->")
    assert failed(bad) == {"animation"}


def test_unused_keyframes_fails():
    bad = GOOD_SVG.replace("animation: pulse 1s infinite alternate;", "")
    assert failed(bad) == {"animation"}


def test_smil_animation_passes():
    svg = GOOD_SVG.replace("<style>", "<!--").replace("</style>", "-->")
    svg = svg.replace(
        'fill="blue"/>',
        'fill="blue"><animate attributeName="r" from="40" to="60" dur="1s" repeatCount="indefinite"/></circle>',
    )
    assert all_passed(validate_svg(svg))


def test_script_tag_fails_security():
    bad = GOOD_SVG.replace("</svg>", "<script>alert(1)</script></svg>")
    assert failed(bad) == {"security"}


def test_onclick_fails_security():
    bad = GOOD_SVG.replace('<circle class="dot"', '<circle onclick="x()" class="dot"')
    assert failed(bad) == {"security"}


def test_external_image_fails_security():
    bad = GOOD_SVG.replace(
        "</svg>", '<image href="http://evil.com/a.png" x="0" y="0" width="10" height="10"/></svg>'
    )
    assert "security" in failed(bad)


def test_internal_reference_is_allowed():
    ok = GOOD_SVG.replace("</svg>", '<use href="#thing"/></svg>')
    assert "security" not in failed(ok)