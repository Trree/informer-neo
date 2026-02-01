import sys
import os
import logging
from dotenv import load_dotenv
from pathlib import Path

# Lets set the logging level
logging.getLogger().setLevel(logging.INFO)

# -----------------
# Load the ENV file
# -----------------
env_file = 'informer.env' if os.path.isfile('informer.env') else '../informer.env'
logging.info(f'env_file: {env_file}')
dotenv_path = Path(env_file)
load_dotenv(dotenv_path=dotenv_path)

from informer import TGInformer


# ===========
# Quick setup
# ===========

#   virtualenv venv
#   source venv/bin/activate
#   pip install -r requirements.txt
#   python3 bot.py

# Read more: https://github.com/paulpierre/informer/

if __name__ == '__main__':
    # TGInformer will read all parameters from environment variables
    # No need to pass them explicitly since they have default values
    informer = TGInformer()
