HIGH = 1
LOW = 0
OUT = "out"
IN = "in"

def setup(pin, action):
    file='/sys/class/gpio/export'
    pinfile="/sys/class/gpio/gpio"+str(pin)+"/direction"
    file1 = open(file, 'w')
    file1.write(str(pin))
    file1.close()
    file2 = open(pinfile, 'w')
    file2.write(action)
    file2.close()

def output(pin, value):
    pinfile="/sys/class/gpio/gpio"+pin+"/value"
    file1 = open(pinfile, 'w')
    if value == "GPIO.HIGH":
        file1.write("1")
    elif value == "GPIO.LOG":
        file1.write("0")
    file1.close()

def cleanup(pin):
    file = '/sys/class/gpio/unexport'
    file1 = open(file, 'w')
    file1.write(str(pin))
    file1.close()