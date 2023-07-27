from instabot import Bot
import os

#Set current working directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

bot = Bot()

bot.login(username="johanfer12", password="J0h4nf3r91nst4gr4m", use_cookie=True, cookie_fname="cootkie.txt")

followers = bot.get_user_followers("johanfer12")
print("Total number of followers:")
print(len(followers))