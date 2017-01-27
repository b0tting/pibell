#!/usr/bin/python
import ConfigParser
import glob
import pygame, time
import json

import sys

from pushbullet import Pushbullet

try:
    import RPi.GPIO as GPIO
except:
    fakerpi = True
import logging
import os
from logging import handlers
import pytz
import random
import sqlite3
from classes.qhue import Bridge

## Manual start of the bluetooth speaker
## echo -e "connect A0:E9:DB:33:CA:82\nexit" | bluetoothctl
## sleep 3
## amixer -D pulse sset Master 60%
## sleep 3
## /etc/init.d/pibell restart


## some setup code
from threading import Thread
from datetime import date, datetime
from flask import Flask, render_template, redirect, url_for,Response
import re


configfile = "pibell_config.properties"
config = ConfigParser.ConfigParser()
try:
    config.read(configfile)
except:
    print("Could not read " + configfile)
    sys.exit();


local_tz = pytz.timezone(config.get("pibell", "pytz_timezone"))
huelamps = config.get("pibell", "huelamps").split(",")
sounddir = config.get("pibell", "sounddir")

pb = Pushbullet(config.get("pibell", "pushbullet")) if config.get("pibell", "pushbullet") else False


GPIO.setmode(GPIO.BCM)
GPIO.setup(config.getint("pibell", "pibell_pin"), GPIO.IN, pull_up_down=GPIO.PUD_UP)

pygame.mixer.init()
app = Flask(__name__)
checked_table = False

## Setup logging
logger = logging.getLogger(__name__)
handler = handlers.RotatingFileHandler(config.get("pibell", "logfile"), maxBytes=500000, backupCount=3)
handler.setLevel(logging.INFO)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


def get_connection():
    global checked_table;
    conn = sqlite3.connect(config.get("pibell", "dbfile"))
    if not checked_table:
        sql = 'create table if not exists bell (belldate integer)'
        try:
            c = conn.cursor()
            c.execute(sql)
            conn.commit()
        except Exception as e:
            logger.error('Failed with query ' + sql)
        checked_table = True
    return conn;


def insert_bell_moment(time):
    conn = get_connection()
    sql = "INSERT INTO bell (belldate) VALUES (" + str(time)+ ");"
    try:
        c = conn.cursor()
        c.execute(sql)
        conn.commit()
    except Exception as e:
        logger.error('Failed with query ' + sql)
    conn.close()

def get_bell_moments():
    conn = get_connection()
    sql = "SELECT * FROM bell ORDER BY belldate DESC limit 20"
    c = conn.cursor()
    result = c.execute(sql)
    return result

def get_sounds_from_folder(dir):
    return [f for f in os.listdir(dir) if re.search(r'.+\.(wav|ogg|mp3)$', f)]

channel = None
def play_random_sound():
    global channel
    matches = get_sounds_from_folder(sounddir)
    if(len(matches)) > 0:
        logger.debug("Got " + str(len(matches))+ " sound bits in the sound directory")
        soundfile = random.choice(matches)
        logger.warning("Now playing " + soundfile)
        cursound = pygame.mixer.Sound(sounddir + soundfile)
        channel = cursound.play(loops=config.getint("pibell", "loops")-1,fade_ms=config.getint("pibell", "fade_in") * 1000)
    else:
        logger.error("Could not find any music file in the " + sounddir + " directory.")

def go_ding():
    logger.warning('The bell is ringing!')
    insert_bell_moment(int(time.time()))
    if pb:
        push = pb.push_note("Ding! Ding!", "The doorbell is ringing.")
    play_random_sound()
    for light in huelamps: 
        b.lights[light].state(alert="lselect")
        time.sleep(0.5)
    while(channel.get_busy() and channel != None):
        time.sleep(1)
    for light in huelamps:
        b.lights[light].state(alert="none")
        time.sleep(0.5)
    logger.debug("Done playing tune")
    return True

def ButtonListener():
    while True:
        GPIO.wait_for_edge(18, GPIO.FALLING)
        input_state = GPIO.input(18)
        if not input_state:
            go_ding();

## Used in the template
def is_today(date):
    return date.date() == datetime.today().date()

@app.route('/last_rings')
def last_rings():
    result = get_bell_moments()
    formattedresults = [datetime.fromtimestamp(x[0]).replace(tzinfo=pytz.utc).astimezone(local_tz).strftime('%d %b %H:%M') for x in result]
    return Response(json.dumps(formattedresults), mimetype='application/json')

@app.route('/test')
def start_now():
    go_ding()
    return '{"test": "ok"}'

@app.route('/play/<sound>')
def play_sound(sound):
    pygame.mixer.music.load(sounddir + sound)
    pygame.mixer.music.play()
    return '{"sound": "ok"}'

@app.route('/')
def show_all():
    result = get_bell_moments()
    sounds = get_sounds_from_folder(sounddir)
    formattedresults = [datetime.fromtimestamp(x[0]).replace(tzinfo=pytz.utc).astimezone(local_tz) for x in result]
    return render_template('index.html', is_today=is_today, ringtimes=formattedresults, sounds=sounds)


ButtonThread = Thread(target = ButtonListener)
ButtonThread.daemon = True
ButtonThread.start()

b = Bridge(config.get("pibell", "hueip"), config.get("pibell", "hueuser"))


logger.info("Starting Webserver")
app.config['PROPAGATE_EXCEPTIONS'] = True
app.debug = config.getboolean("pibell", "webserverdebug")
app.run(host='0.0.0.0', port=config.getint("pibell", "webserverport"))

