import os.path
HIGH = 1
LOW = 0
OUT = "out"
IN = "in"

def setup(pin, action):
    if os.path.isdir("/sys/class/gpio/gpio"+str(pin)+"/"):
        cleanup(pin)
        print("WARNING: Channel already in use.")
    else:
        file='/sys/class/gpio/export'
        pinfile="/sys/class/gpio/gpio"+str(pin)+"/direction"
        file1 = open(file, 'w')
        file1.write(str(pin))
        file1.close()
        file2 = open(pinfile, 'w')
        file2.write(action)
        file2.close()

def output(pin, value):
    try:
        pinfile="/sys/class/gpio/gpio"+str(pin)+"/value"
        file1 = open(pinfile, 'w')
        file1.write(str(value))
        file1.close()
    except:
        return False

def input(pin):
    try:
        pinfile="/sys/class/gpio/gpio"+str(pin)+"/value"
        file1 = open(pinfile, 'r')
        result = file1.read(1)
        file1.close()
        return result
    except:
        return False


def cleanup(pin):
    if os.path.isdir("/sys/class/gpio/gpio"+str(pin)+"/"):
        file = '/sys/class/gpio/unexport'
        file1 = open(file, 'w')
        file1.write(str(pin))
        file1.close()
    else:
        print("no need to cleanup")
