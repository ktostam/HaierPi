# HaierPi

[![AGPL License](https://img.shields.io/badge/license-AGPL-blue.svg)](http://www.gnu.org/licenses/agpl-3.0)

This project allows you to control HAIER heat pumps. 
## Tested with
1. AU082FYCRA(HW)
2. AU162FYCRA(HW)

All tests were performed on a pump with an additional ATW-a01 unit

However, it should work with all pumps that feature the YR-e27 remote control

If you have any question you can find me on discord:

[<img src="https://discordapp.com/api/guilds/1096167750612828210/widget.png?style=banner2" alt="Discord Banner 2"/>
](https://discord.gg/dVXmAfWt3P)

## Patrons
- Radek Michalowski

## Contributors
- @kocur on discord channel
- @Radek on discord channel

## Donation
If you like My work and want to support my work, you can:

[<img width="150px" src="https://d3mi06r82nxl9g.cloudfront.net/files/logotypes/svg/patronite-SVG-02-white.svg">](https://patronite.pl/haierpi)

[<img width="150px" src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png">](https://www.buymeacoffee.com/jacekbrzozZ)

Or if you from Poland:

[<img width="150px" src="https://buycoffee.to/btn/buycoffeeto-btn-primary.svg">](https://buycoffee.to/jacekbrzozz)

## HARDWARE

## PCB
PCB layout is designed for both RaspberryPi zeroW and NanoPi neo 1.4.

![Front](https://github.com/ktostam/HaierPi/blob/master/images/haierpi-front.png?raw=true)

![Front](https://github.com/ktostam/HaierPi/blob/master/images/haierpi-back.png?raw=true)

### PCB 1.1
The revised version of the PCB (1.1) no longer has mislabeling. In addition, one of the leds and the button is now also connected to the RPi.

In the future, HaierPi will support only NanoPi

### Component List

| Symbol        | Value            | Footprint        |
|---------------|------------------|------------------|
| J1            | ADC-002          | ADC-002          |
| H3-H4         | JST XH 3         | JST-XH-TH-3-2.5  |
| POMPA,YR-E27  | JST XH 4         | JST-XH-TH-4-2.5  |
| CON1-CON3     | DG308-2.54/2     |                  |
| R1-R4         | 1K               | SMD 0805         |
| R5-R8,R10-R12 | 4.7K             | SMD 0805         |
| R9            | 120              | SMD 0805         |
| R13-R15       | 0                | SMD 0805         |
| R16-R17       | 330              | SMD 0805         |
| C1            | 104              | SMD 0805         |
| LED1          | RED              | SMD 0805         |
| LED2          | GREEN            | SMD 0805         |
| D1-D4         | 1N4007W          | SOD-123          |
| D5-D7         | SMAJ12CA         | DO214AC          |
| REL1          | N4078-2C-5V-0.2W | N4078-2C-5V-0.2W |
| REL2-REL4     | HFD23-005-1ZS    | HFD23-005-1ZS    |
| U1            | MAX3485          | SOP-8            |

### ERRATA
In the first batch of PCB's was error
PCB descriptions of R1 and R2 are swapped places, so if you have that PCB,
you need to solder 1K resistor on R6 and 4.7 on R1

### Disclaimer
- R9 is RS485 EOL resistor. For this application don't solder it.
- Resistor R14-R15 is for choosing what type to board you want to connect (Raspberrypi/NanoPi Neo). For NanoPi, 
solder 0 Ohm resistor for powering NanoPi via GPIO. `If you connect Raspberry Pi don't solder it`, because powering RPi 
from GPIO bypasses builtin protections. I will be work but its not safe. If you connecting Raspberry Pi zero W, connect
`J2`(GND) to `PP6` pad, and `J3`(+5V) to `PP1` pad. 

### Raspberry Pi
if you want to use the script on the raspberry pi, you need to add the following settings to `config.txt`:

```shell
dtoverlay=w1-gpio,gpiopin=4
dtoverlay=pi3-disable-bt
enable_uart=1
```
Be aware that this settings will disable bluetooth. but we need use UART0

### Nano Pi neo 1.4
Script is also tested on NanoPi neo 1.4. For now no change is required, but in future, when support for hardware
temperature sensor will be added, we need to remap some GPIO pins. Further information will be added later.

### Other platform
script needs a relay to control the data flow in order to function properly, so best choice is some sort of SBC.
At the moment there are no plans to add support for other SBCs, but maybe in future I will add support for relays controlled by Home Assistant, 
so script may running on any platform, and only need a RS485 connection.

## Wiki
Now the documentation is on the wiki [wiki](https://wiki.haos.it)

## Translation
- en
- pl
### if you want to help create a translation into another language write me an email or on the discord channel

## Version
### 1.37
- Add charts with some parameters
- DHW without limit function run in turbo mode
- Add estimated daily energy consumption, separate for central heating and domestic hot water

### 1.35
- Add MQTT Discovery (by Radek)
- Add more option for heatingcurve
- Add Anti ON-OFF function
- Add DHW without limit function
- Add Parameters page
- Add Temperature Charts
- Minor fixes

### 1.32
- Add parameters
- Add scheduler for CH and DHW
- Add translation to polish
- Now changes to settings do not require a restart of the service
- New update script, from now all new update dont need to manualy add option in config.ini.
- Minor fixes

### 1.31
- Add function for automatic/manual control of frequency limit relay
- Add function for automatic/manual control of mode quiet/eco/turbo
- IMPORTANT: new option added in config.ini. If you're updating
  from previous version you need to add options: `log_leve = ERROR` in  `[DEFAULT]` block in `config.ini`
  `flimit = manual`, `flimit_temp = 10`, `presetautochange = manual`,`presetquiet = 10`,`presetturbo = -10` in `[SETTINGS]` block in `config.ini`
- minor fixes
### 1.30
- Add possibility to change heating curve parameters via settings page.
- IMPORTANT: new option added in config.ini. If you're updating
  from previous version you need to add option `hcslope = 0.7`, `hcpshift = 1` and `hcamp = 1` in `[SETTINGS]` block in `config.ini`
- Add chart with heating curve visualisation.
- minor fixes

### 1.26
- IMPORTANT: new option added in config.ini. If you're updating
  from previous version you need to add option `firstrun = 0` in `[DEFAULT]` block in `config.ini`
- Setting page is kinda ready. (unfortunetly you need to manualy restart HaierPi service after saving change for now)
- Added new service for display HaierPi logs via web, for better debugging. Now you don't need to login via ssh
- Now script can talk with home assistant via MQTT (for now there is no mqtt autodiscovery, so you need to add yaml configuration manualy).
- Updates only send via mqtt if something is changes, not as before - everything every 10 seconds
- TODO: add option somewhere to restart HaierPi service. (e.g. after config.ini changed via web)
- Minor fixes

### 1.18
- Add ds18b20 sensor support as outside temp sensor.
- Fixed error handling that could cause sysexit.
- Adding new update mechanism
 need to add new option in `config.ini`:
```shell
    release=master
```
- Minor fixes
### 1.1
In this release I change library to control GPIO, Iam not using RPi.GPIO anymore, there is some issue with RPi.GPIO replacement for Nano Pi, so I decided to control GPIO via system /sys/class/gpio/. This is independent from used SBC,

in `config.ini` there is new configuration for PIN:
```shell
[GPIO]
modbus=17 #17 for raspberrypi, 0 for nanopi neo
freqlimit=27 #27 for raspberrypi, 2 for nanopi neo
heatdemand=22 #22 for raspberrypi, 3 for nanopi neo
cooldemand=10 #10 for raspberrypi, 64 for nanopi neo
```

### 1.0

First release. for now, the following features are available:

- Show pump parameters
- Set DHW temperature
- Set Central Heating Temperature 
- Heating water temperature is calculated according to the heating curve
- Online update

#### disclaimer:
In this release inside and outside temperature must be provided by Home Assistant sensors.
For future release hardware sensor will be supported (ds18b20 for outside and DHT22 for inside temperature).

In this release, MQTT support is not finished

## LICENSE
 GNU Affero General Public License v3 [©Jacek Brzozowski](https://github.com/ktostam/HaierPi)

In this project I'am using:
[open-meteo](https://open-meteo.com/) - CC BY 4.0

[jquery-schedule](https://github.com/Yehzuna/jquery-schedule) - MIT License

[sweetalert2](https://github.com/sweetalert2/sweetalert2) - MIT License

[bootstrap](https://github.com/twbs/bootstrap) - MIT License

[jquery](https://github.com/jquery/jquery) - MIT License
