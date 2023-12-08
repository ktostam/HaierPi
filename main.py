from flask_simplelogin import SimpleLogin,is_logged_in,login_required, get_username
from werkzeug.security import check_password_hash, generate_password_hash
from schedule import every, run_pending, get_jobs, clear, cancel_job
from flask import Flask, render_template, request, session, jsonify, redirect, Markup
from flask_babel import Babel, gettext
from pymodbus.client.sync import ModbusSerialClient
from w1thermsensor import W1ThermSensor, Sensor
import paho.mqtt.client as mqtt
from termcolor import colored
from waitress import serve
from datetime import datetime
import HPi.GPIO as GPIO
import configparser
import subprocess
import threading
import requests
import logging
import PyHaier
import socket
import serial
import signal
import json
import time
import sys

version="1.33"
welcome="\n┌────────────────────────────────────────┐\n│              "+colored("!!!Warning!!!", "red", attrs=['bold','blink'])+colored("             │\n│      This script is experimental       │\n│                                        │\n│ Products are provided strictly \"as-is\" │\n│ without any other warranty or guaranty │\n│              of any kind.              │\n└────────────────────────────────────────┘\n","yellow", attrs=['bold'])
config = configparser.ConfigParser()
config.read('config.ini')
log_level_info = {'DEBUG': logging.DEBUG, 
                    'INFO': logging.INFO,
                    'WARNING': logging.WARNING,
                    'ERROR': logging.ERROR,
                    }

def loadconfig():
    logging.info("Loading new config.ini")
    global loglevel
    loglevel = config['MAIN']['log_level']
    global timeout
    timeout = config['MAIN']['heizfreq']
    global firstrun
    firstrun = config['MAIN']['firstrun']
    global bindaddr
    bindaddr = config['MAIN']['bindaddress']
    global bindport
    bindport = config['MAIN']['bindport']
    global modbusdev
    modbusdev = config['MAIN']['modbusdev']
    global release
    release = config['MAIN']['release']
    global settemp
    settemp = config['SETTINGS']['settemp']
    global slope
    slope = config['SETTINGS']['hcslope']
    global pshift
    pshift = config['SETTINGS']['hcpshift']
    global hcamp
    hcamp = config['SETTINGS']['hcamp']
    global heatingcurve
    heatingcurve = config['SETTINGS']['heatingcurve']
    global insidetemp
    insidetemp = config['SETTINGS']['insidetemp']
    global outsidetemp
    outsidetemp = config['SETTINGS']['outsidetemp']
    global humidity
    humidity = config['SETTINGS']['humidity']
    global flimit
    flimit = config['SETTINGS']['flimit']
    global flimittemp
    flimittemp = config['SETTINGS']['flimittemp']
    global presetautochange
    presetautochange = config['SETTINGS']['presetautochange']
    global presetquiet
    presetquiet = config['SETTINGS']['presetquiet']
    global presetturbo
    presetturbo = config['SETTINGS']['presetturbo']
    global antionoff
    antionoff = config['SETTINGS']['antionoff']
    global antionoffdelta
    antionoffdelta = config['SETTINGS']['antionoffdelta']
    global chscheduler
    chscheduler = config['SETTINGS']['chscheduler']
    global dhwscheduler
    dhwscheduler = config['SETTINGS']['dhwscheduler']
    global dhwwl
    dhwwl = config['SETTINGS']['dhwwl']
    global use_mqtt
    use_mqtt = config['MQTT']['mqtt']
    global mqtt_broker_addr
    mqtt_broker_addr=config['MQTT']['address']
    global mqtt_broker_port
    mqtt_broker_port=config['MQTT']['port']
    global mqtt_topic
    mqtt_topic=config['MQTT']['main_topic']
    global mqtt_username
    mqtt_username=config['MQTT']['username']
    global mqtt_password
    mqtt_password=config['MQTT']['password']
    global modbuspin
    modbuspin=config['GPIO']['modbus']
    global freqlimitpin
    freqlimitpin=config['GPIO']['freqlimit']
    global heatdemandpin
    heatdemandpin=config['GPIO']['heatdemand']
    global cooldemandpin
    cooldemandpin=config['GPIO']['cooldemand']


loadconfig()
newframe=""
writed=""
needrestart=0
dead=0

modbus =  ModbusSerialClient(method = "rtu", port=modbusdev,stopbits=1, bytesize=8, parity='E', baudrate=9600)
ser = serial.Serial(port=modbusdev, baudrate = 9600, parity=serial.PARITY_EVEN,stopbits=serial.STOPBITS_ONE,bytesize=serial.EIGHTBITS,timeout=1)
app = Flask(__name__)
babel = Babel()
app.config['SECRET_KEY'] = '2bb80d537b1da3e38bd30361aa855686bde0eacd7162fef6a25fe97bf527a25b'
app.config['TEMPLATES_AUTO_RELOAD'] = True
set_log_level = log_level_info.get(loglevel, logging.ERROR)
logging.getLogger().setLevel(set_log_level)

#GPIO.setmode(GPIO.BCM) - no need anymore, script use own function independed from RPI.GPIO or NPi.GPIO
GPIO.setup(modbuspin, GPIO.OUT) #modbus
GPIO.setup(freqlimitpin, GPIO.OUT) #freq limit
GPIO.setup(heatdemandpin, GPIO.OUT) # heat demand
GPIO.setup(cooldemandpin, GPIO.OUT) # cool demand

statusmap=["intemp","outtemp","settemp","hcurve","dhw","tank","mode","humid","pch","pdhw","pcool", "theme", "tdts", "archerror", "compinfo", "fans", "tao", "twitwo", "pump", "threeway"]
mqtttop=["/intemp/state","/outtemp/state","/temperature/state","/heatcurve","/dhw/temperature/state","/dhw/curtemperature/state","/preset_mode/state","/humidity/state","/mode/state","/dhw/mode/state","/mode/state", "0", "/details/tdts/state","/details/archerror/state","/details/compinfo/state","/details/fans/state","/details/tao/state","/details/twitwo/state","/details/pump/state","/details/threeway/state",]
status=['N.A.','N.A.',settemp,'N.A.','N.A.','N.A.','N.A.','N.A.','N.A.','N.A.','N.A.', 'light', 'N.A.','N.A.','N.A.','N.A.','N.A.','N.A.','N.A.','N.A.']
R101=[0,0,0,0,0,0]
R141=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
R201=[0]
R241=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
twicheck=[0,0]

def get_locale():
    return request.accept_languages.best_match(['en', 'pl'])

def handler(signum, frame):
    print(colored("\rCtrl-C - Closing... please wait, this can take a while.", 'red', attrs=["bold"]))
    GPIO.cleanup(modbuspin)
    GPIO.cleanup(freqlimitpin)
    GPIO.cleanup(heatdemandpin)
    GPIO.cleanup(cooldemandpin)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    ser.close()
    if use_mqtt == '1':
        client.publish(mqtt_topic+"/connected","offline", qos=1, retain=True)
        client.disconnect()
    event.set()
    clear()
    exit(1)

def isfloat(num):
    try:
        float(num)
        return True
    except ValueError:
        return False

def check_my_users(user):
    my_users = json.load(open("users.json"))
    if not my_users.get(user["username"]):
        return False
    stored_password = my_users[user["username"]]["password"]
    if check_password_hash(stored_password, user["password"]):
        return True
    return False
simple_login = SimpleLogin(app, login_checker=check_my_users)

def gpiocontrol(control, value):
    if control == "modbus":
        if value == "1":
            GPIO.output(modbuspin, GPIO.HIGH)
        elif value == "0":
            GPIO.output(modbuspin, GPIO.LOW)
    if control == "heatdemand":
        if value == "1":
            GPIO.output(heatdemandpin, GPIO.HIGH)
        if value == "0":
            GPIO.output(heatdemandpin, GPIO.LOW)
    if control == "cooldemand":
        if value == "1":
            GPIO.output(cooldemandpin, GPIO.HIGH)
        if value == "0":
            GPIO.output(cooldemandpin, GPIO.LOW)
    if control == "freqlimit":
        if value == "1":
            GPIO.output(freqlimitpin, GPIO.HIGH)
        if value == "0":
            GPIO.output(freqlimitpin, GPIO.LOW)

def WritePump():
    global newframe
    global writed
    comm=1
    if newframe:
        logging.info(newframe)
        newframelen=len(newframe)
        while (comm):
            rs = ser.read(1).hex()
            if rs == "032c":
                for ind in range(22):
                    ser.read(2).hex()
            comm=0
            gpiocontrol("modbus", "1")

        if newframelen == 6:
            logging.info("101")
            time.sleep(1)
            modbus.connect()
            modbusresult=modbus.write_registers(101, newframe, unit=17)
            modbus.close()
            gpiocontrol("modbus","0")
            logging.info(modbusresult)
            writed="1"
            # if hasattr(modbusresult, 'fcode'):
            #     if modbusresult.fcode < 0x80:
            #         print(modbusresult.fcode)
            #         writed="1"
            #     else:
            #         writed="2"
        elif newframelen == 16:
            logging.info("141")
        elif newframelen == 1:
            logging.info("201")
            time.sleep(1)
            modbus.connect()
            modbusresult=modbus.write_registers(201, newframe, unit=17)
            modbus.close()
            gpiocontrol("modbus","0")
            logging.info(modbusresult)
            writed="1"
        newframe=""

def ReadPump():
    global R101
    global R141
    global R201
    global R241
    global newframe
    time.sleep(0.2)
    while (1):
        if (ser.isOpen() == False):
            logging.warning(colored("Closed serial connection.", 'red', attrs=["bold"]))
            break
        if event.is_set():
            break
        if newframe:
            WritePump()
        try:
            rs = ser.read(1).hex()
            if rs == "11":
                rs = ser.read(2).hex()
                # # zapisy
                # if rs == "1000":
                #     rs = ser.read(8).hex()
                #     bits = str(rs)[-2:]
                #     rsa = ser.read(int(bits, 16)).hex()
                #     head = "111000"
                #     toprinttmp = head + rs + rsa
                #     toprint = " ".join(toprinttmp[i:i + 2] for i in range(0, len(toprinttmp), 2))
                #     print(toprint)
                #     # zapisy end
                if rs == "030c":
                    R101 = []
                    for ind in range(6):
                        rs = ser.read(2).hex()
                        R101.append(int(rs, 16))
                    logging.debug(R101)
                if rs == "0320":
                    R141 = []
                    for ind in range(16):
                        rs = ser.read(2).hex()
                        R141.append(int(rs, 16))
                    logging.debug(R141)
                if rs == "0302":
                    R201 = []
                    for ind in range(1):
                        rs = ser.read(2).hex()
                        R201.append(int(rs, 16))
                    logging.debug(R201)
                if rs == "032c":
                    R241 = []
                    for ind in range(22):
                        rs = ser.read(2).hex()
                        R241.append(int(rs, 16))
                    logging.debug(R241)
        except:
            break

def on_connect(client, userdata, flags, rc):
    logging.info(colored("MQTT - Connected", "green", attrs=['bold']))
    client.subscribe(mqtt_topic+'/#')
    client.publish(mqtt_topic+"/connected","online", qos=1, retain=True)


def on_disconnect(client, userdata, rc):  # The callback for when
    logging.warning(colored("Disconnected from MQTT with code: {0}".format(str(rc)), 'red', attrs=['bold']))

def on_message(client, userdata, msg):  # The callback for when a PUBLISH 
    #message is received from the server. 
    #print("Message received-> " + msg.topic + " " + str(msg.payload))  # Print a received msg
    if msg.topic == mqtt_topic+"/power/set":
        logging.info("New power state from mqtt:")
        client.publish(mqtt_topic+"/power/state",msg.payload.decode('utf-8'), qos=1, retain=True)
    elif msg.topic == mqtt_topic+"/preset_mode/set":
        logging.info("New preset mode")
        try:
            presetchange(str(msg.payload.decode('utf-8')))
        except:
            logging.error("MQTT: cannot set new preset: "+msg+" "+state)
    elif msg.topic == mqtt_topic+"/flimit/set":
        logging.info("Frequency limit")
        try:
            flimitchange(str(msg.payload.decode('utf-8')))
        except:
            logging.error("MQTT: cannot set flimit relay")
    elif msg.topic == mqtt_topic+"/mode/set":
        logging.info("New mode")
        newmode=msg.payload.decode('utf-8')
        if newmode == "heat":
            try:
                statechange("pch", "on", "1")
                client.publish(mqtt_topic+"/mode/state",newmode, qos=1, retain=True)
            except:
                logging.error("MQTT: cannot set mode")
        elif newmode == "cool":
            try:
                statechange("pcool", "on", "1")
                client.publish(mqtt_topic+"/mode/state",newmode, qos=1, retain=True)
            except:
                logging.error("MQTT: cannot set mode")
        elif newmode == "off":
            try:
                statechange("pump", "off", "1")
                client.publish(mqtt_topic+"/mode/state",newmode, qos=1, retain=True)
            except:
                logging.error("MQTT: cannot set mode")
        else:
            logging.error("MQTT: mode unsupported")

    elif msg.topic == mqtt_topic+"/temperature/set":
        try:
            tempchange("heat",format(float(msg.payload)),"2")
            client.publish(mqtt_topic+"/temperature/state",str(float(msg.payload)), qos=1, retain=True)
        except:
            logging.error("MQTT: New temp error: payload - "+format(float(msg.payload)))
    elif msg.topic == mqtt_topic+"/dhw/mode/set":
        logging.info("New mode")
        payload=msg.payload.decode('utf-8')
        if payload == "heat":
            newmode="on"
        else:
            newmode=payload
        try:
            statechange("pdhw", str(newmode), "1")
            client.publish(mqtt_topic + "/dhw/mode/state", str(payload), qos=1, retain=True)
        except:
            logging.error("MQTT: cannot change DHW mode - payload:"+str(newmode))
    elif msg.topic == mqtt_topic+"/dhw/temperature/set":
        logging.info("New temperature")
        newtemp=int(float(msg.payload.decode('utf-8')))
        try:
            tempchange("dhw", str(newtemp), "2")
            client.publish(mqtt_topic + "/dhw/temperature/state", str(newtemp), qos=1, retain=True)
        except:
            logging.error("MQTT: cannot change DHW temperature - payload:"+str(newtemp))

def tempchange(which, value, curve):
    global R101
    global newframe
    global writed
    if curve == "1":
        if which == "heat":
            logging.info("Central heating: "+str(value))
            for a in range(3):
                if len(R101) == 6:
                    chframe = PyHaier.SetCHTemp(R101, float(value))
                    continue
            if chframe.__class__ == list:
                newframe=chframe
                return "OK"
            else:
                logging.error("ERROR: Cannot set new CH temp")
                msg=gettext("ERROR: Cannot set new CH temp")
                return msg
        elif which == "dhw":
            logging.info("Domestic Hot Water: "+value)
            dhwframe = PyHaier.SetDHWTemp(R101, int(value))
            if dhwframe.__class__ == list:
                newframe=dhwframe
                msgt=gettext("Domestic Hot Water ")
            else:
                logging.error(gettext("Error: Cannot set new DHW temp"))
                msg=gettext("ERROR: Cannot set new temp")
                state="error"
                return jsonify(msg=msg, state=state)

        for i in range(50):
            logging.info(writed)
            if writed=="1":
                msg=msgt+gettext(" temperature changed!")
                state="success"
                writed="0"
                break
            elif writed=="2":
                msg=gettext("Modbus communication error.")
                state="error"
                writed="0"
            else:
                msg=gettext("Modbus connection timeout.")
                state="error"
                writed="0"
            time.sleep(0.2)
    elif curve == "0":
        if which == "heat":
            status[statusmap.index("settemp")] = float(value)
            config['SETTINGS']['settemp'] = str(value)    # update
            with open('config.ini', 'w') as configfile:    # save
                config.write(configfile)
            if use_mqtt == "1":
                client.publish(mqtt_topic+"/temperature/state",str(value), qos=1, retain=True)
            msg = gettext("Central Heating temperature changed!")
            state = "success"
    elif curve == "2":
        if which == "heat":
            status[statusmap.index("settemp")] = float(value)
            config['SETTINGS']['settemp'] = str(value)
            with open('config.ini', 'w') as configfile:
                config.write(configfile)
            return "OK"
        elif which == "dhw":
            logging.info(gettext("Domestic Hot Water: ")+value)
            dhwframe = PyHaier.SetDHWTemp(R101, int(value))
            if dhwframe.__class__ == list:
                newframe=dhwframe
                return "OK"
            else:
                logging.error("Error: Cannot set new DHW temp")
                return "ERROR"

    return jsonify(msg=msg, state=state)

def presetchange(mode):
    with app.app_context():
        global newframe
        try:
            newframe=PyHaier.SetMode(mode)
            if use_mqtt == "1":
                client.publish(mqtt_topic+"/preset_mode/state", str(mode), qos=1, retain=False)
            #msg=gettext("New preset mode: ")+str(mode)
            msg="New preset mode: "+str(mode)
            state="success"
            return jsonify(msg=msg, state=state)
        except:
            if use_mqtt == "1":
                client.publish(mqtt_topic+"/preset_mode/state", "none", qos=1, retain=False)
            #msg=gettext("Preset mode not changed")
            msg="Preset mode not changed"
            state="error"
            return jsonify(msg=msg, state=state)

def flimitchange(mode):
    try:
        gpiocontrol("freqlimit", mode)
        msg="Frequency limit relay: "+str(mode)
        state="success"
        logging.info("Frequency limit relay changed to: "+ str(mode))
        if use_mqtt == "1":
            client.publish(mqtt_topic+"/flimit/state", str(mode), qos=1, retain=False)
        return msg,state
    except:
        msg="Frequency limit not changed"
        state="error"
        logging.error("Cannot change frequency limit relay")
        if use_mqtt == "1":
            client.publish(mqtt_topic+"/flimit/state", "error", qos=1, retain=False)
        return msg, state


def statechange(mode,value,mqtt):
    global R101
    pcool=status[statusmap.index("pcool")]
    pch=status[statusmap.index("pch")]
    pdhw=status[statusmap.index("pdhw")]
    newstate=""
    if mode == "pch":
        if value == "on":
            newstate="H"
    if mode == "pcool":
        if value == "on":
            newstate="C"
    if pdhw == "on":
        newstate=newstate+"T"
    if mode == "pdhw":
        if pch == "on":
            newstate="H"
        elif pcool == "on":
            newstate="C"
        if value == "on":
            newstate=newstate+"T"
    if not newstate:
        newstate="off"
    global newframe
    global writed
    logging.info(writed)
    logging.info(R101)
    logging.info(newstate)
    if int(R101[0])%2 == 0:
        newframe=PyHaier.SetState(R101, "on")
        time.sleep(2)
    newframe=PyHaier.SetState(R101,newstate)
    for i in range(50):
        logging.info(writed)
        if writed=="1":
            msg=gettext("State changed!")
            state="success"
            writed="0"
            break
        elif writed=="2":
            msg=gettext("Modbus communication error.")
            state="error"
            writed="0"
        else:
            msg=gettext("Modbus connection timeout.")
            state="error"
            writed="0"
        time.sleep(0.2)
    if mqtt == "1":
        return "OK"
    else:
        return jsonify(msg=msg, state=state)

def curvecalc():
    if isfloat(status[statusmap.index("intemp")]) and isfloat(status[statusmap.index("outtemp")]):
        insidetemp=float(status[statusmap.index("intemp")])
        outsidetemp=float(status[statusmap.index("outtemp")])
        settemp=float(status[statusmap.index("settemp")])
        if heatingcurve == 'auto':
            t1=(outsidetemp/(320-(outsidetemp*4)))
            t2=pow(settemp,t1)
            sslope=float(slope)
            ps=int(pshift)
            amp=int(hcamp)
            heatcurve = round(((0.55*sslope*t2)*(((-outsidetemp+20)*2)+settemp+ps)+((settemp-insidetemp)*amp))*2)/2
        elif heatingcurve == '1':
            heatcurve = round((settemp+(0.5*20)*pow(((settemp-outsidetemp)/20), 0.7))*2)/2
        elif heatingcurve == '2':
            heatcurve = round((settemp+(0.7*20)*pow(((settemp-outsidetemp)/20), 0.7))*2)/2
        elif heatingcurve == '3':
            heatcurve = round((settemp+(0.9*20)*pow(((settemp-outsidetemp)/20), 0.7))*2)/2
        
        if use_mqtt == '1':
            client.publish(mqtt_topic+"/heatcurve", str(heatcurve))
        if 25.0 < heatcurve < 55.0:
            try:
                if GPIO.input(heatdemandpin) != "1":
                    logging.info("turn on heat demand")
                    gpiocontrol("heatdemand", "1")
                if str(status[statusmap.index("hcurve")]) != str(heatcurve):
                    tempchange("heat", heatcurve, "1")
            except:
                logging.error("Set chtemp ERROR")
        else:
            if GPIO.input(heatdemandpin) != "0":
                logging.info("turn off heat demand")
                gpiocontrol("heatdemand", "0")
        status[statusmap.index("hcurve")]=heatcurve
        threeway=status[statusmap.index("threeway")]
        compinfo=status[statusmap.index("compinfo")]
        if len(compinfo) > 0:
            if dhwwl=="1" and compinfo[0] != 0 and threeway == "DHW":
                logging.info("dont change flimit in DHW mode")
            else:
                if flimit == "auto":
                    if outsidetemp >= float(flimittemp):
                        logging.info("turn on freq limit")
                        #gpiocontrol("freqlimit", "1")
                        flimitchange("1")
                    elif outsidetemp <= float(flimittemp)+0.5:
                        logging.info("turn off freq limit")
                        #gpiocontrol("freqlimit", "0")
                        flimitchange("0")
        if presetautochange == "auto":
            mode=status[statusmap.index("mode")]
            if outsidetemp >= float(presetquiet) and mode != "quiet":
                response=presetchange("quiet")
            elif outsidetemp <= float(presetturbo) and mode != "turbo":
                response=presetchange("turbo")
            elif outsidetemp > float(presetturbo) and outsidetemp < float(presetquiet) and mode != "eco":
                response=presetchange("eco")
    else:
        status[statusmap.index("hcurve")]=gettext("Error")


def updatecheck():
    gitver=subprocess.run(['git', 'ls-remote', 'origin', '-h', 'refs/heads/'+release ], stdout=subprocess.PIPE).stdout.decode('utf-8')[0:40]
    localver=subprocess.run(['cat', '.git/refs/heads/'+release], stdout=subprocess.PIPE).stdout.decode('utf-8')[0:40]
    if localver != gitver:
	    msg=gettext("Availible")
    else:
	    msg=gettext("Not Availible")
    return jsonify(update=msg)

def logdaemon(action):
    subprocess.check_output("systemctl "+str(action)+" haierlog.service", shell=True).decode().rstrip('\n')
    status = subprocess.check_output("systemctl show -p ActiveState --value haierlog", shell=True).decode().rstrip('\n')
    logging.info(status)
    return status

def installupdate():
    subprocess.Popen("systemctl restart haierupdate.service", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return jsonify(updated="OK")

def restart():
    subprocess.Popen("systemctl restart haier.service", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return jsonify(restarted="OK")

def getparams():
    isr241=1
    isr141=1
    while (isr241):
        if (len(R241) == 22):
            #logging.info(R241)
            tdts=PyHaier.GetTdTs(R241)
            archerror=PyHaier.GetArchError(R241)
            compinfo=PyHaier.GetCompInfo(R241)
            fans=PyHaier.GetFanRpm(R241)
            tao=PyHaier.GetTao(R241)
            isr241=0
    while (isr141):
        if (len(R141) == 16):
            #logging.info(R141)
            twitwo = PyHaier.GetTwiTwo(R141)
            pump=PyHaier.GetPump(R141)
            threeway=PyHaier.Get3way(R141)
            isr141=0
    return twitwo, tdts, archerror, compinfo,fans,tao,pump,threeway

def getdata():
    intemp=status[statusmap.index("intemp")]
    outtemp=status[statusmap.index("outtemp")]
    stemp=status[statusmap.index("settemp")]
    hcurve=status[statusmap.index("hcurve")]
    dhw=status[statusmap.index("dhw")]
    tank=status[statusmap.index("tank")]
    mode=status[statusmap.index("mode")]
    humid=status[statusmap.index("humid")]
    pch=status[statusmap.index("pch")]
    pdhw=status[statusmap.index("pdhw")]
    pcool=status[statusmap.index("pcool")]
    presetch = presetautochange 
    heatdemand=GPIO.input(heatdemandpin)
    cooldemand=GPIO.input(cooldemandpin)
    flimiton=GPIO.input(freqlimitpin)
    ltemp = flimittemp
    return jsonify(intemp=intemp, outtemp=outtemp, setpoint=stemp, hcurve=hcurve,dhw=dhw,tank=tank, mode=mode,humid=humid,pch=pch,pdhw=pdhw,pcool=pcool,flimit=flimit,heatdemand=heatdemand,cooldemand=cooldemand,flimiton=flimiton, ltemp=ltemp, presetch=presetch, presetquiet=presetquiet, presetturbo=presetturbo)

def GetInsideTemp(param):
    if param == "builtin":
        result=subprocess.check_output('./bin/dht22s')
        intemp=result.decode('utf-8').split('#')[1]
        return intemp
    elif param == "ha":
        # connect to Home Assistant API and get status of inside temperature entity
        url=config['HOMEASSISTANT']['HAADDR']+":"+config['HOMEASSISTANT']['HAPORT']+"/api/states/"+config['HOMEASSISTANT']['insidesensor']
        headers = requests.structures.CaseInsensitiveDict()
        headers["Accept"] = "application/json"
        headers["Authorization"] = "Bearer "+config['HOMEASSISTANT']['KEY']
        try:
            resp=requests.get(url, headers=headers)
            json_str = json.dumps(resp.json())
        except requests.exceptions.RequestException as e:
            logging.error(e)
        try:
            if 'state' in json_str:
                response = json.loads(json_str)['state']
            else:
                response = gettext("Entity state not found")
        except:
            response = gettext("Error")
        return response
    else:
        return -1

def GetOutsideTemp(param):
    if param == "builtin":
        try:
            sensor = W1ThermSensor()
            temperature = sensor.get_temperature()
            return temperature
        except:
            sys.stderr.write("Error: cannot read outside temperature")
            return "0"
    elif param == "ha":
        # connect to Home Assistant API and get status of outside temperature entity
        url=config['HOMEASSISTANT']['HAADDR']+":"+config['HOMEASSISTANT']['HAPORT']+"/api/states/"+config['HOMEASSISTANT']['outsidesensor']
        headers = requests.structures.CaseInsensitiveDict()
        headers["Accept"] = "application/json"
        headers["Authorization"] = "Bearer "+config['HOMEASSISTANT']['KEY']
        try:
            resp = requests.get(url, headers=headers)
            json_str = json.dumps(resp.json())
        except requests.exceptions.RequestException as e:
            logging.error(e)
        try:
            if 'state' in json_str:
                response = json.loads(json_str)['state']
            else:
                response = gettext("Entity state not found")
        except:
            response = gettext("Error")
        return response
    else:
        return -1

def GetHumidity(param):
    if param == "builtin":
        result=subprocess.check_output('./bin/dht22s')
        intemp=result.decode('utf-8').split('#')[0]
        return intemp
    elif param == "ha":
        # connect to Home Assistant API and get status of inside humidity entity
        url=config['HOMEASSISTANT']['HAADDR']+":"+config['HOMEASSISTANT']['HAPORT']+"/api/states/"+config['HOMEASSISTANT']['humiditysensor']
        headers = requests.structures.CaseInsensitiveDict()
        headers["Accept"] = "application/json"
        headers["Authorization"] = "Bearer "+config['HOMEASSISTANT']['KEY']
        try:
            resp = requests.get(url, headers=headers)
            json_str = json.dumps(resp.json())
        except requests.exceptions.RequestException as e:
            logging.error(e)
        try:
            if 'state' in json_str:
                response = json.loads(json_str)['state']
            else:
                response = gettext("Entity state not found")
        except:
                response = gettext("Error")
        return response
    else:
        return -1

def settheme(theme):
    status[statusmap.index("theme")]=theme
    return theme

# Function campare new value with old, as "old" you need to provide name of status. for example 'pch'
def ischanged(old, new):
    if status[statusmap.index(old)] != new:
        logging.info("ischanged: status "+str(old)+" has changed. Set new value - "+str(new))
        status[statusmap.index(old)] = new
        if use_mqtt == "1":
            if old == "pdhw" or old == "pch":
                if new == "on":
                    client.publish(mqtt_topic + mqtttop[statusmap.index(old)], "heat")
            elif old =="pcool":
                if new == "on":
                    cient.publish(mqtt_topic + mqtttop[statusmap.index(old)], "cool")
            else:
                client.publish(mqtt_topic + mqtttop[statusmap.index(old)], str(new))

def deltacheck(temps):
    if antionoff == '1':
        global twicheck
        if twicheck[0] == 0:
            twicheck=[temps, time.time(),temps,time.time()]
            logging.info(twicheck)
        else:
            newtime=time.time()
            if newtime - twicheck[1] >= 300:
                delta=temps[0]-twicheck[0][0]
                logging.info("Delta: "+str(delta))
                if delta>=float(antionoffdelta):
                    logging.info("AntiON-OFF: "+str(delta)+", more then: "+antionoffdelta+". Changing mode to lower if possible")
                    mode=status[statusmap.index("mode")]
                    flimiton=GPIO.input(freqlimitpin)
                    logging.info("AntiON-OFF: current mode - "+str(mode))
                    if mode == "turbo":
                        logging.info("AntiON-OFF: changing mode to: ECO")
                        response=presetchange("eco")
                    elif mode == "eco":
                        logging.info("AntiON-OFF: changing mode to: quiet")
                        response=presetchange("quiet")
                    elif mode == "quiet":
                        logging.info("AntiON-OFF: mode in lowest setting, turn on frequency limit relay")
                        gpiocontrol("freqlimit", "1")
                    elif mode == "quiet" and flimiton == "1":
                        logging.info("AntiON-OFF: mode in lowest setting, frequency limit is already ON. I can't do anything else :(")
                else:
                    logging.info("AntiON-OFF: "+str(delta)+", no need to change mode")
                twicheck[0]=temps
                twicheck[1]=newtime

def schedule_write(which, data):
    if which == "ch":
        try:
            f = open("schedule_ch.json", "w")
            f.write(data)
            f.close()
            msg = gettext("Central Heating chedule saved")
            state = "success"
            return msg, state
        except:
            msg = gettext("ERROR: Central Heating not saved")
            state = "error"
            return msg, state
    if which == "dhw":
        try:
            f = open("schedule_dhw.json", "w")
            f.write(data)
            f.close()
            msg = gettext("Domestic Hot Water chedule saved")
            state = "success"
            return msg, state
        except:
            msg = gettext("ERROR: Domestic Hot Water not saved")
            state = "error"
            return msg, state

def scheduler():
    if chscheduler == "1":
        f=open('schedule_ch.json', 'r')
        data = json.load(f)
        now=datetime.now().strftime("%H:%M")
        weekday=datetime.weekday(datetime.now())
        pch=status[statusmap.index("pch")]
        schedulestart=[]
        for x in range(len(data[weekday]['periods'])):
            y=x-1
            start=data[weekday]['periods'][y]['start']
            end=data[weekday]['periods'][y]['end']
            if end >= now >= start:
                if pch == 'off':
                    schedulestart.append('on')
                else:
                    schedulestart.append('aon')
            else:
                if pch == 'on':
                    schedulestart.append('off')
                else:
                    schedulestart.append('aoff')
        if 'on' in schedulestart:
            logging.info("Scheduler: START CH")
            statechange("pch", "on", "1")
        elif 'aon' in schedulestart:
            logging.info("Scheduler: CH ALREADY ON")
        elif 'aoff' in schedulestart:
            logging.info("Scheduler: CH ALREADY OFF")
        else:
            if pch != 'off':
                logging.info("Scheduler: STOP CH")
                statechange("pch", "off", "1")
    if dhwscheduler == "1":
        f=open('schedule_dhw.json', 'r')
        data = json.load(f)
        now=datetime.now().strftime("%H:%M")
        weekday=datetime.weekday(datetime.now())
        pdhw=status[statusmap.index("pdhw")]
        schedulestart=[]
        for x in range(len(data[weekday]['periods'])):
            y=x-1
            start=data[weekday]['periods'][y]['start']
            end=data[weekday]['periods'][y]['end']
            if end >= now >= start:
                if pdhw == 'off':
                    schedulestart.append('on')
                else:
                    schedulestart.append('aon')
            else:
                if pdhw == 'on':
                    schedulestart.append('off')
                else:
                    schedulestart.append('aoff')
        if 'on' in schedulestart:
            logging.info("Scheduler: START DHW")
            statechange("pdhw", "on", "1")
        elif 'aon' in schedulestart:
            logging.info("Scheduler: DHW ALREADY ON")
        elif 'aoff' in schedulestart:
            logging.info("Scheduler: DHW ALREADY OFF")
        else:
            logging.info("Scheduler: STOP DHW")
            statechange("pdhw", "off", "1")


#Reading parameters
def GetParameters():
    global R101
    global R141
    global R201
    global R241
    if len(R141) == 16:
        tank = PyHaier.GetDHWCurTemp(R141)
        twitwo = PyHaier.GetTwiTwo(R141)
        pump=PyHaier.GetPump(R141)
        threeway=PyHaier.Get3way(R141)
        #status[statusmap.index("tank")] = tank
        ischanged("tank", tank)
        ischanged("twitwo", twitwo)
        ischanged("pump", pump)
        ischanged("threeway", threeway)
        deltacheck(twitwo)
    if len(R201) == 1:
        mode=PyHaier.GetMode(R201)
        #status[statusmap.index("mode")] = mode
        ischanged("mode", mode)
    if len(R241) == 22:
        tdts=PyHaier.GetTdTs(R241)
        archerror=PyHaier.GetArchError(R241)
        compinfo=PyHaier.GetCompInfo(R241)
        fans=PyHaier.GetFanRpm(R241)
        tao=PyHaier.GetTao(R241)
        ischanged("tdts", tdts)
        ischanged("archerror", archerror)
        ischanged("compinfo", compinfo)
        ischanged("fans", fans)
        ischanged("tao", tao)
    if len(R101) == 6:
        dhw=PyHaier.GetDHWTemp(R101)
        #status[statusmap.index("dhw")] = dhw
        ischanged("dhw", dhw)
        powerstate=PyHaier.GetState(R101)
        if 'Heat' in powerstate:
            #status[statusmap.index("pch")] = "on"
            ischanged("pch", "on")
            #if use_mqtt == "1":
            #    client.publish(mqtt_topic+"/mode/state", "heat")
        else:
            ischanged("pch", "off")
            #status[statusmap.index("pch")] = "off"
        if 'Cool' in powerstate:
            ischanged("pcool", "on")
            #status[statusmap.index("pcool")] = "on"
            #if use_mqtt == "1":
            #    client.publish(mqtt_topic+"/mode/state", "cool")
        else:
            #status[statusmap.index("pcool")] = "off"
            ischanged("pcool", "off")
        if not any(substring in powerstate for substring in ["Cool", "Heat"]):
            if use_mqtt == "1":
                client.publish(mqtt_topic+"/mode/state", "off")

        if 'Tank' in powerstate:
            #status[statusmap.index("pdhw")] = "on"
            ischanged("pdhw", "on")
            #if use_mqtt == "1":
            #    client.publish(mqtt_topic+"/dhw/mode/state", "heat")
        else:
            #status[statusmap.index("pdhw")] = "off"
            ischanged("pdhw", "off")
            #if use_mqtt == "1":
            #    client.publish(mqtt_topic + "/dhw/mode/state", "off")
    ischanged("intemp", GetInsideTemp(insidetemp))
    ischanged("outtemp", GetOutsideTemp(outsidetemp))
    ischanged("humid", GetHumidity(humidity))
    scheduler()
    threeway=status[statusmap.index("threeway")]
    compinfo=status[statusmap.index("compinfo")]
    flimiton=GPIO.input(freqlimitpin)
    if len(compinfo) > 0:
        if dhwwl == "1" and compinfo[0] > 0 and threeway == "DHW" and flimiton == "1":
            logging.info("DHWWL Function ON")
            gpiocontrol("freqlimit", "0")

    #status[statusmap.index("intemp")] = GetInsideTemp(insidetemp)
    #status[statusmap.index("outtemp")] = GetOutsideTemp(outsidetemp)
    #status[statusmap.index("humid")] = GetHumidity(humidity)
    #if use_mqtt == '1':
        #client.publish(mqtt_topic,str(status))
        #client.publish(mqtt_topic+"/dhw/curtemperature/state", str(status[statusmap.index("tank")]))
        #client.publish(mqtt_topic+"/dhw/temperature/state", str(status[statusmap.index("dhw")]))
        #client.publish(mqtt_topic+"/preset_mode/state", str(status[statusmap.index("mode")]))
        #client.publish(mqtt_topic+"/temperature/state", str(status[statusmap.index("settemp")]))

def create_user(**data):
    """Creates user with encrypted password"""
    if "username" not in data or "password" not in data:
        raise ValueError(gettext("username and password are required."))

    # Hash the user password
    data["password"] = generate_password_hash(
        data.pop("password"), method="pbkdf2:sha256"
    )

    # Here you insert the `data` in your users database
    # for this simple example we are recording in a json file
    db_users = json.load(open("users.json"))
    # add the new created user to json
    db_users[data["username"]] = data
    # commit changes to database
    json.dump(db_users, open("users.json", "w"))
    #return data
    msg=gettext("Password changed")
    return msg

def background_function():
    print("Background function running!")

# Flask route
@app.route('/')
@login_required
def home():
    if firstrun == "1":
        return redirect("/settings", code=302)
    else:
        theme=status[statusmap.index("theme")]
        return render_template('index.html', theme=theme, version=version, needrestart=needrestart, flimit=flimit)

@app.route('/theme', methods=['POST'])
def theme_route():
    theme = request.form['theme']
    settheme(theme)
    return theme

@app.route('/settings', methods=['GET','POST'])
@login_required
def settings():
    if request.method == 'POST':
        #saved="1"
        #global needrestart
        #needrestart=1
        for key, value in request.form.items():
            KEY1=f'{key.split("$")[0]}'
            KEY2=f'{key.split("$")[1]}'
            VAL=f'{value}'
            config[KEY1][KEY2] = str(VAL)    # update
            with open('config.ini', 'w') as configfile:    # save
                config.write(configfile)
        loadconfig()
    logserver=socket.gethostbyname(socket.gethostname())
    theme = status[statusmap.index("theme")]
    timeout = config['MAIN']['heizfreq']
    intemp=status[statusmap.index("intemp")]
    outtemp=status[statusmap.index("outtemp")]
    heatingcurve = config['SETTINGS']['heatingcurve']
    slope = config['SETTINGS']['hcslope']
    pshift = config['SETTINGS']['hcpshift']
    hcamp = config['SETTINGS']['hcamp']
    bindaddr = config['MAIN']['bindaddress']
    bindport = config['MAIN']['bindport']
    modbusdev = config['MAIN']['modbusdev']
    release = config['MAIN']['release']
    settemp = config['SETTINGS']['settemp']
    insidetemp = config['SETTINGS']['insidetemp']
    outsidetemp = config['SETTINGS']['outsidetemp']
    humidity = config['SETTINGS']['humidity']
    flimit = config['SETTINGS']['flimit']
    flimittemp = config['SETTINGS']['flimittemp']
    presetautochange = config['SETTINGS']['presetautochange']
    presetquiet = config['SETTINGS']['presetquiet']
    presetturbo = config['SETTINGS']['presetturbo']
    antionoff = config['SETTINGS']['antionoff']
    antionoffdelta = config['SETTINGS']['antionoffdelta']
    chscheduler = config['SETTINGS']['chscheduler']
    dhwscheduler = config['SETTINGS']['dhwscheduler']
    dhwwl = config['SETTINGS']['dhwwl']
    modbuspin=config['GPIO']['modbus']
    freqlimitpin=config['GPIO']['freqlimit']
    heatdemandpin=config['GPIO']['heatdemand']
    cooldemandpin=config['GPIO']['cooldemand']
    use_mqtt = config['MQTT']['mqtt']
    mqtt_broker_addr=config['MQTT']['address']
    mqtt_broker_port=config['MQTT']['port']
    mqtt_topic=config['MQTT']['main_topic']
    mqtt_username=config['MQTT']['username']
    mqtt_password=config['MQTT']['password']
    haaddr=config['HOMEASSISTANT']['HAADDR']
    haport=config['HOMEASSISTANT']['HAPORT']
    hakey=config['HOMEASSISTANT']['KEY']
    insidesensor=config['HOMEASSISTANT']['insidesensor']
    outsidesensor=config['HOMEASSISTANT']['outsidesensor']
    humiditysensor=config['HOMEASSISTANT']['humiditysensor']
    return render_template('settings.html', **locals(), version=version, needrestart=needrestart)

@app.route('/parameters', methods=['GET','POST'])
@login_required
def parameters():
    theme=status[statusmap.index("theme")]
    return  render_template('parameters.html', version=version, theme=theme)

@app.route('/scheduler', methods=['GET','POST'])
@login_required
def scheduler_route():
    if request.method == 'POST':
        if "schedulech" in request.form:
            msg, state = schedule_write('ch', request.form['schedulech'])
            return jsonify(msg=msg, state=state)
        if "scheduledhw" in request.form:
            msg, state = schedule_write('dhw', request.form['scheduledhw'])
            return jsonify(msg=msg, state=state)

    schedule1 = open("schedule_ch.json", "r")
    schedule2 = open("schedule_dhw.json", "r")
    theme=status[statusmap.index("theme")]
    return  render_template('scheduler.html', ch=Markup(schedule1.read()), dhw=Markup(schedule2.read()), version=version, theme=theme)

@app.route('/statechange', methods=['POST'])
@login_required
def change_state_route():
    mode = request.form['mode']
    value = request.form['value']
    information = statechange(mode, value, "0")
    return information
@app.route('/modechange', methods=['POST'])
@login_required
def change_mode_route():
    newvalue = request.form['newmode']
    response = presetchange(newvalue)
    return response

@app.route('/flrchange', methods=['POST'])
@login_required
def change_flimitrelay_route():
    newvalue = request.form['newmode']
    msg,state = flimitchange(newvalue)
    return jsonify(msg=msg, state=state)

@app.route('/tempchange', methods=['POST'])
@login_required
def change_temp_route():
    which = request.form['which']
    value = request.form['value']
    directly = request.form['directly']
    response = tempchange(which, value, directly)
    return response
@app.route('/updatecheck')
def updatecheck_route():
    response = updatecheck()
    return response

@app.route('/logdaemon', methods=['POST'])
@login_required
def logdaemon_reoute():
    action = request.form['action']
    output = logdaemon(action)
    return jsonify(output=output)

@app.route('/installupdate', methods=['GET'])
@login_required
def installupdate_route():
    output = installupdate()
    return output

@app.route('/restart', methods=['GET'])
@login_required
def restart_route():
    output = restart()
    return output

@app.route('/changepass', methods=['POST'])
@login_required
def change_pass_route():
    user = request.form['user']
    password = request.form['password']
    response = create_user(username=user, password=password)
    return jsonify(response)

@app.route('/getdata', methods=['GET'])
@login_required
def getdata_route():
    output = getdata()
    return output

@app.route('/getparams', methods=['GET'])
@login_required
def getparams_route():
    twitwo, tdts, archerror, compinfo, fans, tao, pump, threeway = getparams()
    return jsonify(twitwo=twitwo, tdts=tdts, archerror=archerror,compinfo=compinfo, fans=fans, tao=tao, pump=pump, threeway=threeway)

# Function to run the background function using a scheduler
def run_background_function():
    job = every(10).seconds.do(GetParameters)
    job2 = every(int(timeout)).minutes.do(curvecalc)
    while True:
        run_pending()
        time.sleep(1)
        if event.is_set():
            break

def connect_mqtt():
    client.on_connect = on_connect  # Define callback function for successful connection
    client.on_message = on_message  # Define callback function for receipt of a message
    client.on_disconnect = on_disconnect
    client.will_set(mqtt_topic+"/connected","offline",qos=1,retain=True)
    client.username_pw_set(mqtt_username, mqtt_password)
    try:
        client.connect(mqtt_broker_addr, int(mqtt_broker_port))
    except:
        logging.error(colored("MQTT connection error.","red", attrs=['bold']))
    client.loop_forever()  # Start networking daemon

def threads_check():
    global dead
    while True:
        if not bg_thread.is_alive():
            if dead == 0:
                logging.error("Background thread DEAD")
                dead = 1
        elif not serial_thread.is_alive():
            logging.error("Serial Thread DEAD")
        elif use_mqtt == "1":
            if not mqtt_bg.is_alive():
                logging.error("MQTT thread DEAD")
        time.sleep(1)
        if event.is_set():
            break

# Start the Flask app in a separate thread
babel.init_app(app, locale_selector=get_locale)

if __name__ == '__main__':
    loadconfig()
    logging.warning(colored(welcome,"yellow", attrs=['bold']))
    logging.warning(colored("Service running: http://127.0.0.1:4000 ", "green"))
    signal.signal(signal.SIGINT, handler)
    bg_thread = threading.Thread(target=run_background_function)
    bg_thread.start()
    if use_mqtt == '1':
        client = mqtt.Client()  # Create instance of client
        mqtt_bg = threading.Thread(target=connect_mqtt)
        mqtt_bg.start()
    serial_thread = threading.Thread(target=ReadPump)
    serial_thread.start()
    threadcheck = threading.Thread(target=threads_check)
    threadcheck.start()
    event = threading.Event()
    serve(app, host=bindaddr, port=bindport)
        #app.run(debug=False, host=bindaddr, port=bindport)#, ssl_context='adhoc')
