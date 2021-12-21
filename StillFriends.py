from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium import webdriver
from datetime import datetime
import itertools
import tweepy
import time
import os

#Set current working directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

#https://m.facebook.com/(your_username))/friends in urls.txt
#C:\\Users\\Your_User\\AppData\\Local\\Google\\Chrome\\User Data in urls.txt

urls = open("urls.txt").read().splitlines()

##Getting current date and time
today = datetime.now()

##File creation method##

def update (name, flist):

    #create *.txt file to store previous results
    if os.path.isfile(name + ".txt") == False:

        file = open(name + '.txt', 'a')

        for friend in flist:
            
            file.write(friend + '\n')

        file.close()
        print(name + " file created")

    #Compare previous results with current results

    else:

        fileback = open(name + ".txt").read().splitlines()

        if fileback == flist:
            print("No new friends")
        if fileback != flist:
            difference = list(set(flist) - set(fileback))
            print("New friends: " + str(len(difference)))
            print("Lost friends: " + str(len(list(set(fileback) - set(flist)))))
            print("New friends names: " + str(difference))
            print("Lost friends names: " + str(list(set(fileback) - set(flist))))

            #Save differences to *diff.txt with date and time

            fdiff = open(name + 'diff.txt', 'a')
            fdiff.write(str(today) + '\n')

            #if is a lost friend:
            for friend in list(set(fileback) - set(flist)):
                fdiff.write("Lost friend: " + friend + '\n')

            #if is a new friend:
            for friend in difference:
                fdiff.write("New friend: " + friend + '\n')
            fdiff.close()

            #update current results to *.txt and delete previous results:
            file = open(name + '.txt', 'w')
            for friend in flist:
                file.write(friend + '\n')
            file.close()

    print(str(len(flist)) + " " + name + " friends found!")

##FACEBOOK FRIENDS CHECK##

def fb_check():

    options = webdriver.ChromeOptions()
    options.add_argument("user-data-dir=" + urls[1])
    s=Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=s, options=options)

    driver.get(urls[2])
       
    ##Scrolling down the page

    SCROLL_PAUSE_TIME = 1

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

    time.sleep(3)

    #Loading friend list

    Friends = driver.find_elements(By.XPATH,"//h3[contains(@class,'_52jh _5pxc _8yo0')]")
    Friends2 = driver.find_elements(By.XPATH,"//h1[contains(@class,'_52jh _5pxc _8yo0')]")
 
    fblist = []

    for friend in itertools.chain(Friends, Friends2):
        fblist.append(friend.text)

    update("FB", fblist)

####TWITTER FOLLOWERS CHECK####

def tw_check():

    auth = tweepy.OAuthHandler(urls[5], urls[7])
    auth.set_access_token(urls[11], urls[13])
    api = tweepy.API(auth)

    # fetching all the followers with cursor
    followers = tweepy.Cursor(api.get_followers, id=urls[14]).items()
  
    twlist = []

    for follower in followers:
        twlist.append(follower.screen_name)

    update("TW", twlist)

###INSTAGRAM FOLLOWERS CHECK###

def ig_check():

    options = webdriver.ChromeOptions()
    options.add_argument("user-data-dir=" + urls[1])
    s=Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=s, options=options)

    driver.get(urls[15])

    time.sleep(1)

    driver.find_element(By.XPATH,"/html/body/div[1]/section/main/div/header/section/ul/li[2]/a").click()

    ##Scrolling down the page

    pop_up_window = WebDriverWait(
    driver, 2).until(EC.element_to_be_clickable(
        (By.XPATH, "//div[@class='isgrP']")))

    cont = 0

    while True:
        driver.execute_script('arguments[0].scrollTop = arguments[0].scrollTop + arguments[0].offsetHeight;',pop_up_window)
        cont = cont + 1

        if cont == 600:
            break

    time.sleep(3)

    Followers = driver.find_elements(By.XPATH,"//a[contains(@class,'FPmhX notranslate  _0imsa ')]")

    iglist = []

    for follower in Followers:
        iglist.append(follower.text)

    update("IG", iglist)

##CHECKING##

ask = int(input("What do you want to check? (1=All 2=FB 3=TW 4=INST): "))

if ask == 1:
    fb_check()
    ig_check()
    tw_check()    

if ask == 2:
    fb_check()

if ask == 3:
    tw_check()

if ask == 4:
    ig_check()

if ask != 1 and ask != 2 and ask != 3 and ask != 4:
    print("Wrong input")

time.sleep(300)