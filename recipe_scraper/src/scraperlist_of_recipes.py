import requests
from bs4 import BeautifulSoup
import json
import csv
import time
import random
from urllib.parse import urlparse
import re
import logging
from tqdm import tqdm

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('recipe_scraper')

# Configure browser-like headers
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}

# Recipe websites to scrape
RECIPE_WEBSITES = [
    "https://www.allrecipes.com/recipes/",
    "https://www.bbcgoodfood.com/recipes",
    "https://www.simplyrecipes.com/recipes/",
    "https://www.bonappetit.com/recipes",
    "https://www.epicurious.com/recipes-menus",
    "https://www.foodnetwork.com/recipes",
    "https://www.jamieoliver.com/recipes/",
    "https://www.delish.com/cooking/recipe-ideas/",
    "https://www.food.com/recipe",
    "https://www.eatingwell.com/recipes/",
    "https://www.cookinglight.com/food",
    "https://www.101cookbooks.com/archives/",
    "https://www.closetcooking.com/",
    "https://www.seriouseats.com/recipes",
    "https://www.twopeasandtheirpod.com/recipes/",
    "https://www.gimmesomeoven.com/recipes/",
    "https://www.damndelicious.net/recipe-index/",
    "https://www.thekitchn.com/recipes",
    "https://www.acouplecooks.com/category/recipes/",
    "https://www.minimalistbaker.com/recipes/"
]

# Track last request time per domain
domain_timers = {}

def make_request(url):
    """Make polite requests with rate limiting per domain"""
    domain = urlparse(url).netloc
    current_time = time.time()
    
    # Respect domain-specific delay
    if domain in domain_timers:
        elapsed = current_time - domain_timers[domain]
        if elapsed < 1.5:  # 1.5 second delay per domain
            time.sleep(1.5 - elapsed)
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        domain_timers[domain] = time.time()
        response.raise_for_status()  # Raise exception for 4xx/5xx responses
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {url}: {str(e)}")
        return None

def extract_recipe_data(url):
    """Extract recipe details from a URL with robust fallbacks"""
    logger.info(f"Extracting recipe from: {url}")
    response = make_request(url)
    if not response or response.status_code != 200:
        logger.warning(f"Failed to retrieve content from {url}")
        return None
    
    soup = BeautifulSoup(response.text, 'html.parser')
    recipe_data = {
        "name": "",
        "ingredients": [],
        "instructions": [],
        "source_url": url
    }
    
    # ====== NAME EXTRACTION ======
    # Try schema.org structured data
    script = soup.find('script', type='application/ld+json')
    if script:
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if item.get('@type') == 'Recipe' and item.get('name'):
                        recipe_data['name'] = item['name']
                        break
                else:
                    data = data[0] if data else {}
            elif isinstance(data, dict) and data.get('@type') == 'Recipe':
                recipe_data['name'] = data.get('name', '')
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug(f"JSON decode error in {url}: {str(e)}")
    
    # Fallback to HTML title
    if not recipe_data['name']:
        title_tag = soup.find('h1')
        if title_tag:
            recipe_data['name'] = title_tag.text.strip()
        else:
            og_title = soup.find('meta', property='og:title')
            if og_title:
                recipe_data['name'] = og_title.get('content', '').strip()
    
    # ====== INGREDIENTS EXTRACTION ======
    # Try schema.org structured data
    if script:
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if item.get('@type') == 'Recipe' and item.get('recipeIngredient'):
                        ingredients = item['recipeIngredient']
                        if isinstance(ingredients, list):
                            recipe_data['ingredients'] = [ing.strip() for ing in ingredients]
                        break
                else:
                    if isinstance(data, list) and data:
                        data = data[0]
            elif isinstance(data, dict) and data.get('@type') == 'Recipe':
                ingredients = data.get('recipeIngredient', [])
                if isinstance(ingredients, list):
                    recipe_data['ingredients'] = [ing.strip() for ing in ingredients]
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug(f"JSON decode error for ingredients: {str(e)}")
    
    # Fallback to common ingredient selectors
    if not recipe_data['ingredients']:
        ingredient_selectors = [
            '.ingredients', '.recipe-ingredients', '.ingredient', 
            '.ingredients-list', '.recipe-ingred_txt', '.wprm-recipe-ingredient',
            '.ingredients-section', '[class*="ingredient"]'
        ]
        
        for selector in ingredient_selectors:
            container = soup.select_one(selector)
            if container:
                ingredients = []
                # Try list items
                list_items = container.find_all(['li', 'p'])
                if list_items:
                    for item in list_items:
                        text = item.get_text(strip=True)
                        if text:
                            ingredients.append(text)
                # Try direct text extraction
                if not ingredients:
                    text = container.get_text('\n', strip=True)
                    if text:
                        ingredients = text.split('\n')
                
                if ingredients:
                    recipe_data['ingredients'] = ingredients
                    break
    
    # ====== INSTRUCTIONS EXTRACTION ======
    # Try schema.org structured data
    if script:
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if item.get('@type') == 'Recipe' and item.get('recipeInstructions'):
                        instructions = item['recipeInstructions']
                        if isinstance(instructions, list):
                            steps = []
                            for step in instructions:
                                if isinstance(step, dict) and step.get('@type') == 'HowToStep':
                                    steps.append(step.get('text', ''))
                                elif isinstance(step, str):
                                    steps.append(step)
                            recipe_data['instructions'] = steps
                        break
                else:
                    if isinstance(data, list) and data:
                        data = data[0]
            elif isinstance(data, dict) and data.get('@type') == 'Recipe':
                instructions = data.get('recipeInstructions', [])
                if isinstance(instructions, list):
                    steps = []
                    for step in instructions:
                        if isinstance(step, dict) and step.get('@type') == 'HowToStep':
                            steps.append(step.get('text', ''))
                        elif isinstance(step, str):
                            steps.append(step)
                    recipe_data['instructions'] = steps
                elif isinstance(instructions, str):
                    recipe_data['instructions'] = [instructions]
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug(f"JSON decode error for instructions: {str(e)}")
    
    # Fallback to common instruction selectors
    if not recipe_data['instructions']:
        instruction_selectors = [
            '.instructions', '.recipe-steps', '.directions', 
            '.recipe-instructions', '.wprm-recipe-instruction', 
            '.instructions-section', '[class*="instruction"]', 
            '[class*="direction"]', '[class*="step"]'
        ]
        
        for selector in instruction_selectors:
            container = soup.select_one(selector)
            if container:
                instructions = []
                # Try ordered list items
                list_items = container.find_all(['li', 'p'])
                if list_items:
                    for item in list_items:
                        text = item.get_text(strip=True)
                        if text:
                            instructions.append(text)
                # Try direct text extraction
                if not instructions:
                    text = container.get_text('\n', strip=True)
                    if text:
                        instructions = text.split('\n')
                
                if instructions:
                    recipe_data['instructions'] = instructions
                    break
    
    # Clean up data
    recipe_data['name'] = recipe_data['name'].replace('\n', ' ').strip() or 'Unknown Recipe Name'
    recipe_data['ingredients'] = [ing.replace('\n', ' ').strip() for ing in recipe_data['ingredients']]
    recipe_data['instructions'] = [step.replace('\n', ' ').strip() for step in recipe_data['instructions']]
    
    # Validate we have at least some data
    if not recipe_data['ingredients'] and not recipe_data['instructions']:
        logger.warning(f"Incomplete data extracted from {url}")
    
    return recipe_data

def get_recipe_links(site_url, max_links=5):
    """Get recipe links from a website's recipe section with multiple strategies"""
    logger.info(f"Getting recipe links from: {site_url}")
    response = make_request(site_url)
    if not response or response.status_code != 200:
        logger.warning(f"Failed to retrieve {site_url}")
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    links = set()
    domain = urlparse(site_url).netloc
    
    # Strategy 1: Find links in recipe cards
    card_selectors = [
        '.card', '.recipe-card', '.post-card', '.item', 
        '.teaser', '.summary', '.content-card', '.result'
    ]
    for selector in card_selectors:
        cards = soup.select(selector)
        for card in cards:
            a_tags = card.find_all('a', href=True)
            for a in a_tags:
                href = a['href']
                if href.startswith('/'):
                    href = f"https://{domain}{href}"
                if href.startswith('http') and domain in href:
                    links.add(href)
                if len(links) >= max_links * 2:
                    break
    
    # Strategy 2: Find links with recipe in URL
    if len(links) < max_links:
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('/'):
                href = f"https://{domain}{href}"
            if href.startswith('http') and domain in href:
                if any(keyword in href.lower() for keyword in ['recipe', 'recipes', 'dish', 'cook', 'make']):
                    links.add(href)
            if len(links) >= max_links * 2:
                break
    
    # Strategy 3: Find links with recipe in text
    if len(links) < max_links:
        for a in soup.find_all('a', href=True):
            text = a.get_text(strip=True).lower()
            if 'recipe' in text or 'cook' in text or 'make' in text:
                href = a['href']
                if href.startswith('/'):
                    href = f"https://{domain}{href}"
                if href.startswith('http') and domain in href:
                    links.add(href)
                if len(links) >= max_links * 2:
                    break
    
    # Return up to max_links
    return list(links)[:max_links]

def scrape_and_save():
    """Main function to scrape recipes and save to CSV"""
    all_recipes = []
    
    logger.info("Starting recipe scraping...")
    
    # Open CSV file early to write headers
    with open('recipes.csv', 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['source_url', 'recipe_name', 'ingredients', 'instructions']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        # Process each website
        for website in tqdm(RECIPE_WEBSITES, desc="Processing websites"):
            logger.info(f"Processing website: {website}")
            try:
                recipe_links = get_recipe_links(website, max_links=5)
                logger.info(f"Found {len(recipe_links)} recipe links at {website}")
                
                for link in recipe_links:
                    try:
                        recipe = extract_recipe_data(link)
                        if recipe:
                            # Validate we have at least ingredients or instructions
                            if recipe['ingredients'] or recipe['instructions']:
                                # Write to CSV immediately
                                writer.writerow({
                                    'source_url': recipe['source_url'],
                                    'recipe_name': recipe['name'],
                                    'ingredients': '\n'.join(recipe['ingredients']),
                                    'instructions': '\n'.join(recipe['instructions'])
                                })
                                csvfile.flush()  # Ensure data is written after each recipe
                                logger.info(f"Saved: {recipe['name'][:50]}...")
                                all_recipes.append(recipe)
                            else:
                                logger.warning(f"Skipping recipe with no data: {link}")
                        else:
                            logger.warning(f"Failed to extract recipe from {link}")
                    except Exception as e:
                        logger.error(f"Error processing recipe {link}: {str(e)}")
                    
                    # Exit if we have enough recipes
                    if len(all_recipes) >= 100:
                        logger.info("Reached 100 recipes. Stopping early.")
                        break
                
                if len(all_recipes) >= 100:
                    break
            except Exception as e:
                logger.error(f"Error processing website {website}: {str(e)}")
    
    logger.info(f"Successfully scraped {len(all_recipes)} recipes!")
    logger.info("Results saved to recipes.csv")

if __name__ == "__main__":
    scrape_and_save()