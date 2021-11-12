from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium import webdriver
import time

options = webdriver.ChromeOptions()
#options.add_argument("--log-level=OFF")
#options.add_argument("--ignore-certificate-error")
#options.add_argument("--ignore-ssl-errors")
#options.add_argument('--headless')
#options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("user-data-dir=C:\\Users\\Johan\\AppData\\Local\\Google\\Chrome\\User Data")
s=Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=s, options=options)



driver.get('https://m.facebook.com/Johanfer12/friends')
time.sleep(5)

Friends = driver.find_elements(By.XPATH,'//*[@id="root"]/div/div/div[3]/div[1]/div[1]/div[2]/div/div[1]/h3')
x = driver.find_elements(By.CSS_SELECTOR("_52jh _5pxc _8yo0"))
for i in x:
    t = i.get_attribute("text")
    print("aaaa"+str(t))
    print("bbbbb"+str(i))

print(Friends)

#time.sleep(1000)