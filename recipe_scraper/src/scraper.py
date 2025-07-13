import requests
from bs4 import BeautifulSoup
import json
import csv
import time
import os
from urllib.parse import urlparse
from tqdm import tqdm
import logging

# ========== SETUP ========== #
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
RECIPE_WEBSITES = [
    "http://101cookbooks.com/",
    "http://allrecipes.com/",
    "http://bbc.co.uk/",
    "http://bbcgoodfood.com/",
    "http://bonappetit.com/",
    "http://closetcooking.com/",
    "http://epicurious.com/",
    "http://finedininglovers.com/",
    "http://foodrepublic.com/",
    "http://jamieoliver.com/",
    "http://mybakingaddiction.com/",
    "http://paninihappy.com/",
    "http://realsimple.com/",
    "http://simplyrecipes.com/",
    "http://steamykitchen.com/",
    "http://tastykitchen.com/",
    "http://thepioneerwoman.com/",
    "http://thevintagemixer.com/",
    "http://twopeasandtheirpod.com/",
    "http://whatsgabycooking.com/"
]
RATE_LIMIT = 1.5
MAX_RECIPES_PER_SITE = 10  # Scrape up to 10 per site
MAX_TOTAL_RECIPES = 500    # Stop after collecting 500 total
DATA_DIR = "data"

# ========== LOGGING ========== #
os.makedirs(DATA_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO)
domain_timers = {}

# ========== HELPERS ========== #
def make_request(url):
    domain = urlparse(url).netloc
    now = time.time()
    if domain in domain_timers and now - domain_timers[domain] < RATE_LIMIT:
        time.sleep(RATE_LIMIT - (now - domain_timers[domain]))
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        domain_timers[domain] = time.time()
        res.raise_for_status()
        return res
    except Exception as e:
        logging.warning(f"Request failed for {url}: {e}")
        return None

def get_links(site_url, max_links):
    res = make_request(site_url)
    if not res: return []
    soup = BeautifulSoup(res.text, 'html.parser')
    links = set()
    domain = urlparse(site_url).netloc
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('/'):
            href = f"https://{domain}{href}"
        if any(word in href.lower() for word in ['recipe']) and domain in href:
            links.add(href)
        if len(links) >= max_links:
            break
    return list(links)

def parse_recipe(url):
    res = make_request(url)
    if not res: return None
    soup = BeautifulSoup(res.text, 'html.parser')
    recipe = {"source_url": url, "name": "", "ingredients": [], "instructions": []}
    try:
        script = soup.find('script', type='application/ld+json')
        if script:
            data = json.loads(script.string.strip())
            if isinstance(data, list):
                data = next((i for i in data if i.get('@type') == 'Recipe'), {})
            if data.get('@type') == 'Recipe':
                recipe['name'] = data.get('name', '')
                recipe['ingredients'] = data.get('recipeIngredient', [])
                steps = data.get('recipeInstructions', [])
                if isinstance(steps, list):
                    recipe['instructions'] = [s.get('text', '') if isinstance(s, dict) else s for s in steps]
    except Exception:
        pass
    return recipe if recipe['ingredients'] or recipe['instructions'] else None

# ========== SAVE FUNCTIONS ========== #
def save_csv(data, path):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["source_url", "name", "ingredients", "instructions"])
        writer.writeheader()
        for r in data:
            writer.writerow({
                "source_url": r['source_url'],
                "name": r['name'],
                "ingredients": " | ".join(r['ingredients']),
                "instructions": " | ".join(r['instructions'])
            })

def save_json(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def save_jsonl(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        for item in data:
            f.write(json.dumps(item) + '\n')

# ========== MAIN SCRAPER ========== #
def main():
    all_recipes = []
    for site in tqdm(RECIPE_WEBSITES, desc="Scraping Sites"):
        try:
            links = get_links(site, MAX_RECIPES_PER_SITE)
            for link in links:
                recipe = parse_recipe(link)
                if recipe:
                    all_recipes.append(recipe)
                if len(all_recipes) >= MAX_TOTAL_RECIPES:
                    break
        except Exception as e:
            logging.error(f"Failed on site {site}: {e}")
        if len(all_recipes) >= MAX_TOTAL_RECIPES:
            break

    save_csv(all_recipes, os.path.join(DATA_DIR, 'recipes.csv'))
    save_json(all_recipes, os.path.join(DATA_DIR, 'recipes.json'))
    save_jsonl(all_recipes, os.path.join(DATA_DIR, 'recipes.json1'))
    logging.info(f"Saved {len(all_recipes)} recipes.")

if __name__ == '__main__':
    main()
