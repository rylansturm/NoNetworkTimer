import configparser

db_config = configparser.ConfigParser()
db_config.read('db.ini')


class Config:
    server = db_config['Settings']['server'] or None
