import requests
from bs4 import BeautifulSoup
import json
import csv
import time
import os
from urllib.parse import urlparse, urljoin
from tqdm import tqdm
import logging

# ========== SETUP ========== #
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
}
RECIPE_WEBSITES = [
    "https://101cookbooks.com/",
    "https://www.allrecipes.com/",
    "https://www.bbc.co.uk/food/recipes/",
    "https://www.bbcgoodfood.com/recipes/",
    "https://www.bonappetit.com/recipes/",
    "https://www.closetcooking.com/",
    "https://www.epicurious.com/recipes/",
    "https://www.finedininglovers.com/recipes/",
    "https://www.foodrepublic.com/recipes/",
    "https://www.jamieoliver.com/recipes/",
    "https://www.mybakingaddiction.com/recipes/",
    "https://www.paninihappy.com/",
    "https://www.realsimple.com/food-recipes",
    "https://www.simplyrecipes.com/recipes/",
    "https://steamykitchen.com/recipes/",
    "https://tastykitchen.com/recipes/",
    "https://thepioneerwoman.com/food-cooking/recipes/",
    "https://www.thevintagemixer.com/recipe-index/",
    "https://www.twopeasandtheirpod.com/recipes/",
    "https://whatsgabycooking.com/recipes/"
]
RATE_LIMIT = 2.0  # Increased from 1.5
MAX_RECIPES_PER_SITE = 10
MAX_TOTAL_RECIPES = 500
DATA_DIR = "data"
TIMEOUT = 15  # Increased timeout

# ========== LOGGING ========== #
os.makedirs(DATA_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(DATA_DIR, 'scraper.log')),
        logging.StreamHandler()
    ]
)
domain_timers = {}
seen_urls = set()  # Track seen URLs to avoid duplicates

# ========== HELPERS ========== #
def normalize_domain(url):
    """Remove www and protocol variations"""
    domain = urlparse(url).netloc.lower()
    return domain[4:] if domain.startswith('www.') else domain

def make_request(url):
    domain = normalize_domain(url)
    now = time.time()
    
    # Rate limiting
    if domain in domain_timers:
        elapsed = now - domain_timers[domain]
        if elapsed < RATE_LIMIT:
            sleep_time = RATE_LIMIT - elapsed
            time.sleep(sleep_time)
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        domain_timers[domain] = time.time()
        res.raise_for_status()
        
        # Check content type
        content_type = res.headers.get('Content-Type', '').lower()
        if 'text/html' not in content_type:
            logging.warning(f"Non-HTML content at {url}: {content_type}")
            return None
            
        return res
    except Exception as e:
        logging.warning(f"Request failed for {url}: {str(e)}")
        return None

def get_links(site_url, max_links):
    res = make_request(site_url)
    if not res: 
        return []
        
    soup = BeautifulSoup(res.text, 'html.parser')
    links = set()
    base_domain = normalize_domain(site_url)
    
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if not href or href.startswith(('javascript:', 'mailto:', 'tel:')):
            continue
            
        # Build absolute URL
        full_url = urljoin(site_url, href)
        parsed = urlparse(full_url)
        
        # Skip non-HTTP links and external domains
        if parsed.scheme not in ('http', 'https'):
            continue
        if normalize_domain(full_url) != base_domain:
            continue
            
        # Check if URL looks like a recipe
        path = parsed.path.lower()
        if any(kw in path for kw in ['recipe', 'recipes', 'cook', 'dish', 'receipt', 'food']):
            if full_url not in seen_urls:
                links.add(full_url)
                seen_urls.add(full_url)
                
        if len(links) >= max_links:
            break
            
    return list(links)

def parse_recipe(url):
    res = make_request(url)
    if not res: 
        return None
        
    soup = BeautifulSoup(res.text, 'html.parser')
    recipe = {
        "source_url": url,
        "name": "",
        "ingredients": [],
        "instructions": []
    }
    
    # Try to find JSON-LD recipe data
    script_tags = soup.find_all('script', type='application/ld+json')
    for script in script_tags:
        try:
            # Handle commented JSON
            data_str = script.string.strip()
            if data_str.startswith('<!--'):
                data_str = data_str[4:-3].strip()  # Remove HTML comments
                
            data = json.loads(data_str)
            
            # Handle different JSON-LD structures
            if isinstance(data, list):
                items = data
            elif '@graph' in data:
                items = data['@graph']
            else:
                items = [data]
                
            for item in items:
                if not isinstance(item, dict):
                    continue
                    
                # Check for Recipe type
                if item.get('@type') in ['Recipe', 'HowTo']:
                    # Get name
                    name = item.get('name') or item.get('headline', '')
                    if name:
                        recipe['name'] = name
                    
                    # Get ingredients
                    ingredients = item.get('recipeIngredient', [])
                    if ingredients:
                        recipe['ingredients'] = ingredients
                    
                    # Get instructions
                    instructions = []
                    steps = item.get('recipeInstructions', [])
                    
                    if isinstance(steps, str):
                        instructions = [steps]
                    elif isinstance(steps, list):
                        for step in steps:
                            if isinstance(step, dict):
                                if step.get('@type') == 'HowToStep':
                                    instructions.append(step.get('text', ''))
                            elif isinstance(step, str):
                                instructions.append(step)
                    
                    recipe['instructions'] = instructions
                    
                    # Return if we have valid data
                    if recipe['ingredients'] and recipe['instructions']:
                        return recipe
                        
        except Exception as e:
            logging.debug(f"JSON-LD parse error at {url}: {str(e)}")
    
    return None  # No valid recipe found

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
        json.dump(data, f, indent=2, ensure_ascii=False)

def save_jsonl(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

# ========== MAIN SCRAPER ========== #
def main():
    all_recipes = []
    
    for site in tqdm(RECIPE_WEBSITES, desc="Scraping Sites"):
        try:
            logging.info(f"Processing site: {site}")
            links = get_links(site, MAX_RECIPES_PER_SITE)
            
            if not links:
                logging.warning(f"No recipe links found for {site}")
                continue
                
            for link in tqdm(links, desc=f"Scraping {urlparse(site).netloc}", leave=False):
                if len(all_recipes) >= MAX_TOTAL_RECIPES:
                    break
                    
                recipe = parse_recipe(link)
                if recipe:
                    all_recipes.append(recipe)
                    logging.info(f"✓ Collected recipe: {recipe['name'][:50]}...")
                else:
                    logging.debug(f"✗ Not a recipe page: {link}")
                    
                # Progress tracking
                if len(all_recipes) % 10 == 0:
                    logging.info(f"Total recipes: {len(all_recipes)}/{MAX_TOTAL_RECIPES}")
                    
        except Exception as e:
            logging.error(f"Failed on site {site}: {str(e)}")
            time.sleep(5)  # Pause after failure
            
        if len(all_recipes) >= MAX_TOTAL_RECIPES:
            break

    # Save results
    save_csv(all_recipes, os.path.join(DATA_DIR, 'recipes.csv'))
    save_json(all_recipes, os.path.join(DATA_DIR, 'recipes.json'))
    save_jsonl(all_recipes, os.path.join(DATA_DIR, 'recipes.jsonl'))
    logging.info(f"Successfully saved {len(all_recipes)} recipes")

if __name__ == '__main__':
    main()