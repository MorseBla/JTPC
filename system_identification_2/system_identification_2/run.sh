python3 build_workers.py

sudo python3 suite.py preflight --target-thor
sudo python3 suite.py profile --target-thor --allow-missing-temperature
sudo python3 suite.py alpha --target-thor --allow-missing-temperature
sudo python3 suite.py verification --target-thor --allow-missing-temperature
