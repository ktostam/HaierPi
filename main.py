from flask_simplelogin import SimpleLogin,is_logged_in,login_required, get_username
from werkzeug.security import check_password_hash, generate_password_hash
from schedule import every, run_pending, get_jobs, clear, cancel_job
from flask import Flask, render_template, request, jsonify
from pymodbus.client.sync import ModbusSerialClient
import paho.mqtt.client as mqtt
from termcolor import colored
from waitress import serve
import RPi.GPIO as GPIO
import configparser
import subprocess
import threading
import requests
import PyHaier
import serial
import signal
import json
import time

welcome="┌────────────────────────────────────────┐\n│              "+colored("!!!Warning!!!", "red", attrs=['bold','blink'])+colored("             │\n│      This script is experimental       │\n│                                        │\n│ Products are provided strictly \"as-is\" │\n│ without any other warranty or guaranty │\n│              of any kind.              │\n└────────────────────────────────────────┘\n","yellow", attrs=['bold'])
config = configparser.ConfigParser()
config.read('config.ini')
timeout = config['DEFAULT']['heizfreq']
bindaddr = config['DEFAULT']['bindaddress']
bindport = config['DEFAULT']['bindport']
modbusdev = config['DEFAULT']['modbusdev']
settemp = config['SETTINGS']['settemp']
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
modbus =  ModbusSerialClient(method = "rtu", port=modbusdev,stopbits=1, bytesize=8, parity='E', baudrate=9600)
ser = serial.Serial(port=modbusdev, baudrate = 9600, parity=serial.PARITY_EVEN,stopbits=serial.STOPBITS_ONE,bytesize=serial.EIGHTBITS,timeout=1)
app = Flask(__name__)
app.config['SECRET_KEY'] = '2bb80d537b1da3e38bd30361aa855686bde0eacd7162fef6a25fe97bf527a25b'

GPIO.setmode(GPIO.BCM)
GPIO.setup(6, GPIO.OUT) #modbus
GPIO.setup(13, GPIO.OUT) #freq limit
GPIO.setup(19, GPIO.OUT) # heat demand
GPIO.setup(26, GPIO.OUT) # cool demand

statusmap=["intemp","outtemp","settemp","hcurve","dhw","tank","humid","pch","pdhw","pcool", "theme"]
status=['N.A.','N.A.',settemp,'N.A.','N.A.','N.A.','N.A.','N.A.','N.A.','N.A.', 'dark']
R101=[0,0,0,0,0,0]
R141=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
R201=[0]
R241=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]

def handler(signum, frame):
    print(colored("\rCtrl-C - Closing... please wait, this can take a while.", 'red', attrs=["bold"]))
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    ser.close()
    GPIO.clenaup()
    if use_mqtt == '1':
        client.publish(mqtt_topic+"/connected","off", qos=1, retain=True)
        client.disconnect()
    clear()
    exit(1)

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
            GPIO.output(6, GPIO.HIGH)
        elif value == "0":
            GPIO.output(6, GPIO.LOW)
    if control == "heatdemand":
        if value == "1":
            GPIO.output(19, GPIO.HIGH)
        if value == "0":
            GPIO.output(19, GPIO.LOW)
    if control == "cooldemand":
        if value == "1":
            GPIO.output(26, GPIO.HIGH)
        if value == "0":
            GPIO.output(26, GPIO.LOW)
    if control == "freqlimit":
        if value == "1":
            GPIO.output(13, GPIO.HIGH)
        if value == "0":
            GPIO.output(13, GPIO.LOW)

def WritePump():
    global newframe
    global writed
    if newframe:
        print(newframe)
        newframelen=len(newframe)
        if newframelen == 6:
            print("101")
            gpiocontrol("modbus","1")
            time.sleep(1)
            modbus.connect()
            modbusresult=modbus.write_registers(101, newframe, unit=17)
            modbus.close()
            gpiocontrol("modbus","0")
            print(modbusresult)
            writed="1"
            # if hasattr(modbusresult, 'fcode'):
            #     if modbusresult.fcode < 0x80:
            #         print(modbusresult.fcode)
            #         writed="1"
            #     else:
            #         writed="2"
        elif newframelen == 16:
            print("141")
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
            print(colored("Closed seial connection.", 'red', attrs=["bold"]))
            break
        if newframe:
            WritePump()
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

def on_connect(client, userdata, flags, rc):
    print(colored("MQTT - Conected", "green", attrs=['bold']))
    # Print result of connection attempt 
    client.subscribe(mqtt_topic)
    client.publish(mqtt_topic+"/connected","on", qos=1, retain=True)
    # Subscribe to the topic “digitest/test1”, receive any messages  published on it

def on_disconnect(client, userdata, rc):  # The callback for when 
    #the client connects to the broker 
    print(colored("Disconected from MQTT with code: {0}".format(str(rc)), 'red', attrs=['bold']))
    # Print result of connection attempt 

def on_message(client, userdata, msg):  # The callback for when a PUBLISH 
    #message is received from the server. 
    #print("Message received-> " + msg.topic + " " + str(msg.payload))  # Print a received msg
    if msg.topic == mqtt_topic+"/power/set":
        print("New power state from mqtt:")
        client.publish(mqtt_topic+"/power/state","new_state_here", qos=1, retain=True)
    elif msg.topic == mqtt_topic+"preset_mode/set":
        print("New preset mode")
        client.publish(mqtt_topic+"/preset_mode/state","new_state_here", qos=1, retain=True)
    elif msg.topic == mqtt_topic+"mode/set":
        print("New mode")
        client.publish(mqtt_topic+"/mode/state","new_state_here", qos=1, retain=True)
    elif msg.topic == mqtt_topic+"/temperature/set":
        print("New temperature")
        client.publish(mqtt_topic+"/temperature/state","new_state_here", qos=1, retain=True)

def tempchange(which, value, curve):
    global newframe
    global writed
    if which == "heat":
        if curve == "1":
            print("Central heating: "+value)
            print(R101)
            newframe = PyHaier.SetCHTemp(R101, float(value))
            msgt="Central heating: "
        elif curve == "0":
            status[statusmap.index("settemp")]=float(value)
    elif which == "dhw":
        print(R101)
        print("Domestic Hot Water: "+value)
        newframe = PyHaier.SetDHWTemp(R101, int(value))
        msgt="Domestic Hot Water "

    for i in range(50):
        print(writed)
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

    return jsonify(msg=msg, state=state)

def statechange(mode,value):
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
    print(writed)
    print(R101)
    print(newstate)
    newframe=PyHaier.SetState(R101,newstate)
    for i in range(50):
        print(writed)
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
    return jsonify(msg=msg, state=state)

def curvecalc():
    insidetemp=float(status[statusmap.index("intemp")])
    outsidetemp=float(status[statusmap.index("outtemp")])
    settemp=float(status[statusmap.index("settemp")])
    t1=(outsidetemp/(320-(outsidetemp*4)))
    t2=pow(settemp,t1)
    slope=0.65
    ps=3
    amp=3
    heatcurve = round(((0.55*slope*t2)*(((-outsidetemp+20)*2)+settemp+ps)+((settemp-insidetemp)*amp))*2)/2
    status[statusmap.index("hcurve")]=heatcurve
    if 25.0 < heatcurve < 55.0:
        gpiocontrol("heatdemand", "1")
        tempchange(heat, heatcurve, "1")
    else:
        gpiocontrol("heatdemand", "0")

def updatecheck():
    gitver=subprocess.run(['git', 'ls-remote', 'origin', '-h', 'refs/heads/master'], stdout=subprocess.PIPE).stdout.decode('utf-8')[0:40]
    localver=subprocess.run(['cat', '.git/refs/remotes/origin/master'], stdout=subprocess.PIPE).stdout.decode('utf-8')[0:40]
    if localver != gitver:
	    msg="Availible"
    else:
	    msg="Not Availible"
    return jsonify(update=msg)

def installupdate():
    subprocess.Popen("systemctl restart haierupdate.service", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return jsonify(updated="OK")


def getdata():
    intemp=status[statusmap.index("intemp")]
    outtemp=status[statusmap.index("outtemp")]
    stemp=status[statusmap.index("settemp")]
    hcurve=status[statusmap.index("hcurve")]
    dhw=status[statusmap.index("dhw")]
    tank=status[statusmap.index("tank")]
    humid=status[statusmap.index("humid")]
    pch=status[statusmap.index("pch")]
    pdhw=status[statusmap.index("pdhw")]
    pcool=status[statusmap.index("pcool")]
    return jsonify(intemp=intemp, outtemp=outtemp, setpoint=stemp, hcurve=hcurve,dhw=dhw,tank=tank,humid=humid,pch=pch,pdhw=pdhw,pcool=pcool)

def GetInsideTemp(param):
    if param == "buildin":
        # function for getting temp from DHT22 connected to RaspberryPi GPIO. for now return static 22
        return "22"
    elif param == "ha":
        # connect to Home Assistant API and get status of inside temperature entity
        url="http://"+config['HOMEASSISTANT']['HAADDR']+":"+config['HOMEASSISTANT']['HAPORT']+"/api/states/"+config['HOMEASSISTANT']['insidesensor']
        headers = requests.structures.CaseInsensitiveDict()
        headers["Accept"] = "application/json"
        headers["Authorization"] = "Bearer "+config['HOMEASSISTANT']['KEY']
        try:
            resp=requests.get(url, headers=headers)
        except requests.exceptions.RequestException as e:
            raise SystemExit(e)
        json_str = json.dumps(resp.json())
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
    if param == "buildin":
        # function for getting temp from DS18b20 connected to RaspberryPi i2c. for now return static 22
        return "22"
    elif param == "ha":
        # connect to Home Assistant API and get status of outside temperature entity
        url="http://"+config['HOMEASSISTANT']['HAADDR']+":"+config['HOMEASSISTANT']['HAPORT']+"/api/states/"+config['HOMEASSISTANT']['outsidesensor']
        headers = requests.structures.CaseInsensitiveDict()
        headers["Accept"] = "application/json"
        headers["Authorization"] = "Bearer "+config['HOMEASSISTANT']['KEY']
        resp=requests.get(url, headers=headers)
        json_str = json.dumps(resp.json())
        response = json.loads(json_str)['state']
        return response
    else:
        return -1

def GetHumidity(param):
    if param == "buildin":
        # function for getting humidity from DHT22 connected to RaspberryPi GPIO. for now return static 22
        return "22"
    elif param == "ha":
        # connect to Home Assistant API and get status of inside humidity entity
        url="http://"+config['HOMEASSISTANT']['HAADDR']+":"+config['HOMEASSISTANT']['HAPORT']+"/api/states/"+config['HOMEASSISTANT']['humiditysensor']
        headers = requests.structures.CaseInsensitiveDict()
        headers["Accept"] = "application/json"
        headers["Authorization"] = "Bearer "+config['HOMEASSISTANT']['KEY']
        resp=requests.get(url, headers=headers)
        json_str = json.dumps(resp.json())
        response = json.loads(json_str)['state']
        return response
    else:
        return -1

def settheme(theme):
    print(theme)
    status[statusmap.index("theme")]=theme
    return theme

#Reading parameters
def GetParameters():
    if len(R141) == 16:
        tank=PyHaier.GetDHWCurTemp(R141)
        status[statusmap.index("tank")] = tank
    if len(R101) == 6:
        dhw=PyHaier.GetDHWTemp(R101)
        powerstate=PyHaier.GetState(R101)
        status[statusmap.index("dhw")] = dhw
        if 'Heat' in powerstate:
            status[statusmap.index("pch")] = "on"
        else:
            status[statusmap.index("pch")] = "off"
        if 'Cool' in powerstate:
            status[statusmap.index("pcool")] = "on"
        else:
            status[statusmap.index("pcool")] = "off"

        if 'Tank' in powerstate:
            status[statusmap.index("pdhw")] = "on"
        else:
            status[statusmap.index("pdhw")] = "off"
    status[statusmap.index("intemp")] = GetInsideTemp(insidetemp)
    status[statusmap.index("outtemp")] = GetOutsideTemp(outsidetemp)
    status[statusmap.index("humid")] = GetHumidity(humidity)
    curvecalc()
    if use_mqtt == '1':
        client.publish(mqtt_topic,str(status))

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
    return jsonify(msg="Password changed")

def background_function():
    print("Background function running!")

# Flask route
@app.route('/')
@login_required
def home():
    theme=status[statusmap.index("theme")]
    return render_template('index.html', theme=theme)

@app.route('/theme', methods=['POST'])
def theme_route():
    theme = request.form['theme']
    settheme(theme)
    return theme


@app.route('/settings')
@login_required
def settings():
    theme = status[statusmap.index("theme")]
    return render_template('settings.html', theme=theme)

@app.route('/statechange', methods=['POST'])
@login_required
def change_state_route():
    mode = request.form['mode']
    value = request.form['value']
    information = statechange(mode, value)
    return information

@app.route('/tempchange', methods=['POST'])
@login_required
def change_temp_route():
    which = request.form['which']
    value = request.form['value']
    response = tempchange(which, value, "0")
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

@app.route('/changepass', methods=['POST'])
@login_required
def change_pass_route():
    user = request.form['user']
    password = request.form['password']
    response = create_user(username=user, password=password)
    return response

@app.route('/getdata', methods=['GET'])
@login_required
def getdata_route():
    output = getdata()
    return output

# Function to run the background function using a scheduler
def run_background_function():
    job=every(int(timeout)).seconds.do(GetParameters)
    while True:
        run_pending()
        time.sleep(1)

def connect_mqtt():
    client.on_connect = on_connect  # Define callback function for successful connection
    client.on_message = on_message  # Define callback function for receipt of a message
    client.on_disconnect = on_disconnect
    # client.connect("m2m.eclipse.org", 1883, 60)  # Connect to (broker, port, keepalive-time)
    client.will_set(mqtt_topic+"/connected","off",qos=1,retain=True)
    client.username_pw_set(mqtt_username, mqtt_password)
    try:
        client.connect(mqtt_broker_addr, int(mqtt_broker_port))
    except:
        print(colored("MQTT connection error.","red", attrs=['bold']))
        exit(1)
    client.loop_forever()  # Start networking daemon

# Start the Flask app in a separate thread
if __name__ == '__main__':
    print(colored(welcome,"yellow", attrs=['bold']))
    print(colored("Service running: http://127.0.0.1:4000 ", "green"))
    signal.signal(signal.SIGINT, handler)
    bg_thread = threading.Thread(target=run_background_function)
    bg_thread.start()
    if use_mqtt == '1':
        client = mqtt.Client()  # Create instance of client with client ID “digi_mqtt_test”
        mqtt_bg = threading.Thread(target=connect_mqtt)
        mqtt_bg.start()
    serial_thread = threading.Thread(target=ReadPump)
    serial_thread.start()
    serve(app, host=bindaddr, port=bindport)
    #app.run(debug=False, host=bindaddr, port=bindport)#, ssl_context='adhoc')