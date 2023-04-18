from flask import Flask, render_template, request, jsonify
from schedule import every, run_pending, cancel_job, clear
import threading
import time
import configparser
import serial
import PyHaier
import requests
import json
import paho.mqtt.client as mqtt
import signal
from termcolor import colored
from waitress import serve

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

ser = serial.Serial(port=modbusdev, baudrate = 9600, parity=serial.PARITY_EVEN,stopbits=serial.STOPBITS_ONE,bytesize=serial.EIGHTBITS,timeout=1)
app = Flask(__name__)

statusmap=["intemp","outtemp","settemp","hcurve","dhw","tank","humid","pch","pdhw","pcool"]
status=['N.A.','N.A.',settemp,'N.A.','N.A.','N.A.','N.A.','N.A.','N.A.','N.A.']
R101=[0,0,0,0,0,0]
R141=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
R201=[0]
R241=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]

def handler(signum, frame):
    print(colored("\rCtrl-C - Closing... please wait, this can take a while.", 'red', attrs=["bold"]))
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    ser.close()
    if use_mqtt == '1':
        client.publish(mqtt_topic+"/connected","off", qos=1, retain=True)
        client.disconnect()
    clear()
    exit(1)

def ReadPump(data):
    if(ser.isOpen() == False):
        print(colored("Closed seial connection.", 'red', attrs=["bold"]))
        exit(1)
    else:
        for x in range(6):
            rs=ser.read(1).hex()
            if rs == "11":
                rs=ser.read(2).hex()
                if data == "101":
                    if rs == "030c":
                        global R101
                        R101=[]
                        for ind in range(6):
                            rs=ser.read(2).hex()
                            R101.append(int(rs, 16))
                        return R101
                elif data == "141":
                    if rs == "0320":
                        global R141
                        R141=[]
                        for ind in range(16):
                            rs=ser.read(2).hex()
                            R141.append(int(rs, 16))
                        return R141
                elif data == "201":
                    if rs == "0302":
                        R201=[]
                        for ind in range(1):
                            rs=ser.read(2).hex()
                            R201.append(int(rs, 16))
                        return R201
                elif data == "241":
                    if rs == "032c":
                        R241=[]
                        for ind in range(22):
                            rs=ser.read(2).hex()
                            R241.append(int(rs, 16))
                        return R241

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

def modechange(mode,value):
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
    newframe=PyHaier.SetState(R101,newstate)

    msg = "Setting changed!"
    state = "success"
    status[statusmap.index(mode)]=value
    return jsonify(msg=msg, state=state)

def curvecalc():
    curve="123"
    return curve

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

#Reading parameters
def GetParameters():
    if(ser.isOpen() == False):
        print(colored("Closed seial connection.", 'red', attrs=["bold"]))
        exit(1)
    else:
        R101=ReadPump("101")
        R141=ReadPump("141")
        #R201=ReadPump("201")
        #R241=ReadPump("241")
        if not R101:
            R101=[0,0,0,0,0,0]
        if not R141:
            R141=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]

        tank=PyHaier.GetDHWCurTemp(R141)
        dhw=PyHaier.GetDHWTemp(R101)
        powerstate=PyHaier.GetState(R101)

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

        status[statusmap.index("tank")]=tank
        status[statusmap.index("dhw")]=dhw
        status[statusmap.index("intemp")] = GetInsideTemp(insidetemp)
        status[statusmap.index("outtemp")] = GetOutsideTemp(outsidetemp)
        status[statusmap.index("humid")] = GetHumidity(humidity)
        if use_mqtt == '1':
            client.publish(mqtt_topic,str(status))

def background_function():
    print("Background function running!")

# Flask route
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/settings')
def settings():
    return render_template('settings.html')

@app.route('/modechange', methods=['POST'])
def change_mode_route():
    mode = request.form['mode']
    value = request.form['value']
    information = modechange(mode, value)
    return information

@app.route('/getdata', methods=['GET'])
def getdata_route():
    output = getdata()
    return output

# Function to run the background function using a scheduler
def run_background_function():
    job=every(int(timeout)).seconds.do(GetParameters)
    while True:
        if(ser.isOpen() == False):
            print(colored("Closed seial connection.", 'red', attrs=["bold"]))
            exit(1)
        else: 
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
    serve(app, host=bindaddr, port=bindport)
    #app.run(debug=False, host=bindaddr, port=bindport)