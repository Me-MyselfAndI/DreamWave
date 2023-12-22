from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from compression.scraping.parser import Parser

from selenium.webdriver.chrome.options import Options

chrome_options = Options()
chrome_options.add_argument("--ignore-certificate-errors")
chrome_options.add_argument("--headless")

import sys
import os

current_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(current_dir)
vulkanai_dir = os.path.dirname(parent_dir)
sys.path.append(vulkanai_dir)

from compression.ai.gpt_engine import GPTEngine


class Crawler:
    def __init__(self, llm_engine):
        self.llm_engine = llm_engine
        options = Options()
        options.add_argument('--headless=new')
        self.driver = webdriver.Chrome(options=options)

    def get_page_source(self, url):
        self.driver.get(url)
        return self.driver.page_source

    def navigate_to_relevant_page(self, search_query, website, threshold=4, min_relevance_rate=0.15, max_recursion_depth=2, lang='english'):
        parser = Parser(website['url'], html=website['html'])
        compressed_original_page_tags = parser.find_text_content()
        page_content_relevance = self.query_llm_for_text_relevance(compressed_original_page_tags, search_query)
        curr_page_relevance_rate = len([1 for item in page_content_relevance if item >= threshold]) / len(page_content_relevance)
        if max_recursion_depth == 0 or curr_page_relevance_rate >= min_relevance_rate:
            return {
                'relevance': curr_page_relevance_rate,
                'url': website['url'],
                'html': website['html']
            }

        menu_items = parser.find_website_menu()

        print('Navigating in menus')
        menu_items_flattened = [
            {'item': item, 'text': item.get('text', '')} for ancestor in menu_items.values()
            for item in ancestor.get('items', [])
        ]
        llm_evaluations = self.query_llm_menus_for_relevance(menu_items_flattened, search_query, lang=lang)
        for i, eval in enumerate(llm_evaluations):
            menu_items_flattened[i]['score'] = eval

        print(f'Total of {len(menu_items_flattened)} items before purging')
        menu_items_flattened = [
            item for item in menu_items_flattened
            if item['score'] >= threshold and item['item']['href']
        ]

        print(f'Total of {len(menu_items_flattened)} items after purging')

        menu_items_flattened.sort(key=lambda x: -x['score'])
        # Navigate to the menu item that meets the relevance threshold
        for i, tag in enumerate(menu_items_flattened):
            item, score = tag.get('item'), tag.get('score')
            print(item, score)
            link = item.get('href', '')
            if not link:
                print('NO LINK', item)
                continue

            try:
                self.driver.get(link)
                self.handle_dropdowns(search_query)
                new_website = {
                    'url': link,
                    'html': self.driver.page_source
                }
                result = self.navigate_to_relevant_page(
                    search_query, new_website,
                    max_recursion_depth=max_recursion_depth-1,
                    threshold=threshold,
                    min_relevance_rate=min_relevance_rate, lang=lang
                )

                if result['relevance'] > curr_page_relevance_rate:
                    return result
                else:
                    return {
                        'relevance': curr_page_relevance_rate,
                        'url': website['url'],
                        'html': website['html']
                    }

            except Exception as e:
                print(f"\u001b[31mError processing {link}: {e}\u001b[0m")

        print('\u001b[31mReturned None - staying on the same page\u001b[0m')
        return {
            'relevance': curr_page_relevance_rate,
            'url': website['url'],
            'html': website['html']
        }

    def query_llm_menus_for_relevance(self, menu_items, search_query, lang):
        responses = self.llm_engine.get_responses_async('{}', [
            f"How likely is menu item \"{menu_item['item'].get('text', '')}\" at link \"{menu_item['item']['href']}\" "
            f"answers \"{search_query}\" Non-\"{lang}\" rejected. Respond number 1 to 5, NOTHING else"
            for menu_item in menu_items
        ])
        for i, response in enumerate(responses):
            try:
                responses[i] = int(response)
            except Exception:
                responses[i] = 0
                print(f'\u001b[33mWarning! GPT returned {response} for i = {i}\u001b[0m')

        return responses

    def query_llm_for_text_relevance(self, text_items, search_query):
        responses = self.llm_engine.get_responses_async('{}', [
            f"On a scale of 1 to 5 where 1 is completely irrelevant and 5 is the spot-on answer, how relevant is "
            f"the menu item \"{text_item['text']}\" to the query \"{search_query}\"? "
            f"Your response must only consist of a number from 1 to 5, NOTHING else at all"
            for text_item in text_items
        ])
        for i, response in enumerate(responses):
            try:
                responses[i] = int(response)
            except Exception:
                responses[i] = 0
                print(f'\u001b[33mWarning! GPT returned {response} for i = {i}\u001b[0m')

        return responses

    def handle_dropdowns(self, search_query):
        dropdowns = self.driver.find_elements(By.TAG_NAME, 'select')
        for dropdown in dropdowns:
            options = dropdown.find_elements(By.TAG_NAME, 'option')
            options_texts = [option.text for option in options]
            most_viable_option = self.llm_engine.get_response(
                f"Given the query '{search_query}', which of these options is most relevant: {options_texts}? Only Answer with the exact option")
            for option in options:
                if option.text == most_viable_option:
                    option.click()
                    break
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, '//*')))
