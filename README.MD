# HaierPi

[![AGPL License](https://img.shields.io/badge/license-AGPL-blue.svg)](http://www.gnu.org/licenses/agpl-3.0)

This project allows basic control of HAIER heat pumps.
## Tested with
1. AU082FYCRA(HW)
2. AU162FYCRA(HW)

However, it should work with all pumps that feature the YR-e27 remote control
## Donation
If you like My work and want to support me, you can:

[<img width="150px" src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png">](https://www.buymeacoffee.com/jacekbrzozZ)

Or if you from Poland:

[<img width="150px" src="https://buycoffee.to/btn/buycoffeeto-btn-primary.svg">](https://buycoffee.to/jacekbrzozz)

## HARDWARE

## PCB
PCB layout is designed for both RaspberryPi zeroW and NanoPi neo 1.4.

![Front](https://github.com/ktostam/HaierPi/blob/master/images/haierpi-front.png?raw=true)

![Front](https://github.com/ktostam/HaierPi/blob/master/images/haierpi-back.png?raw=true)
## INSTALL

#### Download

```shell
$ git clone https://github.com/ktostam/HaierPi.git
```

#### Edit config file

Edit the config.ini file with your favorite editor:
```shell
$ vim config.ini
```

#### use install script
run install script with root privileges

installation script by default installs in **/opt/haier**
```shell
$ sudo install.sh
```
installation script creates systemd services and asks if you want the service to start at system startup.

if you want manualy start/stop service:

for stop service:
```shell
$ sudo systemctl stop haier.service
```
for start service:
```shell
$ sudo systemctl start haier.service
```
### After install
By default sript listen on all interfaces on port 4000, you can change it in **config.ini** 

default login and password for web interfaces is: ***admin/admin***
### Screenshot
![Screenshot](https://github.com/ktostam/HaierPi/blob/master/images/screenshot.gif?raw=true)
## Version

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

[sweetalert2](https://github.com/sweetalert2/sweetalert2) - MIT License

[bootstrap](https://github.com/twbs/bootstrap) - MIT License

[jquery](https://github.com/jquery/jquery) - MIT License