import requests
from bs4 import BeautifulSoup
import csv
import json
import re
import time
import os
import sys
import subprocess
from urllib.parse import quote

# Attempt to install required packages
try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Installing required packages...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4"])
    import requests
    from bs4 import BeautifulSoup

# Configuration with robust fallback selectors
SITE_CONFIG = {
    "BBC Good Food": {
        "search_url": "https://www.bbcgoodfood.com/search?q={}",
        "recipe_selector": "a.standard-card-new__article-title, a.heading-4, div.card__content a",
        "time_selector": ".icon-time, .cook-and-prep-time, .time",
        "ingredients_selector": ".recipe__ingredients li, .ingredients-list__item, .ingredient",
        "instructions_selector": ".recipe__method-steps li, .method__item, .instruction"
    },
    "AllRecipes": {
        "search_url": "https://www.allrecipes.com/search?q={}",
        "recipe_selector": "a.card__titleLink, a.recipeCard__titleLink",
        "time_selector": ".recipe-meta-item-body, .m-recipe-meta__item",
        "ingredients_selector": ".ingredients-item-name, .m-ingredient__name",
        "instructions_selector": ".instructions-section-item p, .paragraph"
    }
}

def get_headers():
    """Generate headers for requests"""
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Referer': 'https://www.google.com/'
    }

def get_recipe_details(url, site_name):
    """Extract recipe details with comprehensive error handling"""
    print(f"🔍 Extracting recipe from {url}")
    try:
        headers = get_headers()
        response = requests.get(url, headers=headers, timeout=20)
        
        if response.status_code != 200:
            print(f"⚠️ HTTP Error {response.status_code} for {url}")
            return None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract recipe name
        name = soup.find('h1').get_text(strip=True) if soup.find('h1') else "Untitled Recipe"
        print(f"✅ Found recipe: {name}")
        
        # Extract cooking time
        time_config = SITE_CONFIG[site_name]
        time_element = None
        for selector in time_config["time_selector"].split(', '):
            time_element = soup.select_one(selector.strip())
            if time_element:
                break
        cooking_time = time_element.get_text(strip=True) if time_element else "Not specified"
        print(f"⏱️ Cooking time: {cooking_time}")
        
        # Extract ingredients
        ingredients = []
        for selector in time_config["ingredients_selector"].split(', '):
            ingredients_elements = soup.select(selector.strip())
            if ingredients_elements:
                for item in ingredients_elements:
                    ingredient = item.get_text(strip=True)
                    if ingredient:
                        ingredients.append(ingredient)
                if ingredients:
                    break
        print(f"📋 Found {len(ingredients)} ingredients")
        
        # Extract instructions
        instructions = []
        for selector in time_config["instructions_selector"].split(', '):
            instructions_elements = soup.select(selector.strip())
            if instructions_elements:
                for i, step in enumerate(instructions_elements, 1):
                    instruction = step.get_text(strip=True)
                    if instruction:
                        instructions.append(f"{i}. {instruction}")
                if instructions:
                    break
        print(f"👩‍🍳 Found {len(instructions)} instructions")
        
        return {
            'site': site_name,
            'name': name,
            'url': url,
            'cooking_time': cooking_time,
            'ingredients': ingredients,
            'instructions': instructions
        }
    
    except Exception as e:
        print(f"⚠️ Error scraping {url}: {str(e)}")
        # Save error details for debugging
        with open('recipe_error.html', 'w', encoding='utf-8') as f:
            f.write(response.text if 'response' in locals() else 'No response')
        print("⚠️ Saved HTML to recipe_error.html for inspection")
        return None

def search_recipes(recipe_name):
    """Search for recipes across configured sites"""
    all_recipes = []
    query = quote(recipe_name)
    
    for site_name, config in SITE_CONFIG.items():
        print(f"\n🌐 Searching {site_name} for '{recipe_name}'...")
        try:
            search_url = config["search_url"].format(query)
            print(f"🔗 Search URL: {search_url}")
            
            headers = get_headers()
            response = requests.get(search_url, headers=headers, timeout=20)
            
            if response.status_code != 200:
                print(f"⚠️ HTTP Error {response.status_code} on {site_name}")
                continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            recipe_links = []
            
            # Find recipe links using multiple selectors
            for selector in config["recipe_selector"].split(', '):
                links = soup.select(selector.strip())
                if links:
                    for link in links:
                        href = link.get('href', '')
                        if href:
                            # Convert relative URLs to absolute
                            if not href.startswith('http'):
                                if 'bbcgoodfood' in search_url:
                                    href = f"https://www.bbcgoodfood.com{href}"
                                elif 'allrecipes' in search_url:
                                    href = f"https://www.allrecipes.com{href}"
                            recipe_links.append(href)
                    if recipe_links:
                        break
            
            if recipe_links:
                print(f"🔗 Found {len(recipe_links)} recipe links")
                # Get details for the first recipe found
                recipe = get_recipe_details(recipe_links[0], site_name)
                if recipe:
                    all_recipes.append(recipe)
                    print(f"✅ Successfully scraped recipe from {site_name}")
                else:
                    print(f"⚠️ Failed to extract recipe details from {site_name}")
            else:
                print(f"⚠️ No recipes found on {site_name}")
                
        except Exception as e:
            print(f"🚨 Error searching {site_name}: {str(e)}")
    
    return all_recipes

def save_to_csv(recipes, filename):
    """Save recipes to a CSV file"""
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['Site', 'Recipe Name', 'URL', 'Cooking Time', 'Ingredients', 'Instructions'])
            
            for recipe in recipes:
                ingredients = '\n'.join(recipe['ingredients'])
                instructions = '\n'.join(recipe['instructions'])
                writer.writerow([
                    recipe['site'],
                    recipe['name'],
                    recipe['url'],
                    recipe['cooking_time'],
                    ingredients,
                    instructions
                ])
        return True
    except Exception as e:
        print(f"⚠️ Error saving CSV: {str(e)}")
        return False

def save_to_json(recipes, filename):
    """Save recipes to a JSON file"""
    try:
        with open(filename, 'w', encoding='utf-8') as file:
            json.dump(recipes, file, indent=2)
        return True
    except Exception as e:
        print(f"⚠️ Error saving JSON: {str(e)}")
        return False

def main():
    """Main function to run the recipe finder"""
    print("="*60)
    print("🍳 RECIPE FINDER - GET INGREDIENTS, INSTRUCTIONS & COOKING TIME")
    print("="*60)
    
    recipe_name = input("\nEnter recipe name: ").strip()
    
    if not recipe_name:
        print("⚠️ Using 'chicken curry' as default recipe")
        recipe_name = "chicken curry"
    
    print(f"\n🔍 Searching for '{recipe_name}'...")
    
    try:
        recipes = search_recipes(recipe_name)
        
        if not recipes:
            print("\n❌ No recipes found. Possible reasons:")
            print("- Websites might be blocking our requests")
            print("- Recipe not available on supported sites")
            print("- Website structure changed (we'll update the script)")
            print("\n💡 Try these popular recipes instead: chocolate chip cookies, spaghetti bolognese, pancakes")
            return
        
        print(f"\n✅ Found {len(recipes)} recipes")
        
        # Create output directory if not exists
        os.makedirs('recipe_output', exist_ok=True)
        
        # Sanitize filename
        safe_name = re.sub(r'[^\w\s]', '', recipe_name).replace(' ', '_')
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        # Save outputs
        csv_filename = f"recipe_output/{safe_name}_{timestamp}.csv"
        json_filename = f"recipe_output/{safe_name}_{timestamp}.json"
        
        csv_success = save_to_csv(recipes, csv_filename)
        json_success = save_to_json(recipes, json_filename)
        
        print("\n" + "="*60)
        if csv_success:
            print(f"📄 CSV saved: {csv_filename}")
        if json_success:
            print(f"📄 JSON saved: {json_filename}")
        
        print("\n💡 TIP: If you got no results, try:")
        print("- Using a different recipe name")
        print("- Checking your internet connection")
        print("- Running the script again later")
        
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {str(e)}")
        print("Please report this issue with the error message")

if __name__ == "__main__":
    main()