#!/usr/bin/python

import glob
import pygame, time
import RPi.GPIO as GPIO
import logging
import os
from logging import handlers
import pytz
import random
import sqlite3
## echo -e "connect A0:E9:DB:33:CA:82\nexit" | bluetoothctl

## some setup code
from threading import Thread
from datetime import date, datetime
from flask import Flask
import re

GPIO.setmode(GPIO.BCM)

## Using pin 18 here
GPIO.setup(18, GPIO.IN, pull_up_down=GPIO.PUD_UP)
logfile = '/var/log/pibell'
dbfile = 'pibell.sql3'
local_tz = pytz.timezone('Europe/Amsterdam')

## We only like OGG, WAV or MP3 files.
sounddir = "./sounds/"
webserverdebug = False

## Mapping IP addresses to phone numbers
phone_map = {'192.168.51.21':'0624643120'}


pygame.mixer.init()
app = Flask(__name__)
checked_table = False

## Setup logging
logger = logging.getLogger(__name__)
handler = handlers.RotatingFileHandler(logfile, maxBytes=500000, backupCount=3)
handler.setLevel(logging.INFO)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


def get_connection():
    global checked_table;
    conn = sqlite3.connect(dbfile)
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
    conn = get_connection();
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
    sql = "SELECT * FROM bell"
    c = conn.cursor()
    result = c.execute(sql)
    return result

def play_random_sound():
    matches  = [sounddir + f for f in os.listdir(sounddir) if re.search(r'.+\.(wav|ogg|mp3)$', f)]
    if(len(matches)) > 0:
        logger.debug("Got " + str(len(matches))+ " sound bits in the sound directory")
        file = random.choice(matches)
        logger.warning("Now playing " + file)
        pygame.mixer.music.load(file)
        pygame.mixer.music.play()
    else:
        logger.error("Could not find any music file in the " + sounddir + " directory.")

def ButtonListener():
    while True:
        GPIO.wait_for_edge(18, GPIO.FALLING)
        input_state = GPIO.input(18)
        if input_state == False:
            logger.warning('The bell is ringing!')
            insert_bell_moment(int(time.time()))
            play_random_sound()
            while(pygame.mixer.music.get_busy()):
                time.sleep(1)
            logger.debug("Done playing tune")

@app.route('/test')
def start_now():
    play_random_sound()
    return '{"test": "ok"}'

@app.route('/')
def show_all():
    result = get_bell_moments()
    showreturn = "{"
    for row in result:
        dt = datetime.fromtimestamp(row[0])
        local_dt = dt.replace(tzinfo=pytz.utc).astimezone(local_tz)
        showreturn = showreturn + str(local_dt) + ",\n"
    showreturn = showreturn + "}"
    return showreturn

ButtonThread = Thread(target = ButtonListener)
ButtonThread.daemon = True
ButtonThread.start()

logger.info("Starting Webserver")
app.config['PROPAGATE_EXCEPTIONS'] = True
app.debug = webserverdebug
app.run(host='0.0.0.0', port=81)

