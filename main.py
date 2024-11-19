from flask_simplelogin import SimpleLogin,is_logged_in,login_required, get_username
from werkzeug.security import check_password_hash, generate_password_hash
from schedule import every, run_pending, get_jobs, clear, cancel_job
from flask import Flask, flash, render_template, request, session, jsonify, redirect, Markup, send_file, url_for
from flask_babel import Babel, gettext
from pymodbus.client.sync import ModbusSerialClient
from w1thermsensor import W1ThermSensor
from werkzeug.utils import secure_filename
import collections
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
import traceback
import jinja2
import PyHaier
import urllib.request
import socket
import serial
import signal
import base64
import json
import time
import sys
import io
import os

version="1.39"
ip_address=subprocess.run(['hostname', '-I'], check=True, capture_output=True, text=True).stdout.strip()
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
    global expert_mode
    expert_mode = config['MAIN']['expert_mode']
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
    global omlat
    omlat = config['SETTINGS']['omlat']
    global omlon
    omlon = config['SETTINGS']['omlon']
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
    global kwhnowcorr 
    kwhnowcorr = config['SETTINGS']['kwhnowcorr']
    global lohysteresis
    lohysteresis = config['SETTINGS']['lohysteresis']
    global hihysteresis
    hihysteresis = config['SETTINGS']['hihysteresis']
    global hcman
    hcman = config['SETTINGS']['hcman'].split(',')
    global use_hpiapp
    use_hpiapp = config['HPIAPP']['hpiapp']
    global hpi_token
    hpi_token = config['HPIAPP']['token']
    global use_mqtt
    use_mqtt = config['MQTT']['mqtt']
    global mqtt_broker_addr
    mqtt_broker_addr=config['MQTT']['address']
    global mqtt_broker_port
    mqtt_broker_port=config['MQTT']['port']
    global mqtt_ssl
    mqtt_ssl=config['MQTT']['mqtt_ssl']
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
    global ha_mqtt_discovery
    ha_mqtt_discovery=config['HOMEASSISTANT']['ha_mqtt_discovery']
    global ha_mqtt_discovery_prefix
    ha_mqtt_discovery_prefix = config['HOMEASSISTANT']['ha_mqtt_discovery_prefix']


loadconfig()
newframe=[]
writed=""
needrestart=0
dead=0
if use_hpiapp == '1':
    jwt_payload=hpi_token.split('.')[1]
    hpitokenjson=json.loads(base64.urlsafe_b64decode(jwt_payload + '=' * (4 - len(jwt_payload) % 4)).decode())
    hpi_username=hpitokenjson['username']
    hpi_topic="data/"+hpi_username
datechart=collections.deque(8640*[''], 8640)
tankchart=collections.deque(8640*[''], 8640)
twichart=collections.deque(8640*[''], 8640)
twochart=collections.deque(8640*[''], 8640)
tdchart=collections.deque(8640*[''], 8640)
tschart=collections.deque(8640*[''], 8640)
thichart=collections.deque(8640*[''], 8640)
thochart=collections.deque(8640*[''], 8640)
taochart=collections.deque(8640*[''], 8640)
pdchart=collections.deque(8640*[''], 8640)
pschart=collections.deque(8640*[''], 8640)
intempchart=collections.deque(8640*[''], 8640)
outtempchart=collections.deque(8640*[''], 8640)
humidchart=collections.deque(8640*[''], 8640)
hcurvechart=collections.deque(8640*[''], 8640)

modbus =  ModbusSerialClient(method = "rtu", port=modbusdev,stopbits=1, bytesize=8, parity='E', baudrate=9600)
ser = serial.Serial(port=modbusdev, baudrate = 9600, parity=serial.PARITY_EVEN,stopbits=serial.STOPBITS_ONE,bytesize=serial.EIGHTBITS,timeout=1)
app = Flask(__name__)
babel = Babel()
UPLOAD_FOLDER = '/opt/haier'
ALLOWED_EXTENSIONS = {'hpi'}
app.config['SECRET_KEY'] = '2bb80d537b1da3e38bd30361aa855686bde0eacd7162fef6a25fe97bf527a25b'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
@app.before_request
def make_session_permanent():
    session.permanent = True
set_log_level = log_level_info.get(loglevel, logging.ERROR)
logging.getLogger().setLevel(set_log_level)

GPIO.setup(modbuspin, GPIO.OUT) #modbus
GPIO.setup(freqlimitpin, GPIO.OUT) #freq limit
GPIO.setup(heatdemandpin, GPIO.OUT) # heat demand
GPIO.setup(cooldemandpin, GPIO.OUT) # cool demand

statusdict={'intemp':{'mqtt':'/intemp/state','value':'N.A.'},'outtemp':{'mqtt':'/outtemp/state','value':'N.A.'},'settemp':{'mqtt':'/temperature/state','value':settemp},'hcurve':{'mqtt':'/heatcurve','value':'N.A.'},'dhw':{'mqtt':'/dhw/temperature/state','value':'N.A.'},'tank':{'mqtt':'/dhw/curtemperature/state','value':'N.A.'},'mode':{'mqtt':'/preset_mode/state','value':'N.A.'},'humid':{'mqtt':'/humidity/state','value':'N.A.'},'pch':{'mqtt':'/mode/state','value':'N.A.'},'pdhw':{'mqtt':'/dhw/mode/state','value':'N.A.'},'pcool':{'mqtt':'/mode/state','value':'N.A.'},'theme':{'mqtt':'0','value':'light'},'tdts':{'mqtt':'/details/tdts/state','value':'N.A.'},'archerror':{'mqtt':'/details/archerror/state','value':'N.A.'},'compinfo':{'mqtt':'/details/compinfo/state','value':'N.A.'},'fans':{'mqtt':'/details/fans/state','value':'N.A.'},'tao':{'mqtt':'/details/tao/state','value':'N.A.'},'twitwo':{'mqtt':'/details/twitwo/state','value':'N.A.'},'thitho':{'mqtt':'/details/thitho/state','value':'N.A.'},'pump':{'mqtt':'/details/pump/state','value':'N.A.'},'pdps':{'mqtt':'/details/pdps/state','value':'N.A.'},'threeway':{'mqtt':'/details/threeway/state','value':'N.A.'},'chkwhpd':{'mqtt':'/details/chkwhpd/state','value':'0'},'dhwkwhpd':{'mqtt':'/details/dhwkwhpd','value':'0'}}
R101=[0,0,0,0,0,0]
R141=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
R201=[0]
R241=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
twicheck=[0,0]

def get_locale():
     return request.accept_languages.best_match(['en', 'pl'])

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def handler(signum, frame):
    logging.info(str(signum)+" "+str(signal.Signals(signum).name))
    print(colored("\rCtrl-C - Closing... please wait, this can take a while.", 'red', attrs=["bold"]))
    GPIO.cleanup(modbuspin)
    GPIO.cleanup(freqlimitpin)
    GPIO.cleanup(heatdemandpin)
    GPIO.cleanup(cooldemandpin)
    if use_mqtt == '1':
        topic=str(client._client_id.decode())
        client.publish(topic + "/connected","offline", qos=1, retain=True)
        client.disconnect()
    if use_hpiapp == '1':
        topic=str(hpiapp._client_id.decode())
        hpiapp.publish(topic + "/connected","offline",qos=1, retain=True)
        hpiapp.disconnect()
    event.set()
    clear()
    sys.exit()

def b2s(value):
    return (value and 'success') or 'error'

def is_raspberrypi():
    try:
        with io.open('/sys/firmware/devicetree/base/model', 'r') as m:
            if 'raspberry pi' in m.read().lower(): return True
    except Exception: pass
    return False

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

def queue_pub(dtopic, value):
    global services
    ctopic=['pdhw', 'pch']
    for clnt in services:
        try:
            if dtopic in ctopic:
                value=value.replace('on','heat')
            if dtopic == 'pcool':
                value=value.replace('on','cool')
            topic=str(clnt._client_id.decode()+statusdict[dtopic]['mqtt'])
            clnt.publish(topic, str(value), qos=1, retain=True)
        except:
            logging.error("MQTT: cannot publish "+dtopic)


def WritePump(newframe): #rewrited
    def WriteRegisters(count):
        global writed
        if count == 6:
            register = 101
        elif count == 1:
            register = 201
        time.sleep(1)
        modbus.connect()
        for x in range(5):
            time.sleep(1)
            logging.info("MODBUS: write register "+str(register)+", attempt: "+str(x)+" of 5")
            try:
                result=modbus.write_registers(register, newframe[1], unit=17)
                logging.info(result)
                time.sleep(0.1)
                result=modbus.read_holding_registers(register, count, unit=17)
                logging.info(newframe[0])
                logging.info(result.registers)
                if result.registers != newframe[0]:
                    logging.info("MODBUS: Registers saved correctly")
                    writed="1"
                    break
            except:
                logging.info("MODBUS: Writing error, make another try...")
        modbus.close()
        gpiocontrol("modbus","0")
        return True
    logging.info("Writing Modbus Frame: "+str(newframe[1]))
    while True:
        rs = ser.read(1).hex()
        if rs == "032c":
            for ind in range(22):
                ser.read(2).hex()
        gpiocontrol("modbus", "1")
        break;
    if len(newframe[1]) in [1,6]:
        WriteRegisters(len(newframe[1]))
    else:
        logging.info("MODBUS: New frame has wrong length, exit")
        return False

def ReadPump():
    global R101
    global R141
    global R201
    global R241
    global newframe
    T101=[]
    T141=[]
    T201=[]
    T241=[]
    time.sleep(0.2)
    while (1):
        if (ser.isOpen() == False):
            logging.warning(colored("Closed serial connection.", 'red', attrs=["bold"]))
            break
        if event.is_set():
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            ser.close()
            break
        if newframe:
            WritePump(newframe)
            newframe=[]
        try:
            rs = ser.read(1).hex()
            if rs == "11":
                rs = ser.read(2).hex()
                if rs == "030c":
                    T101 = []
                    D101 = []
                    for ind in range(6):
                        rs = ser.read(2).hex()
                        if rs:
                            T101.append(int(rs, 16))
                            m, l = divmod(int(rs, 16), 256)
                            D101.append(m)
                            D101.append(l)
                    R101=T101
                    logging.debug(D101)
                if rs == "0320":
                    T141 = []
                    D141 = []
                    for ind in range(16):
                        rs = ser.read(2).hex()
                        if rs:
                            T141.append(int(rs, 16))
                            m, l = divmod(int(rs, 16), 256)
                            D141.append(m)
                            D141.append(l)
                    R141=T141
                    logging.debug(D141)
                if rs == "0302":
                    T201 = []
                    for ind in range(1):
                        rs = ser.read(2).hex()
                        if rs:
                            T201.append(int(rs, 16))
                    logging.debug(R201)
                    R201=T201
                if rs == "032c":
                    T241 = []
                    D241 = []
                    for ind in range(22):
                        rs = ser.read(2).hex()
                        if rs:
                            T241.append(int(rs, 16))
                            m, l = divmod(int(rs, 16), 256)
                            D241.append(m)
                            D241.append(l)
                    R241=T241
                    logging.debug(D241)
        except:
            logging.info(traceback.print_exc())
            break

def on_connect(client, userdata, flags, rc):
    topic=str(client._client_id.decode())
    logging.info(colored("MQTT - Connected - "+topic, "green", attrs=['bold']))
    client.subscribe(topic + '/#')
    client.publish(topic + "/connected","online", qos=1, retain=True)
    if ha_mqtt_discovery == "1":
        client.subscribe(ha_mqtt_discovery_prefix+"/status")
        client.subscribe("hass/status")
        configure_ha_mqtt_discovery()


def on_disconnect(client, userdata, rc):  # The callback for when
    logging.warning(colored("Disconnected from MQTT with code: {0}".format(str(rc)), 'red', attrs=['bold']))

def on_message(client, userdata, msg):  # The callback for when a PUBLISH 
    topic=str(client._client_id.decode())
    if msg.topic == topic + "/power/set":
        logging.info("New power state from mqtt:")
        client.publish(topic + "/power/state",msg.payload.decode('utf-8'), qos=1, retain=True)
    elif msg.topic == topic + "/preset_mode/set":
        logging.info("New preset mode")
        payload=str(msg.payload.decode('utf-8')).lower()
        presets=['quiet', 'eco', 'turbo']
        if payload in presets:
            new_presetchange(payload)

    elif msg.topic == topic + "/flimit/set":
        logging.info("Frequency limit")
        try:
            flimitchange(str(msg.payload.decode('utf-8')))
        except:
            logging.error("MQTT: cannot set flimit relay")
    elif msg.topic == topic + "/mode/set":
        logging.info("New mode")
        newmode=msg.payload.decode('utf-8')
        if newmode == "heat":
            try:
                statechange("pch", "on", "1")
                client.publish(topic + "/mode/state",newmode, qos=1, retain=True)
            except:
                logging.error("MQTT: cannot set mode")
        elif newmode == "cool":
            try:
                statechange("pcool", "on", "1")
                client.publish(topic + "/mode/state",newmode, qos=1, retain=True)
            except:
                logging.error("MQTT: cannot set mode")
        elif newmode == "off":
            try:
                statechange("pump", "off", "1")
                client.publish(topic + "/mode/state",newmode, qos=1, retain=True)
            except:
                logging.error("MQTT: cannot set mode")
        else:
            logging.error("MQTT: mode unsupported")

    elif msg.topic == topic + "/temperature/set":
        try:
            mesg,response = new_tempchange("heat",format(float(msg.payload.decode())),"0")
            if response:
                client.publish(topic + "/temperature/state",str(float(msg.payload.decode())), qos=1, retain=True)
        except:
            logging.error("MQTT: New temp error: payload - "+str(float(msg.payload.decode())))
    elif msg.topic == topic + "/dhw/mode/set":
        logging.info("New mode")
        payload=msg.payload.decode('utf-8')
        if payload == "heat":
            newmode="on"
        else:
            newmode=payload
        try:
            statechange("pdhw", str(newmode), "1")
            client.publish(topic + "/dhw/mode/state", str(payload), qos=1, retain=True)
        except:
            logging.error("MQTT: cannot change DHW mode - payload:"+str(newmode))
    elif msg.topic == topic + "/dhw/temperature/set":
        logging.info("New temperature")
        newtemp=int(float(msg.payload.decode('utf-8')))
        try:
            msg,response = new_tempchange("dhw", str(newtemp), "1")
            if response:
                client.publish(topic + "/dhw/temperature/state", str(newtemp), qos=1, retain=True)
        except:
            logging.error("MQTT: cannot change DHW temperature - payload:"+str(newtemp))
    elif msg.topic == ha_mqtt_discovery_prefix + "/status" or msg.topic == "hass/status":
        if ha_mqtt_discovery == "1":
            logging.info(msg.topic + " | " + msg.payload.decode('utf-8'))
            if msg.payload.decode('utf-8').strip() == "online":
                logging.info("Home Assistant online")
                configure_ha_mqtt_discovery()
    
##### NOWE
def set_newframe(register, frame):
    global newframe
    global writed
    newframe = [register, frame]
    for i in range(50):
        if writed=="1":
            writed="0"
            return True
        time.sleep(0.2)
    return False

def saveconfig(block, name, value):
    statusdict[name]['value'] = value
    config[block][name] = str(value)
    try:
        with open('config.ini', 'w') as configfile:
            config.write(configfile)
        return True
    except:
        return False

def new_tempchange(which, value, curve):
    global R101
    if curve == "1":
        if which == "heat":
            logging.info("Central heating: "+str(value))
            chframe = PyHaier.SetCHTemp(R101, float(value))
            response=set_newframe(R101,chframe)
            return 'Central Heating', response
        elif which == "dhw":
            logging.info("Domestic Hot Water: "+value)
            dhwframe = PyHaier.SetDHWTemp(R101, int(value))
            response=set_newframe(R101,dhwframe)
            queue_pub('dhw', value)
            return 'Domestic Hot Water', response
    elif curve == "0":
        if which == "heat":
            response = saveconfig('SETTINGS', 'settemp', float(value))
            queue_pub("settemp", value)
            if ha_mqtt_discovery=="1":
                Settemp_number.set_value(float(value))
            return 'Central Heating', response

def new_presetchange(mode):
    global R201
    logging.info("PRESET MODE: changed to: "+str(mode))
    response=set_newframe(R201,PyHaier.SetMode(mode))
    queue_pub('mode', mode)
    return 'Preset Mode', response

def new_flimitchange(mode):
    try:
        gpicontrol("freqlimit", mode)
    except:
        return False

def flimitchange(mode):
    try:
        gpiocontrol("freqlimit", mode)
        msg="Frequency limit relay: "+str(mode)
        state="success"
        logging.info("Frequency limit relay changed to: "+ str(mode))
        if use_hpiapp == "1":
            topic=str(hpiapp._client_id.decode())
            hpiapp.publish(topic + "/flimit/state", str(mode), qos=1, retain=True)
        if use_mqtt == "1":
            client.publish(mqtt_topic + "/flimit/state", str(mode), qos=1, retain=False)
        return msg,state
    except:
        msg="Frequency limit not changed"
        state="error"
        logging.error("Cannot change frequency limit relay")
        if use_hpiapp == "1":
            topic=str(hpiapp._client_id.decode())
            hpiapp.publish(topic + "/flimit/state", "error", qos=1, retain=True)
        if use_mqtt == "1":
            client.publish(mqtt_topic + "/flimit/state", "error", qos=1, retain=False)
        return msg, state


def statechange(mode,value,mqtt):
    global R101
    pcool=statusdict['pcool']['value']
    pch=statusdict['pch']['value']
    pdhw=statusdict['pdhw']['value']
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
    if len(R101) > 1:
        if int(R101[0])%2 == 0:
            newframe=[R101, PyHaier.SetState(R101, "on")]
            time.sleep(2)
        newframe=[R101, PyHaier.SetState(R101,newstate)]
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
    if expert_mode == "1":
        mintemp=float(20)
        maxtemp=float(55)
    else:
        mintemp=float(25)
        maxtemp=float(55)
    if isfloat(statusdict['intemp']['value']):
        insidetemp=float(statusdict['intemp']['value'])
    if isfloat(statusdict['outtemp']['value']):
        outsidetemp=float(statusdict['outtemp']['value'])
    if isfloat(statusdict['settemp']['value']):
        settemp=float(statusdict['settemp']['value'])
    global heatingcurve
    if heatingcurve == 'directly':
        heatcurve=settemp
    elif heatingcurve == 'auto':
        t1=(outsidetemp/(320-(outsidetemp*4)))
        t2=pow(settemp,t1)
        sslope=float(slope)
        ps=float(pshift)
        amp=float(hcamp)
        heatcurve = round((((0.55*sslope*t2)*(((-outsidetemp+20)*2)+settemp+ps)+((settemp-insidetemp)*amp))+ps)*2)/2
    elif heatingcurve == 'static':
        sslope=float(slope)
        heatcurve = round((settemp+(sslope*20)*pow(((settemp-outsidetemp)/20), 0.7))*2)/2
    elif heatingcurve == 'manual':
        if float(outsidetemp) < -15:
            heatcurve=float(hcman[0])
        elif -15 <= outsidetemp < -10:
            heatcurve=float(hcman[1])
        elif -10 <= outsidetemp < -5:
            heatcurve=float(hcman[2])
        elif -5 <= outsidetemp < 0:
            heatcurve=float(hcman[3])
        elif 0 <= outsidetemp < 5:
            heatcurve=float(hcman[4])
        elif 5 <= outsidetemp < 10:
            heatcurve=float(hcman[5])
        elif 10 <= outsidetemp < 15:
            heatcurve=float(hcman[6])
        elif outsidetemp >= 15:
            heatcurve=float(hcman[7])

    queue_pub('hcurve', heatcurve)
    #thermostat mode
    if mintemp <= heatcurve <= maxtemp:
        if insidetemp < settemp-float(lohysteresis):
            try:
                if GPIO.input(heatdemandpin) != "1":
                    logging.info("turn on heat demand")
                    gpiocontrol("heatdemand", "1")
                if str(statusdict['hcurve']['value']) != str(heatcurve):
                    new_tempchange("heat", heatcurve, "1")
            except:
                logging.error("Set chtemp ERROR")
        elif insidetemp > settemp+float(hihysteresis):
            if GPIO.input(heatdemandpin) != "0":
                logging.info("turn off heat demand")
                gpiocontrol("heatdemand", "0")
        else:
            logging.info("Thermostat Mode: Don't do anything, the temperature is within the limits of the hysteresis")
    else:
        if GPIO.input(heatdemandpin) != "0":
            logging.info("turn off heat demand")
            gpiocontrol("heatdemand", "0")
    statusdict['hcurve']['value']=heatcurve
    threeway=statusdict['threeway']['value']
    compinfo=statusdict['compinfo']['value']
    if len(compinfo) > 0:
        if dhwwl=="1" and compinfo[0] != 0 and threeway == "DHW":
            logging.info("dont change flimit in DHW mode")
        else:
            if flimit == "auto":
                if outsidetemp >= float(flimittemp):
                    logging.info("turn on freq limit")
                    flimitchange("1")
                elif outsidetemp <= float(flimittemp)+0.5:
                    logging.info("turn off freq limit")
                    flimitchange("0")
            if presetautochange == "auto":
                mode=statusdict['mode']['value']
                if outsidetemp >= float(presetquiet) and mode != "quiet":
                    new_presetchange("quiet")
                elif outsidetemp <= float(presetturbo) and mode != "turbo":
                    new_presetchange("turbo")
                elif outsidetemp > float(presetturbo) and outsidetemp < float(presetquiet) and mode != "eco":
                    new_presetchange("eco")


def updatecheck():
    gitver=subprocess.run(['git', 'ls-remote', 'origin', '-h', 'refs/heads/'+release ], stdout=subprocess.PIPE).stdout.decode('utf-8')[0:40]
    localver=subprocess.run(['cat', '.git/refs/heads/'+release], stdout=subprocess.PIPE).stdout.decode('utf-8')[0:40]
    if localver != gitver:
        msg=gettext("Available")
    else:
        msg=gettext("Not Available")
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
            tdts=PyHaier.GetTdTs(R241)
            archerror=PyHaier.GetArchError(R241)
            compinfo=PyHaier.GetCompInfo(R241)
            fans=PyHaier.GetFanRpm(R241)
            pdps=PyHaier.GetPdPs(R241)
            tao=PyHaier.GetTao(R241)
            isr241=0
    while (isr141):
        if (len(R141) == 16):
            twitwo = PyHaier.GetTwiTwo(R141)
            thitho = PyHaier.GetThiTho(R141)
            pump=PyHaier.GetPump(R141)
            threeway=PyHaier.Get3way(R141)
            isr141=0
    chkwhpd=statusdict['chkwhpd']['value']
    dhwkwhpd=statusdict['dhwkwhpd']['value']
    return twitwo, thitho, tdts, archerror, compinfo,fans, pdps, tao,pump,threeway,chkwhpd,dhwkwhpd

def getdata():
    intemp=statusdict['intemp']['value']
    outtemp=statusdict['outtemp']['value']
    stemp=statusdict['settemp']['value']
    hcurve=statusdict['hcurve']['value']
    dhw=statusdict['dhw']['value']
    tank=statusdict['tank']['value']
    mode=statusdict['mode']['value']
    humid=statusdict['humid']['value']
    pch=statusdict['pch']['value']
    pdhw=statusdict['pdhw']['value']
    pcool=statusdict['pcool']['value']
    presetch = presetautochange 
    heatdemand=GPIO.input(heatdemandpin)
    cooldemand=GPIO.input(cooldemandpin)
    flimiton=GPIO.input(freqlimitpin)
    ltemp = flimittemp
    heatingcurve = config['SETTINGS']['heatingcurve']
    return jsonify(intemp=intemp, outtemp=outtemp, setpoint=stemp, hcurve=hcurve,dhw=dhw,tank=tank, mode=mode,humid=humid,pch=pch,pdhw=pdhw,pcool=pcool,flimit=flimit,heatdemand=heatdemand,cooldemand=cooldemand,flimiton=flimiton, ltemp=ltemp, presetch=presetch, presetquiet=presetquiet, presetturbo=presetturbo, heatingcurve=heatingcurve)

def get_json_data():
    intemp=statusdict['intemp']['value']
    outtemp=statusdict['outtemp']['value']
    stemp=statusdict['settemp']['value']
    hcurve=statusdict['hcurve']['value']
    dhw=statusdict['dhw']['value']
    tank=statusdict['tank']['value']
    mode=statusdict['mode']['value']
    humid=statusdict['humid']['value']
    pch=statusdict['pch']['value']
    pdhw=statusdict['pdhw']['value']
    pcool=statusdict['pcool']['value']
    presetch = presetautochange
    heatdemand=GPIO.input(heatdemandpin)
    cooldemand=GPIO.input(cooldemandpin)
    flimiton=GPIO.input(freqlimitpin)
    ltemp = flimittemp
    heatingcurve = config['SETTINGS']['heatingcurve']
    isr241=1
    isr141=1
    while (isr241):
        if (len(R241) == 22):
            tdts=PyHaier.GetTdTs(R241)
            archerror=PyHaier.GetArchError(R241)
            compinfo=PyHaier.GetCompInfo(R241)
            fans=PyHaier.GetFanRpm(R241)
            pdps=PyHaier.GetPdPs(R241)
            tao=PyHaier.GetTao(R241)
            isr241=0
    while (isr141):
        if (len(R141) == 16):
            twitwo = PyHaier.GetTwiTwo(R141)
            thitho = PyHaier.GetThiTho(R141)
            pump=PyHaier.GetPump(R141)
            threeway=PyHaier.Get3way(R141)
            isr141=0
    chkwhpd=statusdict['chkwhpd']['value']
    dhwkwhpd=statusdict['dhwkwhpd']['value']
    return jsonify(locals())

def GetInsideTemp(param):
    if param == "builtin":
        if is_raspberrypi():
            dhtexec='dht22r'
        else:
            dhtexec='dht22n'

        try:
            result=subprocess.check_output('./bin/'+dhtexec)
            intemp=result.decode('utf-8').split('#')[1]
        except:
            intemp='ERROR'
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
    elif param == "tao":
        temperature = status[statusmap.index("tao")]
        return temperature
    elif param == "openmeteo":
        global omlat
        global omlon
        try:
            with urllib.request.urlopen("https://api.open-meteo.com/v1/forecast?latitude="+str(omlat)+"&longitude="+str(omlon)+"&current=temperature_2m") as url:
                omdata = json.load(url)
            temperature=omdata['current']['temperature_2m']
            return temperature
        except:
            temperature=0
            return temperature
    else:
        return -1

def GetHumidity(param):
    if param == "builtin":
        if is_raspberrypi():
            dhtexec='dht22r'
        else:
            dhtexec='dht22n'

        try:
            result=subprocess.check_output('./bin/'+dhtexec)
            intemp=result.decode('utf-8').split('#')[0]
        except:
            intemp='ERROR'

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
    statusdict['theme']['value']=theme
    return theme

# Function campare new value with old, as "old" you need to provide name of status. for example 'pch'
def ischanged(old, new):
    if statusdict[old]['value'] != new:
        logging.info("ischanged: status "+str(old)+" has changed. Set new value - "+str(new))
        statusdict[old]['value']=new
        queue_pub(old, new)

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
                    mode=statusdict['mode']['value']
                    flimiton=GPIO.input(freqlimitpin)
                    logging.info("AntiON-OFF: current mode - "+str(mode))
                    if mode == "turbo":
                        logging.info("AntiON-OFF: changing mode to: ECO")
                        new_presetchange("eco")
                    elif mode == "eco":
                        logging.info("AntiON-OFF: changing mode to: quiet")
                        new_presetchange("quiet")
                    elif mode == "quiet":
                        logging.info("AntiON-OFF: mode in lowest setting, turn on frequency limit relay")
                        flimitchange("1")
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
        pch=statusdict['pch']['value']
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
        pdhw=statusdict['pdhw']['value']
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
    global datechart
    global tankchart
    global twichart
    global twochart
    global thichart
    global thochart
    global taochart
    global pdchart
    global pschart
    global intempchart
    global outtempchart
    global humidchart
    global hcurvechart
    now=datetime.now().strftime("%d %b %H:%M")
    datechart.append(str(now))

    if len(R141) == 16:
        tank = PyHaier.GetDHWCurTemp(R141)
        twitwo = PyHaier.GetTwiTwo(R141)
        thitho = PyHaier.GetThiTho(R141)
        pump=PyHaier.GetPump(R141)
        threeway=PyHaier.Get3way(R141)
        ischanged("tank", tank)
        tankchart.append(tank)
        ischanged("twitwo", twitwo)
        twichart.append(twitwo[0])
        twochart.append(twitwo[1])
        ischanged("thitho", thitho)
        thichart.append(thitho[0])
        thochart.append(thitho[1])
        ischanged("pump", pump)
        ischanged("threeway", threeway)
        deltacheck(twitwo)
    if len(R201) == 1:
        mode=PyHaier.GetMode(R201)
        ischanged("mode", mode)
    if len(R241) == 22:
        tdts=PyHaier.GetTdTs(R241)
        archerror=PyHaier.GetArchError(R241)
        compinfo=PyHaier.GetCompInfo(R241)
        #0.0002777778
        kwhnow=float(float(compinfo[2])*float(compinfo[3])/1000*float(kwhnowcorr))
        if str(statusdict['threeway']['value']) == 'DHW':
            dhwkwhpd=float(statusdict['dhwkwhpd']['value'])+kwhnow
            ischanged("dhwkwhpd", dhwkwhpd)
        elif str(statusdict['threeway']['value']) == "CH":
            chkwhpd=float(statusdict['chkwhpd']['value'])+kwhnow
            ischanged("chkwhpd",chkwhpd)
        fans=PyHaier.GetFanRpm(R241)
        pdps=PyHaier.GetPdPs(R241)
        tao=PyHaier.GetTao(R241)
        ischanged("tdts", tdts)
        tdchart.append(tdts[0])
        tschart.append(tdts[1])
        ischanged("archerror", archerror)
        ischanged("compinfo", compinfo)
        ischanged("pdps", pdps)
        pdchart.append(pdps[0])
        pschart.append(pdps[1])
        ischanged("fans", fans)
        ischanged("tao", tao)
        taochart.append(tao)
    if len(R101) == 6:
        dhw=PyHaier.GetDHWTemp(R101)
        ischanged("dhw", dhw)
        powerstate=PyHaier.GetState(R101)
        if 'Heat' in powerstate:
            ischanged("pch", "on")
        else:
            ischanged("pch", "off")
        if 'Cool' in powerstate:
            ischanged("pcool", "on")
        else:
            ischanged("pcool", "off")
        if not any(substring in powerstate for substring in ["Cool", "Heat"]):
            if use_mqtt == "1":
                client.publish(mqtt_topic + "/mode/state", "off")
            if use_hpiapp == "1":
                topic=str(hpiapp._client_id.decode())
                hpiapp.publish(topic + "/mode/state", "off", qos=1, retain=True)

        if 'Tank' in powerstate:
            ischanged("pdhw", "on")
        else:
            ischanged("pdhw", "off")
    ischanged("intemp", GetInsideTemp(insidetemp))
    ischanged("outtemp", GetOutsideTemp(outsidetemp))
    ischanged("humid", GetHumidity(humidity))
    scheduler()
    intempchart.append(statusdict['intemp']['value'])
    outtempchart.append(statusdict['outtemp']['value'])
    humidchart.append(statusdict['humid']['value'])
    hcurvechart.append(statusdict['hcurve']['value'])
    threeway=statusdict['threeway']['value']
    compinfo=statusdict['compinfo']['value']
    preset=statusdict['mode']['value']
    flimiton=GPIO.input(freqlimitpin)
    if len(compinfo) > 0:
        if dhwwl == "1" and compinfo[0] > 0 and threeway == "DHW" and (flimiton == "1" or preset != "turbo"):
            logging.info("DHWWL Function ON")
            flimitchange("0")
            new_presetchange("turbo")

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
        theme=statusdict['theme']['value']
        global outsidetemp
        return render_template('index.html', theme=theme, version=version, needrestart=needrestart, flimit=flimit, outsidetemp=outsidetemp)

@app.route('/theme', methods=['POST'])
def theme_route():
    theme = request.form['theme']
    settheme(theme)
    return theme

@app.route('/get_json_data')
def get_json_route():
    return get_json_data()

@app.route('/backup')
def backup_route():
    try:
        subprocess.check_output("7zr a backup.7z config.ini schedule_*", shell=True).decode().rstrip('\n')
        return send_file('/opt/haier/backup.7z', download_name='backup.hpi')
    except Exception as e:
        return str(e)

@app.route('/restore', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            flash('File uploaded, please restart HaierPi service', 'success')
            subprocess.check_output("7zr e -aoa /opt/haier/"+filename+" /opt/haier config.ini schedule_ch.json schedule_dhw.json", shell=True).decode().rstrip('\n')
            return redirect('/', code=302)
    return render_template('upload.html')

@app.route('/charts', methods=['GET','POST'])
def charts_route():
    theme=statusdict['theme']['value']
#    theme=status[statusmap.index("theme")]
    chartdate=list(datechart)
    charttank=list(tankchart)
    charttwi=list(twichart)
    charttwo=list(twochart)
    chartthi=list(thichart)
    charttho=list(thochart)
    charttao=list(taochart)
    charttd=list(tdchart)
    chartts=list(tschart)
    chartpd=list(pdchart)
    chartps=list(pschart)
    chartintemp=list(intempchart)
    chartouttemp=list(outtempchart)
    charthumid=list(humidchart)
    charthcurve=list(hcurvechart)
    return render_template('charts.html', theme=theme, chartdate=chartdate, charttank=charttank, charttwi=charttwi, charttwo=charttwo, chartthi=chartthi, charttho=charttho, charttao=charttao, charttd=charttd, chartts=chartts, chartpd=chartpd, chartps=chartps, chartintemp=chartintemp, chartouttemp=chartouttemp, charthumid=charthumid, charthcurve=charthcurve)

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
    theme=statusdict['theme']['value']
    timeout = config['MAIN']['heizfreq']
    intemp = statusdict['intemp']['value']
    outtemp = statusdict['outtemp']['value']
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
    omlat = config['SETTINGS']['omlat']
    omlon = config['SETTINGS']['omlon']
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
    hcman = config['SETTINGS']['hcman'].split(',')
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
    ha_mqtt_discovery=config['HOMEASSISTANT']['ha_mqtt_discovery']
    log_level=config['MAIN']['log_level']
    return render_template('settings.html', **locals(), version=version, needrestart=needrestart)

@app.route('/parameters', methods=['GET','POST'])
@login_required
def parameters():
    theme=statusdict['theme']['value']
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
    theme=statusdict['theme']['value']
    return  render_template('scheduler.html', ch=Markup(schedule1.read()), dhw=Markup(schedule2.read()), version=version, theme=theme)

@app.route('/change', methods=['POST'])
@login_required
def change():
    content_type = request.headers.get('Content-Type')
    logging.info(content_type)
    if content_type == 'application/json':
        if json.loads(request.data)['name'] in ['hctemperature', 'dhwtemperature']:
            logging.info(json.loads(request.data)['name'])
            return jsonify(response='OK')
        else:
            return jsonify(response='unknown command')
    else:
        return jsonify(response='ERROR, Expected JSON data.')

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
    msg, response = new_presetchange(newvalue)
    code=b2s(response)
    return jsonify(msg=msg, state=code)

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
    msg, response = new_tempchange(which,value,directly)
    code=b2s(response)
    return jsonify(msg=msg, state=code)

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
@login_required(basic=True)
def getdata_route():
    output = getdata()
    return output

@app.route('/getparams', methods=['GET'])
@login_required(basic=True)
def getparams_route():
    twitwo, thitho, tdts, archerror, compinfo, fans, pdps, tao, pump, threeway, chkwhpd, dhwkwhpd = getparams()
    return jsonify(twitwo=twitwo, thitho=thitho, tdts=tdts, archerror=archerror,compinfo=compinfo, fans=fans, pdps=pdps, tao=tao, pump=pump, threeway=threeway, chkwhpd=chkwhpd, dhwkwhpd=dhwkwhpd)

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
    client.will_set(mqtt_topic + "/connected","offline",qos=1,retain=False)
    if mqtt_ssl == '1':
        client.tls_set(tls_version=mqtt.ssl.PROTOCOL_TLS)
    client.username_pw_set(mqtt_username, mqtt_password)
    try:
        client.connect(mqtt_broker_addr, int(mqtt_broker_port))
    except:
        logging.error(colored("MQTT connection error.","red", attrs=['bold']))
    client.loop_forever()  # Start networking daemon

def connect_haierpiapp():
    global hpi_token
    global hpi_username
    global hpi_topic
    username=hpi_username
    password=hpi_token
    topic=hpi_topic
    hpiapp.on_connect = on_connect
    hpiapp.on_message = on_message
    hpiapp.on_disconnect = on_disconnect
    hpiapp.will_set(topic + "/connected","offline", qos=1,retain=True)
    hpiapp.tls_set(tls_version=mqtt.ssl.PROTOCOL_TLS)
    hpiapp.username_pw_set(username, password)
    try:
        hpiapp.connect('haierpi.pl', 8883)
    except:
        logging.error("HAIERPI APP: Connection error")
    hpiapp.loop_forever()

def configure_ha_mqtt_discovery():

    def configure_sensor(name, status_topic, unique_id, unit, device_class, state_class, template):
        jsonMsg = {
            "name" : name,
            "stat_t" : status_topic,
            "uniq_id" : unique_id,
            "unit_of_meas" : unit,
            "stat_cla" : state_class,
            "exp_aft" : "300",
            "dev" : {
                "name" : "HaierPi",
                "ids" : "HaierPi",
                "cu" : f"http://{ip_address}:{bindport}",
                "mf" : "ktostam",
                "mdl" : "HaierPi",
                "sw" : version
            } 
        }
        
        if unit is not None:
            jsonMsg["unit"] = unit
        if device_class is not None:
            jsonMsg["dev_cla"] = device_class    
        if state_class is not None:
            jsonMsg["stat_cla"] = state_class
        if template is not None:
            jsonMsg["value_template"] = template
        msg = json.dumps(jsonMsg)
        
        client.publish(ha_mqtt_discovery_prefix+f"/sensor/HaierPi/{unique_id}/config", msg, qos=1)

    def configure_number(name, command_topic, status_topic, unique_id, unit, min, max, device_class):
        msg = json.dumps(
            {
                "name" : name,
                "cmd_t" : command_topic,
                "stat_t" : status_topic,
                "uniq_id" : unique_id,
                "unit_of_meas" : unit,
                "min" : min,
                "max" : max,
                "mode" : "slider",
                "step" : "0.1",
                "dev_cla" : device_class,
                "dev" : {
                    "name" : "HaierPi",
                    "ids" : "HaierPi",
                    "cu" : f"http://{ip_address}:{bindport}",
                    "mf" : "ktostam",
                    "mdl" : "HaierPi",
                    "sw" : version
                }
            }
        )
        
        client.publish(ha_mqtt_discovery_prefix + f"/number/HaierPi/{unique_id}/config", msg, qos=1)
        
    def configure_select(name, command_topic, status_topic, unique_id, options):
        msg = json.dumps(
            {
                "name" : name,
                "cmd_t" : command_topic,
                "stat_t" : status_topic,
                "uniq_id" : unique_id,
                "options" : options,
                "dev" : {
                    "name" : "HaierPi",
                    "ids" : "HaierPi",
                    "cu" : f"http://{ip_address}:{bindport}",
                    "mf" : "ktostam",
                    "mdl" : "HaierPi",
                    "sw" : version
                }
            }
        )
        
        client.publish(ha_mqtt_discovery_prefix + f"/select/HaierPi/{unique_id}/config", msg, qos=1)
        
    logging.info("Configuring HA discovery")

    configure_number("Set temp", mqtt_topic + "/temperature/set", mqtt_topic + "/temperature/state","HaierPi_SetTemp","°C", 0.0, 50.0, "temperature")

    configure_select("Preset", mqtt_topic + "/preset_mode/set", mqtt_topic + "/preset_mode/state", "Haier_Preset", ["eco", "quiet", "turbo"])

    configure_sensor("Heating curve value",mqtt_topic + "/heatcurve","HaierPi_Heatcurve","°C", "temperature","measurement",None)
    configure_sensor("DHW set temperature",mqtt_topic + "/dhw/temperature/state","HaierPi_DHWSet","°C", "temperature","measurement",None)
    configure_sensor("DHW actual temperature",mqtt_topic + "/dhw/curtemperature/state","HaierPi_DHWCurrent","°C", "temperature","measurement",None)
    configure_sensor("Humidity inside",mqtt_topic + "/humidity/state","HaierPi_HumidityInside","%", "humidity","measurement",None)

    configure_sensor("3-way valve",mqtt_topic + "/details/threeway/state","HaierPi_3wayvalve", None, None, None, None)
    configure_sensor("Pump",mqtt_topic + "/details/pump/state","HaierPi_Pump", None, None, None, None)
    configure_sensor("Archerror",mqtt_topic + "/details/archerror/state","HaierPi_Archerror", None, None, None, None)
    configure_sensor("Mode",mqtt_topic + "/mode/state","HaierPi_Mode", None, None, None, None)
    configure_sensor("DHW Mode",mqtt_topic + "/dhw/mode/state","HaierPi_DHWMode", None, None, None, None)

    configure_sensor("Tao",mqtt_topic + "/details/tao/state","HaierPi_Tao","°C", "temperature","measurement", None)
    configure_sensor("Twi",mqtt_topic + "/details/twitwo/state","HaierPi_Twi","°C", "temperature","measurement", "{{ value_json[0] | float}}")
    configure_sensor("Two",mqtt_topic + "/details/twitwo/state","HaierPi_Two","°C", "temperature","measurement", "{{ value_json[1] | float}}")
    configure_sensor("Thi",mqtt_topic + "/details/thitho/state","HaierPi_Thi","°C", "temperature","measurement", "{{ value_json[0] | float}}")
    configure_sensor("Tho",mqtt_topic + "/details/thitho/state","HaierPi_Tho","°C", "temperature","measurement", "{{ value_json[1] | float}}")
    configure_sensor("Fan 1",mqtt_topic + "/details/fans/state","HaierPi_Fan1","rpm", None, "measurement", "{{ value_json[0] | float}}")
    configure_sensor("Fan 2",mqtt_topic + "/details/fans/state","HaierPi_Fan2","rpm", None, "measurement", "{{ value_json[1] | float}}")
    configure_sensor("Pd",mqtt_topic + "/details/pdps/state","HaierPi_Pd","Mpa", "pressure","measurement", "{{ value_json[0] | float}}")
    configure_sensor("Ps",mqtt_topic + "/details/pdps/state","HaierPi_Ps","MPa", "pressure","measurement", "{{ value_json[1] | float}}")
    configure_sensor("Compressor fact",mqtt_topic + "/details/compinfo/state","HaierPi_Compfact","Hz", "frequency","measurement", "{{ value_json[0] | float}}")
    configure_sensor("Compressor fset",mqtt_topic + "/details/compinfo/state","HaierPi_Compfset","Hz", "frequency","measurement", "{{ value_json[1] | float}}")
    configure_sensor("Compressor current",mqtt_topic + "/details/compinfo/state","HaierPi_Compcurrent","A", "current","measurement", "{{ value_json[2] | float}}")
    configure_sensor("Compressor voltage",mqtt_topic + "/details/compinfo/state","HaierPi_Compvoltage","V", "voltage","measurement", "{{ value_json[3] | float}}")
    configure_sensor("Compressor temperature",mqtt_topic + "/details/compinfo/state","HaierPi_Comptemperature","°C", "temperature","measurement", "{{ value_json[4] | float}}")
    configure_sensor("Td",mqtt_topic + "/details/tdts/state","HaierPi_Td","°C", "temperature","measurement","{{ value_json[0] | float}}")
    configure_sensor("Ts",mqtt_topic + "/details/tdts/state","HaierPi_Ts","°C", "temperature","measurement","{{ value_json[1] | float}}")
    configure_sensor("Daily CH energy usage", mqtt_topic +"/details/chkwhpd", "HaierPi_CH_daily_kWh", "kWh", "energy", "measurement", None)
    configure_sensor("Daily DHW energy usage", mqtt_topic +"/details/dhwkwhpd", "HaierPi_DHW_daily_kWh", "kWh", "energy", "measurement", None)

def threads_check():
    global dead
    while True:
        if not bg_thread.is_alive():
            if dead == 0:
                logging.error("Background thread DEAD")

                dead = 1
        elif not serial_thread.is_alive():
            if dead == 0:
                logging.error("Serial Thread DEAD")
                dead = 1
        elif use_mqtt == "1":
            if not mqtt_bg.is_alive():
                if dead == 0:
                    logging.error("MQTT thread DEAD")
                    dead = 1
        elif use_hpiapp == "1":
            if not hpiapp_bg.is_alive():
                if dead == 0:
                    logging.error("HPIAPP thread DEAD")
                    dead = 1
        if dead == 1:
            now = datetime.now()
            crash_date=now.strftime("%Y-%m-%d_%H-%M-%S")
            proc = subprocess.Popen(['journalctl', '-t', 'HaierPi', '-p','debug'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            f=open("/opt/haier/crashlog-"+crash_date+".log", "w")
            for line in iter(proc.stdout.readline, ''):
                f.write(line)
            f.close()
            dead = 2

        time.sleep(1)
        if event.is_set():
            break

# Start the Flask app in a separate thread
babel.init_app(app, locale_selector=get_locale)
#babel.init_app(app)

if __name__ == '__main__':
    loadconfig()
    app.jinja_env.globals['get_locale'] = 'pl'
    logging.warning(colored(welcome,"yellow", attrs=['bold']))
    logging.warning(colored(f"Service running: http://{ip_address}:{bindport} ", "green"))
    logging.warning(f"MQTT: {'enabled' if use_mqtt == '1' else 'disabled'}")
    logging.warning(f"Home Assistant MQTT Discovery: {'enabled' if ha_mqtt_discovery == '1' and use_mqtt == '1' else 'disabled'}")
    signal.signal(signal.SIGINT, handler)
    bg_thread = threading.Thread(target=run_background_function)
    bg_thread.start()
    services=[]
    if use_mqtt == '1':
        client = mqtt.Client(mqtt_topic)  # Create instance of client
        mqtt_bg = threading.Thread(target=connect_mqtt)
        mqtt_bg.start()
        services.append(client)
    if use_hpiapp == '1':
        hpiapp = mqtt.Client(hpi_topic)
        hpiapp_bg = threading.Thread(target=connect_haierpiapp)
        hpiapp_bg.start()
        services.append(hpiapp)

    serial_thread = threading.Thread(target=ReadPump)
    serial_thread.start()
    threadcheck = threading.Thread(target=threads_check)
    threadcheck.start()
    event = threading.Event()
    serve(app, host=bindaddr, port=bindport)
        #app.run(debug=False, host=bindaddr, port=bindport)#, ssl_context='adhoc')

