mkdir -p $HOME/seagate
cp -r /opt/seagate/cortx/ $HOME/seagate/
sudo rm -rf /opt/seagate/cortx/hare
sudo rm -rf /usr/bin/hctl
sudo ln -s  $HOME/seagate/cortx/hare/bin/hctl /usr/bin/hctl
HOMED="\/home\/"
HOMED+=$USER
echo $HOMED
sed -i "s/\/opt/$HOMED/" $HOME/seagate/cortx/hare/bin/m0ping  \
                         |  tee -a $HOME/seagate/cortx/hare/bin/m0ping > /dev/null
HOMEDR="home\/"
HOMEDR+=$USER
sed -i "s|opt|$HOMEDR|" $HOME/seagate/cortx/hare/share/consul/consul-client-conf.json.in
sed -i "s|opt|$HOMEDR|" $HOME/seagate/cortx/hare/share/consul/consul-server-conf.json.in
