from config import Config
import sqlite3
from sqlite3 import OperationalError
import datetime
import requests


class DB:
    """ handles functionality with data storage """
    password = '24246'
    password_attempt = ''
    db_change = False
    local = Config.local_db

    @staticmethod
    def get_db():
        """ returns the database configuration """
        return {'type': 'server - api' if Config.server else 'local',
                'server': Config.server or '',
                'area': Config.area or '',
                'sequence': Config.sequence or '',
                'sequence_num': Config.sequence_num or '1'
                }

    @staticmethod
    def enter_password(btn):
        """ stores the last 5 buttons pushed on the data tab as a string, checked against a password """
        DB.password_attempt += btn[0]
        if len(DB.password_attempt) > 5:
            DB.password_attempt = DB.password_attempt[-5:]

    @staticmethod
    def set_db(btn):
        """ tells gui to change db configuration """
        DB.db_change = True
        DB.enter_password(btn)

    @staticmethod
    def cycle(mark, cycle_time, sequence, partsper, delivered, code, kpi):
        """ Timer.cycle calls this function in a separate thread, logging data to both local and api databases """
        conn = sqlite3.connect(DB.local)
        c = conn.cursor()
        try:
            data = cycle_time, code, str(datetime.datetime.now())
            c.execute("""INSERT INTO cycle VALUES (?,?,?)""", data)
            print('local database: updated')
            conn.commit()
        except OperationalError:
            conn.execute("""CREATE TABLE cycle
                                (cycle_time int, code int, d text)""")
            DB.cycle(mark, cycle_time, sequence, partsper, delivered, code, kpi)
            print('No local database exists...\ncreating local DB...')
            conn.commit()
        if kpi:
            data = {'id_kpi': kpi['id'],
                    'd': mark,
                    'sequence': sequence,
                    'cycle_time': cycle_time,
                    'parts_per': partsper,
                    'delivered': delivered,
                    'code': code
                    }
            try:
                r = requests.post('https://{}/api/cycles'.format(Config.server), json=data, verify=False)
                print('server database: updated')
                print(r.json())
            except ConnectionError:
                print('server database: Connection Failed')
        else:
            print('server database: No connection has been made to a server database')

    @staticmethod
    def andon(kpi):
        if kpi:
            data = {'id_kpi': kpi['id'],
                    'd': str(datetime.datetime.now()),
                    'sequence': Config.sequence_num,
                    'responded': 0,
                    }
            try:
                r = requests.post('https://{}/api/andon'.format(Config.server), json=data, verify=False)
                print(r.json())
                print('server database: andon logged')
            except ConnectionError:
                print('server database: Connection Failed (for Andon)')
        else:
            print('server database: No connection has been made to a server database')

    @staticmethod
    def andon_response(kpi):
        if kpi:
            data = {'id_kpi': kpi['id'],
                    'sequence': Config.sequence_num,
                    'response_d': str(datetime.datetime.now()),
                    }
            try:
                r = requests.post('https://{}/api/andon/respond'.format(Config.server), json=data, verify=False)
                print(r.json())
                print('server database: andon response logged')
            except ConnectionError:
                print('server database: connection failed (for andon response)')
        else:
            print('server database: No connection has been made to a server database')


