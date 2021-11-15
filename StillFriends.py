from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))

login = open("urls.txt").read().splitlines()
options = webdriver.ChromeOptions()
options.add_argument("user-data-dir=C:\\Users\\Johan\\AppData\\Local\\Google\\Chrome\\User Data")
s=Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=s, options=options)
#driver.get('https://m.facebook.com/Johanfer12/friends')
driver.get('https://m.facebook.com/Johanfer12/friends')

##Scrolling down the page

SCROLL_PAUSE_TIME = 0.5

# Get scroll height
last_height = driver.execute_script("return document.body.scrollHeight")

while True:
    # Scroll down to bottom
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    # Wait to load page
    time.sleep(SCROLL_PAUSE_TIME)

    # Calculate new scroll height and compare with last scroll height
    new_height = driver.execute_script("return document.body.scrollHeight")
    if new_height == last_height:
        break
    last_height = new_height

time.sleep(5)

Friends = driver.find_elements(By.XPATH,"//h3[contains(@class,'_52jh _5pxc _8yo0')]")
Friends2 = driver.find_elements(By.XPATH,"//h1[contains(@class,'_52jh _5pxc _8yo0')]")

count = 0

for friend in Friends:
    print(friend.text)
    count = count + 1

for friend in Friends2:
    print(friend.text)
    count = count + 1

print(count)