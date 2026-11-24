"""Checks for AI-generated SVGs.

Every check returns (passed: bool, reason: str).
validate_svg() runs all five and returns a dictionary the web page can show.
"""
import re
import xml.etree.ElementTree as ET

from app import config

# A number like 12, -3.5, .5 or 1e3 (no capture groups, so findall returns whole numbers)
NUMBER_PATTERN = r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_NUMBER = re.compile(NUMBER_PATTERN)
_TRANSLATE = re.compile(
    rf"^\s*translate\(\s*({NUMBER_PATTERN})\s*(?:[,\s]\s*({NUMBER_PATTERN}))?\s*\)\s*$"
)

ANIMATION_TAGS = {"animate", "animatetransform", "animatemotion", "set"}

# Parts of an SVG that are not drawn directly, so we don't measure them
SKIP_TAGS = {"defs", "clippath", "mask", "pattern", "symbol", "marker",
             "style", "title", "desc", "metadata"}

# Shapes we can't measure with simple maths. We count them but don't fail them.
UNCHECKED_TAGS = {"path", "image", "use"}

FORBIDDEN_TAGS = {"script", "foreignobject", "iframe", "embed", "object"}


# ----------------------------------------------------------------- helpers
def _local(tag):
    """'{http://www.w3.org/2000/svg}Circle' -> 'circle'"""
    return tag.split("}")[-1].lower()


def _num(elem, name, default=0.0):
    """Read a numeric attribute.

    Missing attribute -> default. Percentages or junk -> None ("can't measure").
    """
    raw = elem.get(name)
    if raw is None:
        return default
    raw = raw.strip()
    if "%" in raw:
        return None
    match = _NUMBER.match(raw)
    return float(match.group()) if match else None


def _first_number(raw, default=0.0):
    """First number in a string like '10 20 30' (text x can be a list)."""
    match = _NUMBER.search(raw or "")
    return float(match.group()) if match else default


def _text_content(elem):
    """All text inside an element, with whitespace tidied."""
    return " ".join("".join(elem.itertext()).split())


def parse_svg(svg_string):
    """Parse the SVG or raise an error. Used by check 1 and by validate_svg()."""
    lowered = svg_string.lower()
    # DOCTYPE/ENTITY tricks can make XML parsers misbehave. SVGs never need them.
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise ValueError("SVG contains a DOCTYPE or ENTITY declaration, which is not allowed")
    root = ET.fromstring(svg_string)
    if _local(root.tag) != "svg":
        raise ValueError(f"Root element is <{_local(root.tag)}>, not <svg>")
    return root


# ----------------------------------------------------- check 1: valid XML
def check_valid_xml(svg_string):
    try:
        parse_svg(svg_string)
    except ET.ParseError as error:
        return False, f"Invalid XML: {error}"
    except ValueError as error:
        return False, str(error)
    return True, "Valid XML with an <svg> root element"


# --------------------------------------------------- check 2: inside viewBox
def _get_viewbox(root):
    """Return [min_x, min_y, width, height] or None if missing/invalid."""
    raw = root.get("viewBox")
    if not raw:
        return None
    try:
        numbers = [float(p) for p in re.split(r"[\s,]+", raw.strip())]
    except ValueError:
        return None
    if len(numbers) != 4 or numbers[2] <= 0 or numbers[3] <= 0:
        return None
    return numbers


def _text_box(elem):
    """Estimate the box a <text> covers. Returns None if the text is empty."""
    content = _text_content(elem)
    if not content:
        return None
    style = elem.get("style", "")

    size = _num(elem, "font-size", None)
    if size is None:
        match = re.search(r"font-size\s*:\s*([\d.]+)", style)
        size = float(match.group(1)) if match else config.DEFAULT_FONT_SIZE

    anchor = elem.get("text-anchor", "")
    if not anchor:
        match = re.search(r"text-anchor\s*:\s*(\w+)", style)
        anchor = match.group(1) if match else "start"

    x = _first_number(elem.get("x"))
    y = _first_number(elem.get("y"))
    width = config.CHAR_WIDTH_FACTOR * size * len(content)

    if anchor == "middle":
        x0 = x - width / 2
    elif anchor == "end":
        x0 = x - width
    else:
        x0 = x
    # Text sits ON the baseline y, so most of it is above y
    return (x0, y - size, x0 + width, y + 0.25 * size)


def _element_box(elem, tag):
    """Return (x0, y0, x1, y1), the string 'unchecked', or None if not a shape."""
    if tag == "text":
        return _text_box(elem)

    if tag == "circle":
        cx, cy, r = _num(elem, "cx"), _num(elem, "cy"), _num(elem, "r")
        if None in (cx, cy, r):
            return "unchecked"
        box = (cx - r, cy - r, cx + r, cy + r)
    elif tag == "ellipse":
        cx, cy = _num(elem, "cx"), _num(elem, "cy")
        rx, ry = _num(elem, "rx"), _num(elem, "ry")
        if None in (cx, cy, rx, ry):
            return "unchecked"
        box = (cx - rx, cy - ry, cx + rx, cy + ry)
    elif tag == "rect":
        x, y = _num(elem, "x"), _num(elem, "y")
        w, h = _num(elem, "width"), _num(elem, "height")
        if None in (x, y, w, h):
            return "unchecked"
        box = (x, y, x + w, y + h)
    elif tag == "line":
        x1, y1, x2, y2 = (_num(elem, n) for n in ("x1", "y1", "x2", "y2"))
        if None in (x1, y1, x2, y2):
            return "unchecked"
        box = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    elif tag in ("polygon", "polyline"):
        numbers = [float(n) for n in _NUMBER.findall(elem.get("points", ""))]
        pairs = list(zip(numbers[0::2], numbers[1::2]))
        if not pairs:
            return "unchecked"
        xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
        box = (min(xs), min(ys), max(xs), max(ys))
    elif tag in UNCHECKED_TAGS:
        return "unchecked"
    else:
        return None  # a container like <g>, or something we ignore

    # A stroke is drawn half inside, half outside the shape's edge
    stroke = elem.get("stroke")
    if stroke and stroke != "none":
        half = (_num(elem, "stroke-width", 1.0) or 0.0) / 2
        box = (box[0] - half, box[1] - half, box[2] + half, box[3] + half)
    return box


def _collect_boxes(root):
    """Walk the whole SVG. Return (list of (tag, x0, y0, x1, y1), unchecked_count)."""
    boxes = []
    state = {"unchecked": 0}

    def walk(elem, dx, dy):
        tag = _local(elem.tag)
        if tag in SKIP_TAGS:
            return

        # Support transform="translate(x, y)" only. Anything else -> skip this subtree.
        transform = elem.get("transform")
        if transform:
            match = _TRANSLATE.match(transform)
            if match:
                dx += float(match.group(1))
                dy += float(match.group(2) or 0)
            else:
                state["unchecked"] += 1
                return

        result = _element_box(elem, tag)
        if result == "unchecked":
            state["unchecked"] += 1
        elif result is not None:
            x0, y0, x1, y1 = result
            boxes.append((tag, x0 + dx, y0 + dy, x1 + dx, y1 + dy))

        for child in elem:
            walk(child, dx, dy)

    for child in root:
        walk(child, 0.0, 0.0)
    return boxes, state["unchecked"]


def check_viewbox_bounds(root):
    viewbox = _get_viewbox(root)
    if viewbox is None:
        return False, "Missing or invalid viewBox attribute"

    min_x, min_y, width, height = viewbox
    max_x, max_y = min_x + width, min_y + height
    tol = config.BOUNDS_TOLERANCE

    boxes, unchecked = _collect_boxes(root)
    problems = []
    for tag, x0, y0, x1, y1 in boxes:
        sides = []
        if x0 < min_x - tol:
            sides.append(f"left edge at {x0:.0f}")
        if y0 < min_y - tol:
            sides.append(f"top edge at {y0:.0f}")
        if x1 > max_x + tol:
            sides.append(f"right edge at {x1:.0f}")
        if y1 > max_y + tol:
            sides.append(f"bottom edge at {y1:.0f}")
        if sides:
            problems.append(f"<{tag}> {', '.join(sides)}")

    if problems:
        shown = "; ".join(problems[:3])
        more = f" (+{len(problems) - 3} more)" if len(problems) > 3 else ""
        return False, (f"{len(problems)} element(s) outside the "
                       f"{width:.0f}x{height:.0f} viewBox: {shown}{more}")

    note = f"; {unchecked} part(s) not checked (paths or complex transforms)" if unchecked else ""
    return True, f"All {len(boxes)} measured shapes are inside the viewBox{note}"


# ---------------------------------------------- check 3: title and labels
def check_title_and_labels(root):
    titles = [e for e in root.iter() if _local(e.tag) == "title" and _text_content(e)]
    labels = [e for e in root.iter() if _local(e.tag) == "text" and _text_content(e)]

    problems = []
    if not titles:
        problems.append("No non-empty <title> element")
    if len(labels) < config.MIN_LABELS:
        problems.append(f"Only {len(labels)} text label(s), need at least {config.MIN_LABELS}")

    if problems:
        return False, "; ".join(problems)
    return True, f"Title found and {len(labels)} text labels"


# ------------------------------------------------------ check 4: animation
def _collect_css(root):
    """All CSS in <style> tags and style="..." attributes, joined together."""
    parts = []
    for elem in root.iter():
        if _local(elem.tag) == "style":
            parts.append("".join(elem.itertext()))
        if elem.get("style"):
            parts.append(elem.get("style"))
    return "\n".join(parts)


def check_animation(root):
    smil = [e for e in root.iter() if _local(e.tag) in ANIMATION_TAGS]
    if smil:
        return True, f"Found {len(smil)} SMIL animation element(s)"

    css = _collect_css(root)
    names = re.findall(r"@keyframes\s+([\w-]+)", css)
    for name in names:
        # Is there an "animation: ..." or "animation-name: ..." declaration using this name?
        pattern = r"animation[\w-]*\s*:[^;}]*\b" + re.escape(name) + r"\b"
        if re.search(pattern, css):
            return True, f"CSS animation '{name}' is defined and used"

    if names:
        return False, "@keyframes defined but no animation declaration uses them"
    return False, "No animation found (no SMIL tags and no CSS @keyframes)"


# -------------------------------------------------- check 5: security (mine)
def check_security(root):
    problems = []

    for elem in root.iter():
        tag = _local(elem.tag)
        if tag in FORBIDDEN_TAGS:
            problems.append(f"forbidden element <{tag}>")

        for attr, value in elem.attrib.items():
            name = _local(attr)
            if name.startswith("on"):
                problems.append(f"event handler attribute '{name}'")
            if name == "href" and not value.strip().startswith("#"):
                problems.append(f"external link in href: {value[:40]}")
            if "javascript:" in value.lower():
                problems.append("javascript: URL in an attribute")
            for target in re.findall(r"url\(([^)]*)\)", value, re.I):
                if not target.strip(" '\"").startswith("#"):
                    problems.append(f"external url() in attribute '{name}'")

    css = _collect_css(root)
    if re.search(r"@import", css, re.I):
        problems.append("CSS @import")
    for target in re.findall(r"url\(([^)]*)\)", css, re.I):
        if not target.strip(" '\"").startswith("#"):
            problems.append("external url() in CSS")

    if problems:
        unique = list(dict.fromkeys(problems))  # remove duplicates, keep order
        return False, "Unsafe content: " + "; ".join(unique[:4])
    return True, "No scripts, event handlers or external references"


# ------------------------------------------------------ run everything
def _as_dict(passed, reason):
    return {"passed": bool(passed), "reason": reason}


def validate_svg(svg_string):
    """Run all five checks. Returns {check_name: {"passed": bool, "reason": str}}."""
    checks = {}

    ok, reason = check_valid_xml(svg_string)
    checks["valid_xml"] = _as_dict(ok, reason)
    root = parse_svg(svg_string) if ok else None

    later_checks = [
        ("viewbox_bounds", check_viewbox_bounds),
        ("title_and_labels", check_title_and_labels),
        ("animation", check_animation),
        ("security", check_security),
    ]
    for name, function in later_checks:
        if root is None:
            checks[name] = _as_dict(False, "Skipped: the SVG could not be parsed")
            continue
        try:
            passed, reason = function(root)
        except Exception as error:  # a buggy check must never crash the pipeline
            passed, reason = False, f"Check crashed: {type(error).__name__}: {error}"
        checks[name] = _as_dict(passed, reason)

    return checks


def all_passed(checks):
    return all(check["passed"] for check in checks.values())


def failure_messages(checks):
    """List of 'name: reason' strings for failed checks. Phase 3 sends these to Gemini."""
    return [f"{name}: {c['reason']}" for name, c in checks.items() if not c["passed"]]