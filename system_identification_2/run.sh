sudo python3 system_identification_2/suite.py profile --target-thor --allow-missing-temperature
sudo python3 system_identification_2/suite.py alpha --target-thor --allow-missing-temperature
sudo python3 system_identification_2/suite.py validate --target-thor --allow-missing-temperature

sudo python3 periodic_validation.py plot --run results/20261101T075714Z_validate_26a3cdc9/ --model identification_model.json --plot-bin-seconds 10
