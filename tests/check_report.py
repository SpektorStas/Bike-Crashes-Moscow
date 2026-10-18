"""Check the standalone report in Chromium; keep screenshots for visual review."""

from pathlib import Path
import json
import csv
import os
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "outputs/final/screenshots"
SCREENSHOTS.mkdir(parents=True, exist_ok=True)
# A full-page capture should show off-screen content as in a printed report.
FULL_PAGE_STYLE = ".report-main>section{position:relative!important;top:auto!important}"

with sync_playwright() as p:
    executable = os.environ.get("REPORT_BROWSER")
    if not executable:
        chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        executable = str(chrome) if chrome.exists() else None
    browser = p.chromium.launch(executable_path=executable, headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors, requests = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("request", lambda r: requests.append(r.url))
    page.goto((ROOT / "report.html").as_uri())
    page.wait_for_selector("#map-year")
    # The progress line and section links belong to the sticky header.
    assert page.locator("#reading-nav").is_visible()
    progress_box = page.locator("#reading-progress").bounding_box()
    assert (
        progress_box["y"] == 0
        and progress_box["width"] == 1440
        and progress_box["height"] == 36
    )
    bike_start = page.locator("#reading-bike").bounding_box()
    assert 0 <= bike_start["x"] < 20
    assert not page.locator("#reading-progress").evaluate(
        '(el) => el.classList.contains("is-complete")'
    )
    assert (
        page.locator('#reading-links a[aria-current="location"]').get_attribute("href")
        == "#cover"
    )
    assert (
        page.locator(".card").first.evaluate(
            "(el) => getComputedStyle(el).borderRadius"
        )
        == "0px"
    )
    assert (
        page.locator(".section").first.evaluate(
            "(el) => getComputedStyle(el).backgroundImage"
        )
        == "none"
    )
    page.screenshot(path=str(SCREENSHOTS / "cover-desktop.png"))
    page.emulate_media(reduced_motion="reduce")
    page.locator('#reading-links a[href="#models"]').click()
    page.wait_for_function(
        'document.querySelector("#reading-links a[aria-current=location]").hash === "#models"'
    )
    assert (
        0 < int(page.locator("#reading-progress").get_attribute("aria-valuenow")) < 100
    )
    assert page.locator("#reading-progress").bounding_box()["y"] == 0
    fill = page.locator("#reading-fill").evaluate(
        "(el) => new DOMMatrix(getComputedStyle(el).transform).a"
    )
    assert (
        abs(
            fill * 100
            - int(page.locator("#reading-progress").get_attribute("aria-valuenow"))
        )
        < 1
    )
    bike_middle = page.locator("#reading-bike").bounding_box()
    assert bike_middle["x"] > bike_start["x"] + 100
    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    page.wait_for_function(
        'document.querySelector("#reading-progress").getAttribute("aria-valuenow") === "100"'
    )
    assert page.locator("#reading-progress").evaluate(
        '(el) => el.classList.contains("is-complete")'
    )
    bike_end = page.locator("#reading-bike").bounding_box()
    car = page.locator(".reading-car").bounding_box()
    assert bike_end["x"] > bike_middle["x"]
    assert abs(bike_end["x"] + bike_end["width"] - car["x"]) < 10
    assert (
        page.locator(".reading-impact").evaluate("(el) => getComputedStyle(el).opacity")
        == "1"
    )
    assert (
        page.locator(".reading-impact").evaluate(
            "(el) => getComputedStyle(el).animationName"
        )
        == "none"
    )
    page.screenshot(path=str(SCREENSHOTS / "progress-finish.png"))
    assert (
        page.locator('#reading-links a[aria-current="location"]').get_attribute("href")
        == "#method"
    )
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_function(
        'document.querySelector("#reading-progress").getAttribute("aria-valuenow") === "0"'
    )
    assert not page.locator("#reading-progress").evaluate(
        '(el) => el.classList.contains("is-complete")'
    )
    page.emulate_media(reduced_motion="no-preference")
    page.wait_for_function(
        'getComputedStyle(document.querySelector(".hero")).opacity === "1"'
    )
    page.screenshot(
        path=str(SCREENSHOTS / "desktop.png"), full_page=True, style=FULL_PAGE_STYLE
    )
    # Normal scrolling moves the incoming panel while the cover stays in place.
    page.evaluate('window.scrollTo({top:0,behavior:"instant"})')
    page.wait_for_timeout(150)
    page.mouse.move(650, 450)
    page.mouse.wheel(0, 120)
    page.wait_for_timeout(350)
    assert 60 < page.evaluate("window.scrollY") < 240
    assert page.locator("#cover").evaluate(
        '(el) => Math.abs(el.getBoundingClientRect().top - document.querySelector(".masthead").offsetHeight) < 2'
    )
    assert (
        page.locator('#reading-links a[aria-current="location"]').get_attribute("href")
        == "#cover"
    )
    # Near a boundary the page must not accelerate or jump to a heading.
    page.evaluate(
        'window.scrollTo({top:document.querySelector(\'.section-anchor[data-section="geography"]\').getBoundingClientRect().top + window.scrollY - document.querySelector(".masthead").offsetHeight - 300,behavior:"instant"})'
    )
    page.wait_for_timeout(150)
    before_scroll = page.evaluate("window.scrollY")
    page.mouse.wheel(0, 120)
    page.wait_for_timeout(1100)
    assert abs(page.evaluate("window.scrollY") - before_scroll - 120) < 3
    assert page.locator("#geography").evaluate(
        '(el) => Math.abs(el.getBoundingClientRect().top - document.querySelector(".masthead").offsetHeight - 180) < 3'
    )
    # The incoming panel must be painted over the still-visible previous panel.
    assert (
        page.evaluate('document.elementFromPoint(300, 500).closest("section").id')
        == "geography"
    )
    assert (
        page.evaluate('document.elementFromPoint(300, 150).closest("section").id')
        == "cover"
    )
    page.screenshot(path=str(SCREENSHOTS / "overlap-desktop.png"))
    page.emulate_media(reduced_motion="reduce")
    page.locator('#reading-links a[href="#dynamics"]').click()
    page.emulate_media(reduced_motion="no-preference")
    assert (
        page.locator("#dynamics > .wrap").evaluate(
            "(el) => getComputedStyle(el).maskImage"
        )
        == "none"
    )
    page.screenshot(path=str(SCREENSHOTS / "section-transition-desktop.png"))
    page.emulate_media(media="print")
    assert (
        page.locator("#dynamics").evaluate("(el) => getComputedStyle(el).position")
        == "relative"
    )
    page.emulate_media(media="screen")
    data = page.locator("#report-data").text_content()
    report = json.loads(data)
    west, south, east, north = report["map"]["initial_bbox"]
    assert 25000 < east - west < 35000
    assert 35000 < north - south < 42000
    assert report["map"]["mkad_paths"]
    with (ROOT / "results/models.csv").open() as f:
        model_rows = list(csv.DictReader(f))
    assert len(report["models"]) == len(model_rows)
    assert len(report["map"]["hexagons"]) == report["meta"]["n_hex"]
    assert len(page.locator("#model-table tbody tr").all()) == len(model_rows)
    # Year controls must update both map totals and the incomplete-year notice.
    page.emulate_media(reduced_motion="reduce")
    page.locator('#reading-links a[href="#geography"]').click()
    # Printing resizes the canvas; wait for its screen-size redraw before comparing.
    page.wait_for_function(
        """() => {
        const canvas = document.querySelector('#map');
        const rect = canvas.getBoundingClientRect();
        const ratio = Math.min(devicePixelRatio, 2);
        return canvas.width === Math.round(rect.width * ratio)
            && canvas.height === Math.round(rect.height * ratio);
    }"""
    )
    original_view = page.evaluate("({zoom, panX, panY, cx, cy})")
    original_scale = page.locator("#scale-line").evaluate("(el) => el.style.width")
    page.locator("#zoom-in").click()
    assert page.evaluate("zoom") > original_view["zoom"]
    page.locator("#zoom-reset").click()
    assert page.evaluate("({zoom, panX, panY, cx, cy})") == original_view
    assert (
        page.locator("#scale-line").evaluate("(el) => el.style.width") == original_scale
    )
    page.locator("#zoom-out").click()
    page.locator("#map").press("Home")
    assert page.evaluate("({zoom, panX, panY, cx, cy})") == original_view
    assert (
        page.locator("#scale-line").evaluate("(el) => el.style.width") == original_scale
    )
    page.screenshot(path=str(SCREENSHOTS / "map-mkad-desktop.png"))
    slider = page.locator("#year-slider")
    slider.fill("1")
    slider.dispatch_event("input")
    assert page.locator("#map-year").inner_text() == "2016"
    assert page.locator("#partial-warning").is_visible()
    slider.fill("0")
    slider.dispatch_event("input")
    page.locator("#play").click()
    page.wait_for_timeout(1600)
    assert page.locator("#map-year").inner_text() == "2018"
    page.locator("#play").click()
    # Different units must render separate coefficient charts.
    page.locator('#reading-links a[href="#models"]').click()
    for scale in ["count", "percent", "probability"]:
        page.locator(f'#main-scales button[data-scale="{scale}"]').click()
        assert page.locator("#main-model-chart svg").count() == 1
    page.locator('#reading-links a[href="#neighbors"]').click()
    page.locator('#spill-scales button[data-scale="total"]').click()
    page.locator('#reading-links a[href="#models"]').click()
    assert page.locator("#spill-model-chart svg").count() == 1
    page.locator("#show-sensitivity").check()
    page.locator('#main-scales button[data-scale="count"]').click()
    page.locator(".model-details summary").click()
    # An expanded, tall section must remain readable by scrolling inside it.
    page.evaluate(
        'window.scrollTo({top:document.querySelector(\'.section-anchor[data-section="models"]\').getBoundingClientRect().top + window.scrollY - document.querySelector(".masthead").offsetHeight,behavior:"instant"})'
    )
    page.wait_for_timeout(800)
    outer_before = page.evaluate("window.scrollY")
    page.mouse.move(650, 300)
    page.mouse.wheel(0, 220)
    page.wait_for_timeout(800)
    assert page.evaluate("window.scrollY") > outer_before + 100
    assert (
        page.locator('#reading-links a[aria-current="location"]').get_attribute("href")
        == "#models"
    )
    with page.expect_download() as info:
        page.locator("#download-csv").click()
    download = info.value
    assert download.suggested_filename.endswith(".csv")
    export = Path(download.path()).read_text(encoding="utf-8-sig")
    csv_rows = list(csv.DictReader(export.splitlines()))
    assert len(csv_rows) == len(model_rows)
    assert "p_holm_within_model" in csv_rows[0] and "n_exposed_hex" in csv_rows[0]
    page.locator('#reading-links a[href="#method"]').click()
    with page.expect_download() as history_info:
        page.locator("#download-history").click()
    history = Path(history_info.value.path()).read_text(encoding="utf-8-sig")
    history_rows = list(csv.DictReader(history.splitlines()))
    assert len(history_rows) == len(report["history_rows"])
    assert sum(row["status"] == "new_after2015" for row in history_rows) == sum(
        row["status"] == "new_after2015" for row in report["history_rows"]
    )
    page.screenshot(
        path=str(SCREENSHOTS / "models.png"), full_page=True, style=FULL_PAGE_STYLE
    )
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(300)
    page.evaluate(
        "document.documentElement.style.scrollBehavior='auto'; window.scrollTo(0, document.querySelector('.section-anchor[data-section=\"dynamics\"]').getBoundingClientRect().top + window.scrollY - 350)"
    )
    page.wait_for_timeout(100)
    assert page.locator("#geography").evaluate(
        "(el) => Math.abs(el.getBoundingClientRect().bottom - window.innerHeight) < 2"
    )
    assert (
        page.evaluate('document.elementFromPoint(200, 200).closest("section").id')
        == "geography"
    )
    assert (
        page.evaluate('document.elementFromPoint(200, 700).closest("section").id')
        == "dynamics"
    )
    page.screenshot(path=str(SCREENSHOTS / "section-transition-mobile.png"))
    page.evaluate('document.documentElement.style.removeProperty("scroll-behavior")')
    page.emulate_media(reduced_motion="reduce")
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(100)
    page.screenshot(path=str(SCREENSHOTS / "cover-mobile.png"))
    assert page.locator("#reading-links").is_visible()
    assert page.locator("#reading-progress").bounding_box()["y"] == 0
    assert page.locator("#reading-links").evaluate(
        "(el) => el.scrollWidth > el.clientWidth"
    )
    page.locator('#reading-links a[href="#geography"]').click()
    page.locator("#zoom-reset").click()
    page.screenshot(path=str(SCREENSHOTS / "map-mkad-mobile.png"))
    page.locator('#reading-links a[href="#neighbors"]').click()
    page.wait_for_function(
        'document.querySelector("#reading-links a[aria-current=location]").hash === "#neighbors"'
    )
    assert page.locator("#reading-progress").bounding_box()["y"] == 0
    page.screenshot(
        path=str(SCREENSHOTS / "mobile.png"), full_page=True, style=FULL_PAGE_STYLE
    )
    page.locator("#models").screenshot(
        path=str(SCREENSHOTS / "mobile-models.png"),
        style=".masthead,.skip-link{visibility:hidden}",
    )
    page.locator("#dynamics").screenshot(
        path=str(SCREENSHOTS / "mobile-trends.png"),
        style=".masthead,.skip-link{visibility:hidden}",
    )
    assert page.evaluate(
        "document.documentElement.scrollWidth <= window.innerWidth + 1"
    )
    # Contact animates only at the end; scrolling back clears it.
    page.evaluate('window.scrollTo({top:0,behavior:"instant"})')
    page.wait_for_function(
        '!document.querySelector("#reading-progress").classList.contains("is-complete")'
    )
    page.emulate_media(reduced_motion="no-preference")
    page.evaluate(
        'window.scrollTo({top:document.documentElement.scrollHeight,behavior:"instant"})'
    )
    page.wait_for_function(
        'document.querySelector("#reading-progress").classList.contains("is-complete")'
    )
    assert (
        page.locator(".reading-impact").evaluate(
            "(el) => getComputedStyle(el).animationName"
        )
        == "impact"
    )
    bike = page.locator("#reading-bike").bounding_box()
    car = page.locator(".reading-car").bounding_box()
    assert 0 < bike["x"] < car["x"] < 390
    assert abs(bike["x"] + bike["width"] - car["x"]) < 10
    page.wait_for_timeout(350)
    page.screenshot(path=str(SCREENSHOTS / "progress-finish-mobile.png"))
    for width in [320, 768, 1199, 1280]:
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_timeout(200)
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth + 1"
        ), width
    page.emulate_media(reduced_motion="reduce")
    page.reload()
    assert page.locator("#play").get_attribute("aria-pressed") != "true"
    assert not errors, errors
    assert not [u for u in requests if u.startswith(("http:", "https:"))], requests
    browser.close()
print(
    "PASS: cyclist progress, MKAD map/reset, navigation, natural scrolling, model scales, CSV, mobile layout and reduced motion."
)
