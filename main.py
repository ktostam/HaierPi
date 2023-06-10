from flask_simplelogin import SimpleLogin,is_logged_in,login_required, get_username
from werkzeug.security import check_password_hash, generate_password_hash
from schedule import every, run_pending, get_jobs, clear, cancel_job
from flask import Flask, render_template, request, jsonify, redirect
from pymodbus.client.sync import ModbusSerialClient
from w1thermsensor import W1ThermSensor, Sensor
import paho.mqtt.client as mqtt
from termcolor import colored
from waitress import serve
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
import math
import json
import time

version="1.41"
welcome="\n┌────────────────────────────────────────┐\n│              "+colored("!!!Warning!!!", "red", attrs=['bold','blink'])+colored("             │\n│      This script is experimental       │\n│                                        │\n│ Products are provided strictly \"as-is\" │\n│ without any other warranty or guaranty │\n│              of any kind.              │\n└────────────────────────────────────────┘\n","yellow", attrs=['bold'])
config = configparser.ConfigParser()
config.read('config.ini')
timeout = config['DEFAULT']['heizfreq']
firstrun = config['DEFAULT']['firstrun']
bindaddr = config['DEFAULT']['bindaddress']
bindport = config['DEFAULT']['bindport']
modbusdev = config['DEFAULT']['modbusdev']
release = config['DEFAULT']['release']
settemp = config['SETTINGS']['settemp']
slope = config['SETTINGS']['hcslope']
pshift = config['SETTINGS']['hcpshift']
heatingcurve = config['SETTINGS']['heatingcurve']
hcamp = config['SETTINGS']['hcamp']
insidetemp = config['SETTINGS']['insidetemp']
outsidetemp = config['SETTINGS']['outsidetemp']
humidity = config['SETTINGS']['humidity']
use_mqtt = config['MQTT']['mqtt']
mqtt_broker_addr=config['MQTT']['address']
mqtt_broker_port=config['MQTT']['port']
mqtt_topic=config['MQTT']['main_topic']
mqtt_username=config['MQTT']['username']
mqtt_password=config['MQTT']['password']
newframe=""
writed=""
modbuspin=config['GPIO']['modbus']
freqlimitpin=config['GPIO']['freqlimit']
heatdemandpin=config['GPIO']['heatdemand']
cooldemandpin=config['GPIO']['cooldemand']
needrestart=0

modbus =  ModbusSerialClient(method = "rtu", port=modbusdev,stopbits=1, bytesize=8, parity='E', baudrate=9600)
ser = serial.Serial(port=modbusdev, baudrate = 9600, parity=serial.PARITY_EVEN,stopbits=serial.STOPBITS_ONE,bytesize=serial.EIGHTBITS,timeout=1)
app = Flask(__name__)
app.config['SECRET_KEY'] = '2bb80d537b1da3e38bd30361aa855686bde0eacd7162fef6a25fe97bf527a25b'
logging.getLogger().setLevel(logging.INFO)

#GPIO.setmode(GPIO.BCM) - no need anymore, script use own function independed from RPI.GPIO or NPi.GPIO
GPIO.setup(modbuspin, GPIO.OUT) #modbus
GPIO.setup(freqlimitpin, GPIO.OUT) #freq limit
GPIO.setup(heatdemandpin, GPIO.OUT) # heat demand
GPIO.setup(cooldemandpin, GPIO.OUT) # cool demand

statusmap=["intemp","outtemp","settemp","hcurve","dhw","tank","mode","humid","pch","pdhw","pcool", "theme", "dewpoint"]
mqtttop=["/intemp/state","/outtemp/state","/temperature/state","/heatcurve","/dhw/temperature/state","/dhw/curtemperature/state","/preset_mode/state","/humidity/state","/mode/state","/dhw/mode/state","/mode/state", "0"]
status=['N.A.','N.A.',settemp,'N.A.','N.A.','N.A.','N.A.','N.A.','N.A.','N.A.','N.A.', 'light','N.A.']
R101=[0,0,0,0,0,0]
R141=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
R201=[0]
R241=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]

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
    if newframe:
        logging.info(newframe)
        newframelen=len(newframe)
        if newframelen == 6:
            logging.info("101")
            gpiocontrol("modbus","1")
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
            gpiocontrol("modbus", "1")
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
            logging.warning(colored("Closed seial connection.", 'red', attrs=["bold"]))
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
                    # print(R101)
                if rs == "0320":
                    R141 = []
                    for ind in range(16):
                        rs = ser.read(2).hex()
                        R141.append(int(rs, 16))
                if rs == "0302":
                    R201 = []
                    for ind in range(1):
                        rs = ser.read(2).hex()
                        R201.append(int(rs, 16))
                if rs == "032c":
                    R241 = []
                    for ind in range(22):
                        rs = ser.read(2).hex()
                        R241.append(int(rs, 16))
        except:
            break

def on_connect(client, userdata, flags, rc):
    logging.info(colored("MQTT - Conected", "green", attrs=['bold']))
    client.subscribe(mqtt_topic+'/#')
    client.publish(mqtt_topic+"/connected","online", qos=1, retain=True)


def on_disconnect(client, userdata, rc):  # The callback for when
    logging.warning(colored("Disconected from MQTT with code: {0}".format(str(rc)), 'red', attrs=['bold']))

def on_message(client, userdata, msg):  # The callback for when a PUBLISH 
    #message is received from the server. 
    #print("Message received-> " + msg.topic + " " + str(msg.payload))  # Print a received msg
    if msg.topic == mqtt_topic+"/power/set":
        logging.info("New power state from mqtt:")
        client.publish(mqtt_topic+"/power/state",msg.payload.decode('utf-8'), qos=1, retain=True)
    elif msg.topic == mqtt_topic+"/preset_mode/set":
        logging.info("New preset mode")
        try:
            msg, state = presetchange(str(msg.payload.decode('utf-8')))
        except:
            logging.error("MQTT: cannot set new preset: "+msg+" "+state)
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
            logging.warning("MQTT: New temp error: payload - "+format(float(msg.payload)))
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
            logging.warning("MQTT: cannot change DHW mode - payload:"+str(newmode))
    elif msg.topic == mqtt_topic+"/dhw/temperature/set":
        logging.info("New temperatura")
        newtemp=int(float(msg.payload.decode('utf-8')))
        try:
            tempchange("dhw", str(newtemp), "2")
            client.publish(mqtt_topic + "/dhw/temperature/state", str(newtemp), qos=1, retain=True)
        except:
            logging.warning("MQTT: cannot change DHW temperature - payload:"+str(newtemp))

def tempchange(which, value, curve):
    global R101
    global newframe
    global writed
    if curve == "1":
        if which == "cool":
            logging.info(value)
        if which == "heat":
            logging.info("Central heating: "+str(value))
            logging.debug(R101)
            for a in range(3):
                if len(R101) == 6:
                    chframe = PyHaier.SetCHTemp(R101, float(value))
                    continue
            if chframe.__class__ == list:
                newframe=chframe
                return "OK"
            else:
                logging.error("ERROR: Cannot set new CH temp")
                msg="ERROR: Cannot set new CH temp"
                return msg
        elif which == "dhw":
            logging.info(R101)
            logging.info("Domestic Hot Water: "+value)
            dhwframe = PyHaier.SetDHWTemp(R101, int(value))
            if dhwframe.__class__ == list:
                newframe=dhwframe
                msgt="Domestic Hot Water "
            else:
                logging.error("Error: Cannot set new DHW temp")
                msg="ERROR: Cannot set new temp"
                state="error"
                return jsonify(msg=msg, state=state)

        for i in range(50):
            logging.info(writed)
            if writed=="1":
                msg=msgt+" temperature changed!"
                state="success"
                writed="0"
                break
            elif writed=="2":
                msg="Modbus communication error."
                state="error"
                writed="0"
            else:
                msg="Modbus connection timeout."
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
            msg = "Central Heating temperature changed!"
            state = "success"
    elif curve == "2":
        if which == "heat":
            status[statusmap.index("settemp")] = float(value)
            config['SETTINGS']['settemp'] = str(value)
            with open('config.ini', 'w') as configfile:
                config.write(configfile)
            return "OK"
        elif which == "dhw":
            logging.info(R101)
            logging.info("Domestic Hot Water: "+value)
            dhwframe = PyHaier.SetDHWTemp(R101, int(value))
            if dhwframe.__class__ == list:
                newframe=dhwframe
                return "OK"
            else:
                logging.error("Error: Cannot set new DHW temp")
                return "ERROR"

    return jsonify(msg=msg, state=state)

def presetchange(mode):
    global newframe
    try:
        newframe=PyHaier.SetMode(mode)
        if use_mqtt == "1":
            client.publish(mqtt_topic+"/preset_mode/state", str(mode), qos=1, retain=True)
        msg="New preset mode: "+str(mode)
        state="success"
        return msg, state
    except:
        msg="Preset mode not changed"
        state="error"
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
            msg="State changed!"
            state="success"
            writed="0"
            break
        elif writed=="2":
            msg="Modbus communication error."
            state="error"
            writed="0"
        else:
            msg="Modbus connection timeout."
            state="error"
            writed="0"
        time.sleep(0.2)
    if mqtt == "1":
        return "OK"
    else:
        return jsonify(msg=msg, state=state)

def curvecalc():
    if status[statusmap.index("pch")] == "on":
        if heatingcurve == "auto":
            if isfloat(status[statusmap.index("intemp")]) and isfloat(status[statusmap.index("outtemp")]):
                insidetemp=float(status[statusmap.index("intemp")])
                outsidetemp=float(status[statusmap.index("outtemp")])
                settemp=float(status[statusmap.index("settemp")])
                t1=(outsidetemp/(320-(outsidetemp*4)))
                t2=pow(settemp,t1)
                sslope=float(slope)
                ps=int(pshift)
                amp=int(hcamp)
                heatcurve = round(((0.55*sslope*t2)*(((-outsidetemp+20)*2)+settemp+ps)+((settemp-insidetemp)*amp))*2)/2
                status[statusmap.index("hcurve")]=heatcurve
                if use_mqtt == '1':
                    client.publish(mqtt_topic+"/heatcurve", str(heatcurve))
                if 25.0 < heatcurve < 55.0:
                    try:
                        logging.info("turn on heat demand")
                        gpiocontrol("heatdemand", "1")
                        tempchange("heat", heatcurve, "1")
                    except:
                        logging.error("Set chtemp ERROR")
                else:
                    logging.info("turn off heat demand")
                    gpiocontrol("heatdemand", "0")
            else:
                status[statusmap.index("hcurve")]="Error"
        elif heatingcurve == "manual":
            status[statusmap.index("hcurve")]="11"
        elif heatingcurve == "1" or heatingcurve == "2" or heatingcurve == "3":
            status[statusmap.index("hcurve")] = "2"
def calcdewpoint():
    if status[statusmap.index("pcool")] == "on":
        hum=float(status[statusmap.index("humid")])
        temp=float(status[statusmap.index("intemp")])
        h=((math.log10(float(hum))-2)/0.4343)+((17.62*float(temp))/(243.12+float(temp)))
        h=((243.12*h)/(17.62-h))
        dewpoint=round(h*2)/2
        status[statusmap.index("dewpoint")] = dewpoint
        if user_mqtt == '1':
            client.publish(mqtt_topic+"/dewpoint", str(dewpoint))
        if 6.0 < dewpoint < 20.0
            try:
                logging.info("turn on cool demand")
                gpiocontrol('cooldemand', '1')
                tempchange("cool", dewpoint, '0')
            except:
                logging.error("Set cooltemp ERROR")
        else:
            logging.info("turn off cool demand")
            gpiocontrol("cooldemand",0)

def updatecheck():
    gitver=subprocess.run(['git', 'ls-remote', 'origin', '-h', 'refs/heads/'+release ], stdout=subprocess.PIPE).stdout.decode('utf-8')[0:40]
    localver=subprocess.run(['cat', '.git/refs/heads/'+release], stdout=subprocess.PIPE).stdout.decode('utf-8')[0:40]
    if localver != gitver:
	    msg="Availible"
    else:
	    msg="Not Availible"
    return jsonify(update=msg)

def installupdate():
    subprocess.Popen("systemctl restart haierupdate.service", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return jsonify(updated="OK")

def restart():
    subprocess.Popen("systemctl restart haier.service", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return jsonify(restarted="OK")

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
    dewpoint=status[statusmap.index("dewpoint")]
    return jsonify(intemp=intemp, outtemp=outtemp, setpoint=stemp, hcurve=hcurve,dhw=dhw,tank=tank, mode=mode,humid=humid,pch=pch,pdhw=pdhw,pcool=pcool,dewpoint=dewpoint)

def GetInsideTemp(param):
    if param == "builtin":
        result=subprocess.check_output('./bin/dht22s')
        intemp=result.decode('utf-8').split('#')[1]
        return intemp
    elif param == "ha":
        # connect to Home Assistant API and get status of inside temperature entity
        url="http://"+config['HOMEASSISTANT']['HAADDR']+":"+config['HOMEASSISTANT']['HAPORT']+"/api/states/"+config['HOMEASSISTANT']['insidesensor']
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
                response = "Entity state not found"
        except:
            response = "Error"
        return response
    else:
        return -1

def GetOutsideTemp(param):
    if param == "builtin":
        try:
            sensor = W1ThermSensor()
            temperature = sensor.get_temperature()
            return temperature
        except W1ThermSensorError as e:
            sys.stderr.write("Error: cannot read outside temperature")
            return "0"
    elif param == "ha":
        # connect to Home Assistant API and get status of outside temperature entity
        url="http://"+config['HOMEASSISTANT']['HAADDR']+":"+config['HOMEASSISTANT']['HAPORT']+"/api/states/"+config['HOMEASSISTANT']['outsidesensor']
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
                response = "Entity state not found"
        except:
            response = "Error"
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
        url="http://"+config['HOMEASSISTANT']['HAADDR']+":"+config['HOMEASSISTANT']['HAPORT']+"/api/states/"+config['HOMEASSISTANT']['humiditysensor']
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
                response = "Entity state not found"
        except:
            response = "Error"
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

#Reading parameters
def GetParameters():
    global R101
    global R141
    global R201
    if len(R141) == 16:
        tank=PyHaier.GetDHWCurTemp(R141)
        #status[statusmap.index("tank")] = tank
        ischanged("tank", tank)
    if len(R201) == 1:
        mode=PyHaier.GetMode(R201)
        #status[statusmap.index("mode")] = mode
        ischanged("mode", mode)
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
        raise ValueError("username and password are required.")

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
    msg="Password changed"
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
        return render_template('index.html', theme=theme, version=version, needrestart=needrestart)

@app.route('/theme', methods=['POST'])
def theme_route():
    theme = request.form['theme']
    settheme(theme)
    return theme


@app.route('/settings', methods=['GET','POST'])
@login_required
def settings():
    if request.method == 'POST':
        saved="1"
        global needrestart
        needrestart=1
        for key, value in request.form.items():
            KEY1=f'{key.split("$")[0]}'
            KEY2=f'{key.split("$")[1]}'
            VAL=f'{value}'
            config[KEY1][KEY2] = str(VAL)    # update
            with open('config.ini', 'w') as configfile:    # save
                config.write(configfile)
    logserver=socket.gethostbyname(socket.gethostname())
    theme = status[statusmap.index("theme")]
    timeout = config['DEFAULT']['heizfreq']
    intemp=status[statusmap.index("intemp")]
    outtemp=status[statusmap.index("outtemp")]
    heatingcurve = config['SETTINGS']['heatingcurve']
    slope = config['SETTINGS']['hcslope']
    pshift = config['SETTINGS']['hcpshift']
    hcamp = config['SETTINGS']['hcamp']
    bindaddr = config['DEFAULT']['bindaddress']
    bindport = config['DEFAULT']['bindport']
    modbusdev = config['DEFAULT']['modbusdev']
    release = config['DEFAULT']['release']
    settemp = config['SETTINGS']['settemp']
    insidetemp = config['SETTINGS']['insidetemp']
    outsidetemp = config['SETTINGS']['outsidetemp']
    humidity = config['SETTINGS']['humidity']
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


@app.route('/statechange', methods=['POST'])
@login_required
def change_state_route():
    mode = request.form['mode']
    value = request.form['value']
    information = statechange(mode, value, "0")
    return information

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

# Function to run the background function using a scheduler
def run_background_function():
    job = every(10).seconds.do(GetParameters)
    job2 = every(int(timeout)).minutes.do(curvecalc)
    job3 = every(int(timeout)).minutes.do(calcdewpoint)
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
    while True:
        if not bg_thread.is_alive():
            logging.error("Background thread DEAD")
        elif not serial_thread.is_alive():
            logging.error("serial Thread DEAD")
        elif not mqtt_bg.is_alive() and use_mqtt == "1":
            logging.error("MQTT thread DEAD")
        time.sleep(1)
        if event.is_set():
            break

# Start the Flask app in a separate thread
if __name__ == '__main__':
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