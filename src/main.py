from selenium import webdriver
from selenium.webdriver.firefox.options import Options

# plus for
# https://youtu.be/NB8OceGZGjA?t=587
# class WebDriverWrapper:
#     def __init__(self, sel_driver: driver) -> None:
#         pass


def main() -> None:
    options = Options()
    options.set_preference(name="dom.webdriver.enabled", value=False)
    options.set_preference(name="useAutomationExtension", value=False)

    driver = webdriver.Firefox(options=options)

    try:
        driver.get("https://example.com/")
        print(driver.title)
        print("Current URL:", driver.current_url)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
