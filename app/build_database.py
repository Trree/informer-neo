
import csv
import sys
import os
import logging
from dotenv import load_dotenv
from pathlib import Path
import sqlalchemy as db
from datetime import datetime
from sqlalchemy.orm import sessionmaker
from models import Account, Channel, ChatUser, Keyword, Message, Monitor, Notification, Base
logging.getLogger().setLevel(logging.INFO)

# -----------------
# Load the ENV file
# -----------------
dotenv_path = Path('informer.env')
load_dotenv(dotenv_path=dotenv_path)

Session = None
session = None
SERVER_MODE = None
engine = None

"""
This script will build our your database for you
"""

def init_db():
    global session, SERVER_MODE, engine
    logging.info(f'{sys._getframe().f_code.co_name}: Initializing the database')

    try:
        # Create all tables using Base metadata (more efficient and handles existing tables gracefully)
        # checkfirst=True (default) ensures tables are only created if they don't exist
        Base.metadata.create_all(engine, checkfirst=True)
        logging.info(f'{sys._getframe().f_code.co_name}: Database tables created successfully')
    except Exception as e:
        logging.error(f'{sys._getframe().f_code.co_name}: Error creating database tables: {e}')
        raise
    finally:
        if session:
            session.close()


"""
    Lets setup the channels to monitor in the database
"""
def init_data():

    global session, SERVER_MODE, engine
    session = Session()
    init_add_account()
    init_add_channels()
    init_add_keywords()
    init_add_monitors()
    session.close()

def init_add_account():

    global session, SERVER_MODE, engine

    logging.info(f'{sys._getframe().f_code.co_name}: Adding bot account')

    account_id = os.environ['TELEGRAM_ACCOUNT_ID']
    account_phone = os.environ['TELEGRAM_ACCOUNT_PHONE_NUMBER']

    # Check if account already exists
    existing_account = session.query(Account).filter_by(account_id=account_id).first()
    if existing_account:
        logging.info(f'{sys._getframe().f_code.co_name}: Account {account_id} already exists, skipping')
        return

    BOT_ACCOUNTS = [

        Account(
            account_id=account_id,
            account_api_id=os.environ['TELEGRAM_API_APP_ID'],
            account_api_hash=os.environ['TELEGRAM_API_HASH'],
            account_is_bot=False,
            account_is_verified=False,
            account_is_restricted=False,
            account_first_name=os.environ['TELEGRAM_ACCOUNT_FIRST_NAME'],
            account_last_name=os.environ['TELEGRAM_ACCOUNT_LAST_NAME'],
            account_user_name=os.environ['TELEGRAM_ACCOUNT_USER_NAME'],
            account_phone=account_phone,  # Enter your burner phone number here
            account_is_enabled=True,
            account_tlogin=datetime.utcnow(),
            account_tcreate=datetime.utcnow(),
            account_tmodified=datetime.utcnow()),

    ]

    for account in BOT_ACCOUNTS:
        session.add(account)

    try:
        session.commit()
        logging.info(f'{sys._getframe().f_code.co_name}: Successfully added account {account_id}')
    except IntegrityError as e:
        session.rollback()
        logging.error(f'{sys._getframe().f_code.co_name}: Database integrity error: {e}')
        raise

def init_add_channels():
    global session, SERVER_MODE, engine

    # Lets get the first account
    account = session.query(Account).first()

    CHANNELS = [
        {
            'channel_name': 'Informer monitoring',
            'channel_id': os.environ['TELEGRAM_NOTIFICATIONS_CHANNEL_ID'],  # Enter your own Telegram channel ID for monitoring here
            'channel_url': os.environ['TELEGRAM_NOTIFICATIONS_CHANNEL_URL'],
            'channel_is_private': False if os.environ['TELEGRAM_NOTIFICATIONS_CHANNEL_IS_PRIVATE']=='0' else True
        },

    ]

    # Lets import the CSV with the channel list
    with open(os.environ['TELEGRAM_CHANNEL_MONITOR_LIST']) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        line_count = 0
        for row in csv_reader:
            if line_count != 0:
                print(f'Adding channel {row[0]} => {row[1]}')
                CHANNELS.append({
                    'channel_name': row[0],
                     'channel_url': row[1]
                                 })
            line_count += 1


    logging.info(f'Inserting {line_count} channels to database')

    channels_added = 0
    channels_skipped = 0

    for channel in CHANNELS:
        channel_url = channel['channel_url'] if 'channel_url' in channel else None
        channel_id = channel['channel_id'] if 'channel_id' in channel else None
        channel_is_group = channel['channel_is_group'] if 'channel_is_group' in channel else False
        channel_is_private = channel['channel_is_private'] if 'channel_is_private' in channel else False

        # Check if channel already exists (by URL or channel_id)
        existing_channel = None
        if channel_id:
            existing_channel = session.query(Channel).filter_by(channel_id=channel_id).first()
        elif channel_url:
            existing_channel = session.query(Channel).filter_by(channel_url=channel_url).first()

        if existing_channel:
            logging.info(f"{sys._getframe().f_code.co_name}: Channel {channel['channel_name']} already exists, skipping")
            channels_skipped += 1
            continue

        logging.info(f"{sys._getframe().f_code.co_name}: Adding channel {channel['channel_name']} to database")

        session.add(Channel(
            channel_name=channel['channel_name'],
            channel_url=channel_url,
            channel_id=channel_id,
            account_id=account.account_id,
            channel_tcreate=datetime.utcnow(),
            channel_is_group=channel_is_group,
            channel_is_private=channel_is_private
        ))
        channels_added += 1

    try:
        session.commit()
        logging.info(f"{sys._getframe().f_code.co_name}: Successfully added {channels_added} channels, skipped {channels_skipped} duplicates")
    except IntegrityError as e:
        session.rollback()
        logging.error(f"{sys._getframe().f_code.co_name}: Database integrity error: {e}")
        raise

# ==============================
# The keywords we want to spy on
# ==============================
def init_add_keywords():
    global session, SERVER_MODE, engine
    KEYWORDS = [
        {
            'keyword_description': 'Binance',
            'keyword_regex': '(binance|bnb)'
        },
        {
            'keyword_description': 'Huobi',
            'keyword_regex': '(huobi)'
        },
        {
            'keyword_description': 'Bittrex',
            'keyword_regex': '(bittrex)'
        },
        {
            'keyword_description': 'Bitfinex',
            'keyword_regex': '(bitfinex)'
        },
        {
            'keyword_description': 'Coinbase',
            'keyword_regex': '(coinbase)'
        },
        {
            'keyword_description': 'Kraken',
            'keyword_regex': '(kraken)'
        },
        {
            'keyword_description': 'Poloniex',
            'keyword_regex': '(poloniex)'
        },

    ]

    keywords_added = 0
    keywords_skipped = 0

    for keyword in KEYWORDS:
        # Check if keyword already exists (by regex, which is unique)
        existing_keyword = session.query(Keyword).filter_by(keyword_regex=keyword['keyword_regex']).first()

        if existing_keyword:
            logging.info(f"{sys._getframe().f_code.co_name}: Keyword {keyword['keyword_description']} already exists, skipping")
            keywords_skipped += 1
            continue

        logging.info(f"{sys._getframe().f_code.co_name}: Adding keyword {keyword['keyword_description']} to the database")

        session.add(Keyword(
            keyword_description=keyword['keyword_description'],
            keyword_regex=keyword['keyword_regex'],
            keyword_tmodified=datetime.utcnow(),
            keyword_tcreate=datetime.utcnow()
        ))
        keywords_added += 1

    try:
        session.commit()
        logging.info(f"{sys._getframe().f_code.co_name}: Successfully added {keywords_added} keywords, skipped {keywords_skipped} duplicates")
    except IntegrityError as e:
        session.rollback()
        logging.error(f"{sys._getframe().f_code.co_name}: Database integrity error: {e}")
        raise


# ======================================
# Lets add the channels we want to watch
# ======================================
def init_add_monitors():
    global session, SERVER_MODE, engine
    # Lets assign them all
    accounts = session.query(Account).all()
    channels = session.query(Channel).all()
    account_index = 0
    channel_count = 0

    monitors_added = 0
    monitors_skipped = 0

    for channel in channels:
        if account_index < len(accounts):  # Fixed: should be < not in
            account = accounts[account_index]

            # Check if monitor already exists
            existing_monitor = session.query(Monitor).filter_by(
                channel_id=channel.id,
                account_id=account.account_id
            ).first()

            if existing_monitor:
                logging.info(f'{sys._getframe().f_code.co_name}: Monitor for channel {channel.channel_name} with account_id {account.account_id} already exists, skipping')
                monitors_skipped += 1
                continue

            logging.info(f'{sys._getframe().f_code.co_name}: Adding monitoring to channel {channel.channel_name} with account_id {account.account_id} to the database')
            session.add(Monitor(
                channel_id=channel.id,
                account_id=account.account_id,
                monitor_tcreate=datetime.utcnow(),
                monitor_tmodified=datetime.utcnow()
            ))
            monitors_added += 1
            channel_count += 1
            if channel_count > 500:
                account_index += 1
                channel_count = 0

    try:
        session.commit()
        logging.info(f'{sys._getframe().f_code.co_name}: Successfully added {monitors_added} monitors, skipped {monitors_skipped} duplicates')
    except IntegrityError as e:
        session.rollback()
        logging.error(f'{sys._getframe().f_code.co_name}: Database integrity error: {e}')
        raise


def initialize_db():
    global session, SERVER_MODE, engine, Session
    DATABASE_NAME = os.environ['POSTGRES_DB']

    db_database = os.environ['POSTGRES_DB']
    db_user = os.environ['POSTGRES_USER']
    db_password = os.environ['POSTGRES_PASSWORD']
    db_ip_address = os.environ['POSTGRES_HOST']
    db_port = os.environ['POSTGRES_PORT']
    SERVER_MODE = os.environ['ENV']
    POSTGRES_CONNECTOR_STRING = f'postgresql+psycopg2://{db_user}:{db_password}@{db_ip_address}:{db_port}/{db_database}'

    engine = db.create_engine(POSTGRES_CONNECTOR_STRING, echo=True)
    Session = sessionmaker(bind=engine)
    session = None
    session = Session()

    # PostgreSQL automatically supports UTF-8 encoding, no special configuration needed
    init_db()
    init_data()


if __name__ == '__main__':
    initialize_db()
