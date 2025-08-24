# Books Parser

Парсер сайта Books to Scrape.

Функционал:
- Парсит все страницы или ограниченное количество (--max-pages)
- Собирает поля: title, price, rating, availability, product_url
- Опционально собирает: category, description, upc, image_url (--details)
- Выгрузка в Excel или CSV (--output)

Примеры запуска:

# Все страницы в Excel
python books_parser.py --max-pages 0 --output output/books.xlsx

# Первые 3 страницы с деталями карточки
python books_parser.py --max-pages 3 --details --output output/books.xlsx
