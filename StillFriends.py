from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium import webdriver
import time
import os

#Set current working directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

#https://m.facebook.com/(your_username))/friends in urls.txt

urls = open("urls.txt").read().splitlines()
fb = urls[0]
options = webdriver.ChromeOptions()
options.add_argument("user-data-dir=C:\\Users\\Johan\\AppData\\Local\\Google\\Chrome\\User Data")
s=Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=s, options=options)
driver.get(fb)

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

#Loading friend list

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