import configparser
import sqlite3

db_config = configparser.ConfigParser()
db_config.read('db.ini')


class Config:
    server = db_config['Settings']['server'] or None
    area = db_config['Settings']['area'] or None
    sequence = db_config['Settings']['sequence'] or None
    sequence_num = db_config['Settings']['sequence_num'] or None
    local_db = 'local.db'
