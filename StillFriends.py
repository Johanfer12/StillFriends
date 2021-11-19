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

##FACEBOOK CHECK##

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

    count = 0
    fblist = []

    for friend in itertools.chain(Friends, Friends2):
        fblist.append(friend.text)

    #Create fb.txt file to store previous results
    if os.path.isfile("fb.txt") == False:

        fb = open('fb.txt', 'a')
        for friend in fblist:
            
            fb.write(friend + '\n')
            count = count + 1

        fb.close()
        print("FB file created")

    #Compare previous results with current results

    else:

        fbback = open('fb.txt').read().splitlines()

        if fbback == fblist:
            print("No new friends")
        if fbback != fblist:
            difference = list(set(fblist) - set(fbback))
            print("New friends: " + str(len(difference)))
            print("Lost friends: " + str(len(list(set(fbback) - set(fblist)))))
            print("New friends names: " + str(difference))
            print("Lost friends names: " + str(list(set(fbback) - set(fblist))))

            #Save differences to fbdiff.txt with date and time

            fbdiff = open('fbdiff.txt', 'a')
            fbdiff.write(str(today) + '\n')

            #if is a lost friend:
            for friend in list(set(fbback) - set(fblist)):
                fbdiff.write("Lost friend: " + friend + '\n')

            #if is a new friend:
            for friend in difference:
                fbdiff.write("New friend: " + friend + '\n')
            fbdiff.close()

            #update current results to fb.txt and delete previous results:
            fb = open('fb.txt', 'w')
            for friend in fblist:
                fb.write(friend + '\n')
            fb.close()

    print(str(len(fblist)) + " friends found!")

####TWITTER FOLLOWERS CHECK####

def tw_check():

    auth = tweepy.OAuthHandler(urls[5], urls[7])
    auth.set_access_token(urls[11], urls[13])
    api = tweepy.API(auth)

    # fetching the user
    user = api.get_user(id=urls[14])

    # fetching number of followers
    num_followers = user.followers_count

    # fetching all the followers with cursor
    followers = tweepy.Cursor(api.get_followers, id=urls[14]).items()

    twlist = []

    for follower in followers:
        twlist.append(follower.screen_name)

    #Create tw.txt file
    if os.path.isfile("tw.txt") == False:

        tw = open('tw.txt', 'a', encoding="utf-8")
        for follower in twlist:
            tw.write(follower + '\n')
        tw.close()
        print("TW file created")

    #Compare previous results with current results

    else:

        twback = open('tw.txt').read().splitlines()

        if twback == twlist:
            print("No new followers")
        if twback != twlist:
            difference = list(set(twlist) - set(twback))
            print("New followers: " + str(len(difference)))
            print("Lost followers: " + str(len(list(set(twback) - set(twlist)))))
            print("New followers names: " + str(difference))
            print("Lost followers names: " + str(list(set(twback) - set(twlist))))

            #Save differences to twdiff.txt with date and time

            twdiff = open('twdiff.txt', 'a')
            twdiff.write(str(today) + '\n')

            #if is a lost follower:
            for follower in list(set(twback) - set(twlist)):
                twdiff.write("Lost follower: " + follower + '\n')
                
            #if is a new follower:
            for follower in difference:
                twdiff.write("New follower: " + follower + '\n')
            twdiff.close()

        #update current results to tw.txt and delete previous results:
        tw = open('tw.txt', 'w', encoding="utf-8")
        for follower in twlist:
            tw.write(follower + '\n')
        tw.close()

##CHECKING##

ask = int(input("What do you want to check? (1=All 2=FB 3=TW 4=INST): "))

if ask == 1:
    fb_check()
    tw_check()
    #inst_check()

if ask == 2:
    fb_check()

if ask == 3:
    tw_check()

#if ask == 4:
    #inst_check()

if ask != 1 and ask != 2 and ask != 3 and ask != 4:
    print("Wrong input")

