from compression.ai.astica_engine import AsticaEngine
from compression.scraping.crawler import Crawler
from compression.ai.gpt_engine import GPTEngine
from compression.scraping.parser import Parser


class ScrapingController:
    def __init__(self, gpt=None, astica=None):
        if gpt is None:
            self._gpt = GPTEngine()
        else:
            self._gpt = gpt

        if astica is None:
            self._astica = AsticaEngine()
        else:
            self._astica = astica

    def _filter_marketplace_products(self, product_info, search_query, threshold=3):
        print(f"Products ({len(product_info)}):")
        for i, product in enumerate(product_info):
            print(i, product)

        filtered_products = []
        nonempty_description_products = []
        for i, product in enumerate(product_info):
            # Filter out all fully-empty items
            for text_piece in product['text']:
                if text_piece.strip() != '':
                    break
            else:
                continue
            nonempty_description_products.append(product)

        print("Products with descriptions:")
        for i, product in enumerate(nonempty_description_products):
            print(i, product)

        # astica_descriptions = []
        # for i, (product, (astica_response_code, astica_result)) in enumerate(
        #     zip(
        #         nonempty_description_products,
        #         self._astica.get_image_descriptions_async(list(map(lambda x: x['img'], nonempty_description_products)))
        #     )
        # ):
        #     try:
        #         if astica_response_code != 200:
        #             print(f'\u001b[31mAstica returned code {astica_response_code} on this product; error message: {astica_result}\n skipping\u001b[0m')
        #             astica_descriptions.append(f'NO IMAGE-BASED DESCRIPTION: {astica_result}')
        #         else:
        #             astica_descriptions.append(astica_result)
        #     except Exception as e:
        #         print(f'\u001b[31mException {e} encountered with this product; skipping\u001b[0m')
        #         astica_descriptions.append(
        #             f'NO IMAGE-BASED DESCRIPTION')

        args, image_urls = [], []
        for product in nonempty_description_products:
            prompt = (f"Given the user's preference of '{search_query}', how well does the product "
                      f"with data '{product['text']}' with this image match the "
                      f"criteria? Answer from 1 (not relevant at all) to 5 (great match). "
                      f"Only return the number, nothing else")
            args.append(prompt)
            image_urls.append([product['img']])
        gpt_responses = self._gpt.get_responses_async('{}', args=args, image_urls=image_urls)

        for i, (product, gpt_response) in enumerate(zip(nonempty_description_products, gpt_responses)):
            try:
                if not '1' <= gpt_response <= '5' or len(gpt_response) > 1:
                    print(f"\u001b[31mWARNING! BAD RESPONSE: {gpt_response}")
                    gpt_response = 0

                gpt_response = int(gpt_response)
                print(product, gpt_response, "\n")

                if gpt_response >= threshold:
                    filtered_products.append(product)
            except Exception as e:
                print(f'\u001b[31mException {e} encountered with this product; skipping\u001b[0m')
                continue
        return filtered_products

    def _generate_container_html(self, products):
        html_content = """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>VulkanAI - Filtered Products</title>
                <style>
                    .products {
                        display: flex;
                        flex-wrap: wrap;
                        gap: 20px;
                        justify-content: center;
                    }
                    .product {
                        border: 1px solid #ddd;
                        padding: 10px;
                        box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
                        width: 150px;
                        text-align: center;
                    }
                    .product img {
                        max-width: 100%;
                        max-height: 100px;
                    }
                </style>
            </head>
            <body>
            <div class="products">
            """

        product_titles = self._gpt.get_responses_async(
            "A product in a marketplace has properties: {}. Some of it is the title. Find it, "
            "and print. Give NO other text aside from what I asked. ", [product['text'] for product in products])
        for product, product_title in zip(products, product_titles):
            product_block = f"""
                <div class="product">
                    <a href="{product['href']}" target="_blank">
                        <img src="{product['img']}" alt="{product['text']}">
                        <p>{product_title}</p>
                    </a>
                </div>
                """
            html_content += product_block

        html_content += """
                </div>
            </body>
            </html>
            """

        return html_content

    def _generate_text_wesite_html(self, parsed_content, search_query, threshold=3):
        html_content = """
                        <!DOCTYPE html>
                        <html lang="en">
                        <head>
                            <meta charset="UTF-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                            <title>VulkanAI - Filtered Website</title>
                            <style>
                                .products {
                                    display: flex;
                                    flex-wrap: wrap;
                                    gap: 20px;
                                    justify-content: center;
                                }
                                .product {
                                    border: 1px solid #ddd;
                                    padding: 10px;
                                    box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
                                    width: 150px;
                                    text-align: center;
                                }
                                .product img {
                                    max-width: 100%;
                                    max-height: 100px;
                                }
                            </style>
                        </head>
                        <body>
                        <div class="products">
                    """

        for i, element in enumerate(parsed_content):
            request = (f"On a scale of 1 to 5, how likely is it that the menu item \"{element['text']}\" contains "
                       f"what the query '{search_query}' is searching for? Make sure the response only consists of a "
                       f"number between 1 to 5, NOTHING else")
            response = self._gpt.get_response(request)
            print(i, element['text'], response)
            if not '1' <= response <= '5' or len(response) > 1:
                print(f"\u001b[31mWARNING! BAD RESPONSE: {response}")
                continue

            if int(response) >= threshold:
                html_content += f"""
                            <div>
                                {element['tag']}
                            </div>
                            """
        html_content += """
                            </div>
                        </body>
                        </html>
                        """
        return html_content

    def get_parsed_website_html(self, website, search_query, threshold=4):

        marketplace_likelihood = self._gpt.get_response(
            f'Is this query {search_query} on this website {website["url"]} likely to be a marketplace? Rate the '
            f'likelihood from 1 to 5, and output nothing other than the number')

        if marketplace_likelihood >= '4':
            parser = Parser(website['url'], html=website['html'])
            product_groups = parser.find_container_groups(website['url'])
            filtered_products = self._filter_marketplace_products(product_groups, search_query)
            return self._generate_container_html(filtered_products)

        else:
            crawler = Crawler(self._gpt)
            crawled_page = crawler.navigate_to_relevant_page(search_query, website, threshold=threshold, lang=website.get('lang', 'english'))

            print('crawled page URL:', crawled_page['url'])
            crawled_page_parser = Parser(crawled_page['url'], html=crawled_page['html'])
            parsed_content = crawled_page_parser.find_text_content()

            threshold = 3

            return self._generate_text_wesite_html(parsed_content, search_query, threshold=threshold)


def main():
    scraping_controller = ScrapingController()
    with open('compression/test_input.html', encoding='utf-8') as file:
        products_html = file.read()
    print(scraping_controller.get_parsed_website_html(
        {
            'url': 'https://www.amazon.com/s?k=bike+tires&crid=VO1Z0N6VACIT&sprefix=bike+tires%2Caps%2C107&ref=nb_sb_noss_1',
            'html': products_html,
            'lang': 'english'
        },
        'Tires for a road bike'
    ))


if __name__ == '__main__':
    main()
