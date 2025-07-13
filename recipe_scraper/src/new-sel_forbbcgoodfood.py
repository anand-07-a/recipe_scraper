import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import json

def get_recipe_links_bbc(query):
    """Get recipe links from BBC Good Food using direct HTML parsing"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    # First try to find recipes through search
    search_url = f"https://www.bbcgoodfood.com/search?q={query.replace(' ', '%20')}"
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        recipe_links = []
        
        # Try multiple selector patterns
        selectors = [
            "a.standard-card-new__article-title",  # Primary selector
            "a.heading-4",  # Fallback selector 1
            "div.gfc-standard-card-new a",  # Fallback selector 2
            "div.card__content a"  # Fallback selector 3
        ]
        
        for selector in selectors:
            links = soup.select(selector)
            if links:
                for link in links:
                    href = link.get('href', '')
                    if href and '/recipes/' in href:
                        full_url = f"https://www.bbcgoodfood.com{href}" if not href.startswith('http') else href
                        recipe_links.append(full_url)
                if recipe_links:
                    return list(set(recipe_links))  # Remove duplicates
        
        # If no links found, try to extract from JSON-LD data
        script_tags = soup.find_all('script', type='application/ld+json')
        for script in script_tags:
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    for item in data:
                        if item.get('@type') == 'ItemList' and 'itemListElement' in item:
                            for element in item['itemListElement']:
                                if 'url' in element:
                                    url = element['url']
                                    if '/recipes/' in url:
                                        recipe_links.append(url)
            except json.JSONDecodeError:
                continue
        
        return list(set(recipe_links))
    
    except Exception as e:
        print(f"⚠️ Request failed: {str(e)}")
        return []

def get_recipe_details(url):
    """Get detailed recipe information from a BBC Good Food recipe page"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract recipe name
        name = soup.find('h1').get_text(strip=True) if soup.find('h1') else "Untitled Recipe"
        
        # Extract cooking time
        time_element = soup.select_one('.icon-time')
        cooking_time = time_element.parent.get_text(strip=True) if time_element else "Not specified"
        
        # Extract ingredients
        ingredients = []
        ingredients_section = soup.select_one('.recipe__ingredients')
        if ingredients_section:
            ingredients_list = ingredients_section.select('li')
            for item in ingredients_list:
                ingredient = item.get_text(strip=True)
                if ingredient:
                    ingredients.append(ingredient)
        
        # DEBUG: Print ingredients to verify extraction
        print(f"\nIngredients found: {len(ingredients)}")
        for i, ing in enumerate(ingredients[:3], 1):
            print(f"  {i}. {ing}")
        
        # Extract method - IMPROVED SELECTORS
        method = []
        method_section = soup.select_one('.recipe__method-steps')
        
        if not method_section:
            # Try alternative selectors
            method_section = soup.select_one('.method__list, .method__container, .method-steps')
        
        if method_section:
            # Try different ways to find steps
            method_steps = method_section.select('li, p, div[itemprop="recipeInstructions"]')
            
            if not method_steps:
                # If no list items, try getting direct text
                method_text = method_section.get_text(strip=True)
                if method_text:
                    # Split by numbers if steps are numbered in text
                    steps = re.split(r'\d+\.', method_text)
                    steps = [s.strip() for s in steps if s.strip()]
                    for i, step in enumerate(steps, 1):
                        method.append(f"{i}. {step}")
            
            else:
                # Process list items
                for i, step in enumerate(method_steps, 1):
                    # Clean text by removing step numbers if present
                    step_text = step.get_text(strip=True)
                    if step_text.startswith(f"{i}."):
                        step_text = step_text[len(f"{i}."):].strip()
                    method.append(f"{i}. {step_text}")
            
            # DEBUG: Print method steps
            print(f"Method steps found: {len(method)}")
            for i, step in enumerate(method[:3], 1):
                print(f"  {i}. {step[:60]}...")
        else:
            print("⚠️ Method section not found in HTML")
            # Save HTML for debugging
            with open('recipe_debug.html', 'w', encoding='utf-8') as f:
                f.write(response.text)
            print("⚠️ Saved HTML to recipe_debug.html for inspection")
        
        # Extract rating
        rating_element = soup.select_one('.rating__average-text')
        rating = rating_element.get_text(strip=True) if rating_element else "Not rated"
        
        return {
            'name': name,
            'url': url,
            'cooking_time': cooking_time,
            'rating': rating,
            'ingredients': ingredients,
            'method': method
        }
    
    except Exception as e:
        print(f"⚠️ Failed to get recipe details: {str(e)}")
        return None

def get_recipe_links_selenium(query):
    """Fallback method using Selenium when direct requests fail"""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
    
    try:
        service = Service(executable_path='chromedriver.exe')
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(f"https://www.bbcgoodfood.com/search?q={query.replace(' ', '%20')}")
        
        # Wait for recipes to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a.standard-card-new__article-title"))
        )
        
        # Get all recipe links
        recipe_links = []
        links = driver.find_elements(By.CSS_SELECTOR, "a.standard-card-new__article-title")
        for link in links:
            href = link.get_attribute('href')
            if href and '/recipes/' in href:
                recipe_links.append(href)
        
        driver.quit()
        return list(set(recipe_links))
    
    except Exception as e:
        print(f"⚠️ Selenium failed: {str(e)}")
        return []

def display_recipe(recipe):
    """Display recipe in a readable format"""
    print("\n" + "="*50)
    print(f"🍳 {recipe['name']}")
    print("-"*50)
    print(f"⏱️  Cooking Time: {recipe['cooking_time']}")
    print(f"⭐ Rating: {recipe['rating']}")
    print(f"🔗 URL: {recipe['url']}")
    
    print("\n📋 Ingredients:")
    for ingredient in recipe['ingredients']:
        print(f" - {ingredient}")
    
    print("\n👩‍🍳 Method:")
    if recipe['method']:
        for step in recipe['method']:
            print(step)
    else:
        print("⚠️ No method steps found for this recipe")
        print("This could be due to:")
        print("1. The recipe page structure has changed")
        print("2. The recipe doesn't have detailed instructions")
        print("3. There was an error extracting the method")
        print("Check the URL for full instructions: " + recipe['url'])
    
    print("="*50 + "\n")

def main():
    print("🔍 BBC Good Food Recipe Finder")
    query = input("Enter the recipe you want to find: ").strip()
    
    if not query:
        query = "chicken curry"
        print(f"Using default search: {query}")
    
    print(f"\n🚀 Searching BBC Good Food for '{query}'...")
    
    # First try direct method
    recipe_links = get_recipe_links_bbc(query)
    
    # If no results, try Selenium fallback
    if not recipe_links:
        print("ℹ️ Direct search failed, trying with browser automation...")
        recipe_links = get_recipe_links_selenium(query)
    
    if not recipe_links:
        print("\n❌ No recipes found. Please try a different search term.")
        return
    
    print(f"\n✅ Found {len(recipe_links)} recipes. Getting details for the first one...")
    
    # Get details for the first recipe
    recipe = get_recipe_details(recipe_links[0])
    
    if recipe:
        display_recipe(recipe)
        
        # Offer to show more recipes
        if len(recipe_links) > 1:
            show_more = input(f"Show next recipe? ({len(recipe_links)-1} more available) (y/n): ").lower()
            if show_more == 'y':
                recipe = get_recipe_details(recipe_links[1])
                if recipe:
                    display_recipe(recipe)
    else:
        print("❌ Failed to retrieve recipe details")

if __name__ == "__main__":
    main()