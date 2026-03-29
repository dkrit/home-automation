
cat << EOT | sudo tee /lib/systemd/system/invertercollector.service >/dev/null
[Unit]
Description=invertercollector

[Service]
User=rasbian
Group=rasbian
ExecStart=/home/rasbian/app/collector.sh
PIDFile=/tmp/invertercollector.pid
Restart=always

[Install]
WantedBy=multi-user.target
EOT

sudo systemctl enable invertercollector
sudo systemctl start invertercollector


cat << EOT | sudo tee /lib/systemd/system/inverterweb.service >/dev/null
[Unit]
Description=inverterweb

[Service]
User=rasbian
Group=rasbian
ExecStart=/home/rasbian/app/web.sh
PIDFile=/tmp/inverterweb.pid
Restart=always

[Install]
WantedBy=multi-user.target
EOT

sudo systemctl enable inverterweb
sudo systemctl start inverterweb

