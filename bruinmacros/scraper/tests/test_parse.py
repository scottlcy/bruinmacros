"""Parser tests against small pages shaped like UCLA Dining's (run: python -m pytest scraper/tests)."""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scrape import parse_item, parse_menu  # noqa: E402

MENU = """
<html><body>
<h3>Today's Dining Hours</h3><p>Breakfast 9:00 a.m. - 10:00 a.m.</p>
<a href="#breakfastmenu">Breakfast</a>
<ul><li>Today, September 27</li><li>Tomorrow, September 28</li></ul>
<p>September 28, 2026</p>
<h2>BREAKFAST</h2>
<a href="https://dining.ucla.edu/nutrition-calculator/?menu_id=393">Calculate Nutrition</a>
<ul><li><a href="#breakfast-The-Front-Burner">The front burner</a></li></ul>
<h2>The Front Burner</h2>
<h3>Bruin Scramble</h3><img title="Dairy"><a href="https://dining.ucla.edu/menu-item/?recipe=7404">See Meal Details</a>
<h3>Buttermilk Pancakes</h3><a href="https://dining.ucla.edu/menu-item/?recipe=7300">See Meal Details</a>
<h2>The Kitchen</h2>
<h3>Scrambled Eggs</h3><a href="https://dining.ucla.edu/menu-item/?recipe=6542">See Meal Details</a>
<h2>LUNCH</h2>
<h2>Theme of the Day</h2>
<h3>Brunch</h3><a href="https://dining.ucla.edu/menu-item/?recipe=1254">See Meal Details</a>
<h2>The Grill</h2>
<h3>Bruin Burger</h3><a href="https://dining.ucla.edu/menu-item/?recipe=6204">See Meal Details</a>
<h3>Bruin Burger</h3><a href="https://dining.ucla.edu/menu-item/?recipe=6204">See Meal Details</a>
<h2>DINNER</h2>
<h2>Icon Legend</h2>
<h3>Vegan</h3>
</body></html>
"""

ITEM = """
<html><body><h1>Bruin Burger</h1><h2>Nutrition</h2>
<p><strong>Serving Size:</strong> 8.61oz</p><p>Calories: 440</p>
<table><tr><td>Total Fat 18.79g</td><td>24%</td></tr><tr><td>Saturated Fat 5.69g</td></tr>
<tr><td>Total Carbohydrate 35.5g</td></tr><tr><td>Dietary Fiber 2.24g</td></tr>
<tr><td>Protein 33.45g</td><td>67%</td></tr></table>
<h2>Allergen Information</h2><ul><li>High-Carbon-Footprint</li><li>Halal</li><li>Contains Soy</li><li>Some Other Note</li></ul>
</body></html>
"""


def test_menu_structure():
    meals = parse_menu(MENU, dt.date(2026, 9, 28))
    assert [m["name"] for m in meals] == ["Breakfast", "Lunch"]  # empty Dinner dropped
    b = meals[0]
    assert [s["name"] for s in b["stations"]] == ["The Front Burner", "The Kitchen"]
    assert b["stations"][0]["items"] == [
        {"id": "7404", "name": "Bruin Scramble"},
        {"id": "7300", "name": "Buttermilk Pancakes"},
    ]
    lunch = meals[1]
    # "Theme of the Day / Brunch" label skipped, duplicate burger collapsed
    assert [s["name"] for s in lunch["stations"]] == ["The Grill"]
    assert lunch["stations"][0]["items"] == [{"id": "6204", "name": "Bruin Burger"}]


def test_stale_page_rejected():
    assert parse_menu(MENU, dt.date(2026, 9, 27)) is None


def test_item_nutrition():
    info = parse_item(ITEM)
    assert info["name"] == "Bruin Burger"
    assert info["serving"] == "8.61oz"
    assert (info["cal"], info["p"], info["c"], info["f"]) == (440, 33.45, 35.5, 18.79)
    assert info["tags"] == ["High-Carbon-Footprint", "Halal", "Contains Soy"]
    assert "nodata" not in info


def test_missing_and_tray_sized_items_flagged():
    zero = ITEM.replace("Calories: 440", "Calories: 0")
    assert parse_item(zero)["nodata"] is True
    tray = ITEM.replace("8.61oz", "41.84oz")
    assert parse_item(tray)["nodata"] is True
