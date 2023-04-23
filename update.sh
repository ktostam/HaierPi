#!/bin/bash
systemctl stop haier
cd /opt/haier2/
git checkout
git pull
systemctl start haier