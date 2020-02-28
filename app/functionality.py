"""
Basic functionality of the timer is very simple:
    1.  What is planned cycle time (PCT)?
    2.  How many parts does this sequence produce per cycle (Partsper)?
            Sequence time is PCT * Partsper
    3.  The timer counts down from the expected sequence time and restarts when the pedal is pushed.
        If the expectation is missed, the timer will continue to count into the negative to show total missed time.
    4.  At the end of the planned 'available time' the timer will automatically stop and display measurables.
        Timer will start again with the new block

Additional functionality:
    **  Andons can be signaled and dismissed visually, and a cumulative count is kept
    **  Stores end-of-shift data in sqlite3 file, displays last 3 shifts on 'History' tab  TODO: not made yet
    **  Live metrics for:
        * Number of cycles ahead/behind
        * Total number of cycles that were late, on target, or early

Functions for the takt timer module are separated into 6 classes:   TODO: Clean up the functions/put in proper class
                                                                    TODO: initialize classes with gui object
PCT:
    Everything related to the planned cycle time
Partsper:
    Everything related to the parts delivered per cycle
Andon:
    Everything related to visually signaling andon, including the operation of the LED
Plan:
    Variables and functions that deal with the scheduled start/stop times and how they operate
Timer:
    The main functionality and counting mechanisms of the timer
DB:
    Everything related to the db connection (both local and api)
"""

# imports
import datetime
import configparser
from app.schedule import Schedule  # see schedule.py for documentation
import os
from config import Config
import sqlite3
from sqlite3 import OperationalError
import requests
from threading import Thread


"""
boolean to determine if we are running on windows or a raspberry pi
functions that should not be ran while testing on Windows will check this variable first (ie shut_down, run_lights)
"""
raspi = os.sys.platform == 'linux'
if raspi:
    from app.lights import Light  # see lights.py for documentation


"""
configparser object to read initialization file (setup.ini)
partsper and pct are stored here so the system will not forget after being restarted
"""
setup = configparser.ConfigParser()
setup.read('setup.ini')


class PCT:
    """pct -> int; number of seconds planned for cycling each part through flow"""
    planned_cycle_time = int(setup['Values']['pct'])
    catch_up_pct = planned_cycle_time

    """ new/adjusted/adjust are read by the gui to determine if/when to write changes """
    new = ''
    adjusted = False
    adjust = False

    @staticmethod
    def sequence_time():
        """ returns PCT * Partsper, the expected sequence cycle time """
        return PCT.planned_cycle_time * Partsper.partsper

    @staticmethod
    def set_pct(btn):
        """ handles buttons related to PCT adjustment """
        if btn == 'OK_PCT':
            PCT.adjust = True
        elif btn == 'Back_PCT':
            PCT.adjusted = True
            PCT.new = '-'
        elif btn == 'Get from server':
            Plan.kpi = Plan.get_kpi()
            if Plan.kpi:
                PCT.planned_cycle_time = Plan.kpi['plan_cycle_time']
        elif btn == 'Log to server':
            DB.adjust_kpi()
        else:
            PCT.adjusted = True
            PCT.new = btn[0]

    @staticmethod
    def catch_up():
        """ launches the subWindow for catch_up functionality"""
        Timer.show_catch_up = True

    @staticmethod
    def cycles_until_caught_up():
        """ returns the number of cycles it will take to catch up if you cycle at catch_up_pct """
        ahead = (Timer.total_block_cycles() * PCT.sequence_time()) - Plan.block_time_elapsed()
        diff = (PCT.catch_up_pct - PCT.planned_cycle_time) * Partsper.partsper
        try:
            return int(ahead / diff)
        except ZeroDivisionError:
            return 'infinite'


class Partsper:
    """partsper -> int; the number of parts this sequence produces in one cycle"""
    partsper = int(setup['Values']['partsper'])

    """ new/adjusted/adjust are read by the gui to determine if/when to write changes """
    new = ''
    adjusted = False
    adjust = False

    @staticmethod
    def set_partsper(btn):
        """ handles button pushes relative to partsper adjustments """
        if btn == 'OK_partsper':
            Partsper.adjust = True
        elif btn == 'Back_partsper':
            Partsper.adjusted = True
            Partsper.new = '-'
        else:
            Partsper.adjusted = True
            Partsper.new = btn[0]


class Andon:
    """ andons -> int; The number of times an operator has signaled an abnormality
        only two buttons interact with the andon system, 'Andon' and 'Respond' """
    andons = 0
    safety = 0
    quality = 0
    delivery = 0
    responded = 0  # used to show how many andons the team leader has already responded to

    @staticmethod
    def andon(btn):
        """ handles the andon buttons ['Safety', 'Quality', 'Delivery', 'Respond'] """
        if btn == 'Andon':  # NO LONGER A VISIBLE BUTTON
            Andon.andons += 1
            t = Thread(target=DB.andon, args=(Plan.kpi,))
            t.start()
        if btn == 'Safety':  # operator signals safety andon
            Andon.safety += 1
            Andon.andons += 1
            t = Thread(target=DB.andon, args=(Plan.kpi, 'Safety',))
            t.start()
        if btn == 'Quality':  # operator signals quality andon
            Andon.quality += 1
            Andon.andons += 1
            t = Thread(target=DB.andon, args=(Plan.kpi, 'Quality',))
            t.start()
        if btn == 'Delivery':
            Andon.delivery += 1
            Andon.andons += 1
            t = Thread(target=DB.andon, args=(Plan.kpi, 'Delivery',))
            t.start()
        if btn == 'Respond':  # team leader responds to andon and resets andon LED
            Andon.responded = Andon.andons
            t = Thread(target=DB.andon_response, args=(Plan.kpi,))
            t.start()
        if btn == 'Changeover':
            Timer.color = 'blue'

    @staticmethod
    def run_lights():
        """ changes light color to red or green """
        if Andon.responded != Andon.andons:
            Light.set_all(1, 0, 0)
        else:
            Light.set_all(0, 0, 1)

    @staticmethod
    def get_andons():
        """ returns the label shown under the andon buttons """
        if Andon.responded != Andon.andons:
            return '%s + %s' % (Andon.responded, Andon.andons - Andon.responded)
        else:
            return Andon.andons


class Timer:
    """ main class for most functionality """
    window = 2                              # the acceptable range (+/-) for 'on target'
    tCycle = 0                              # the main number displaying on the timer
    mark = datetime.datetime.now()          # every cycle resets the mark. Used for calculating tCycle
    color = 'light grey'                    # current bg color of timer
    late = 0                                # number of late cycles this block
    early = 0                               # number of early cycles this block
    on_target = 0                           # number of on_target cycles this block
    total_shift_cycles = 0                  # number of total cycles for the shift
    expected_cycles = 0                     # number of expected cycles so far this block (constantly updating)
    past_10 = ["00:00:00"]                  # a list of the previous ten cycle times
    last_cycle_difference = 0               # difference between when our last cycle happened and when it should have
    update_history = False                  # boolean to avoid constant updating on loop function
    show_catch_up = False                   # boolean for loop function to launch subWindow
    hide_catch_up = True                    # boolean for loop function to hide subWindow
    catch_up_mode = False                   # whether we are currently running in catch_up_mode
    shut_down_timer = 0                     # disables shut down button to prevent accidental presses
    shut_down_count = 0                     # the number of times the button has been pressed (requires 3)
    summary = "Shift:  0/0\nBlock: 0/0"     # displays between shifts/blocks so last block isn't lost
    restart = False                         # restarts timer when necessary

    @staticmethod
    def get_tcycle():
        """ returns the current remaining cycle time """
        if not Timer.catch_up_mode:
            Timer.tCycle = PCT.sequence_time() - int((Plan.now() - Timer.mark).total_seconds())
        else:
            Timer.tCycle = (PCT.catch_up_pct * Partsper.partsper) - int((Plan.now() - Timer.mark).total_seconds())
        return Timer.tCycle

    @staticmethod
    def set_catch_up(btn):
        """ handles 'OK' button push in subWindow when setting PCT.catch_up_pct """
        if btn == 'OK':
            Timer.catch_up_mode = True
            Timer.hide_catch_up = True
        if btn == 'Cancel':
            Timer.catch_up_mode = False
            Timer.hide_catch_up = True

    @staticmethod
    def countdown_format(seconds: int, force_pos_neg_label=False):
        """ takes int (seconds) and returns str (":SS", "MM:SS", or "HH:MM:SS") """
        sign = -1 if seconds < 0 else 1
        seconds = seconds * sign
        sign_label = '-' if sign < 0 else ''
        hours, minutes = divmod(seconds, 3600)
        minutes, seconds = divmod(minutes, 60)
        hour_label = '%sh:%02d' % (hours, minutes)
        minute_label = '%s:%02d' % (minutes, seconds)
        second_label = sign_label + ':%02d' % seconds
        if force_pos_neg_label:
            sign_label = '-' if sign < 0 else '+'
            hour_label = sign_label + hour_label
            minute_label = sign_label + minute_label
            second_label = sign_label + ':%02d' % seconds
        return seconds if hours < 0 else hour_label if hours else minute_label if minutes else second_label

    @staticmethod
    def get_ahead():
        """ returns the number of cycles we are ahead this block (negative if behind) """
        expected = Plan.block_time_elapsed() // (Partsper.partsper * PCT.planned_cycle_time)
        return int(Timer.total_block_cycles() - expected)

    @staticmethod
    def get_last_cycle_difference():
        """ returns the difference in seconds from our last cycle (mark) and the time it should have happened """
        start = Plan.schedule.start[Plan.block - 1]
        seconds_expected = Timer.total_block_cycles() * PCT.planned_cycle_time * Partsper.partsper
        expected_time = start + datetime.timedelta(seconds=seconds_expected)
        return int((expected_time - Timer.mark).total_seconds())

    @staticmethod
    def get_next_pct_increment():
        """ returns a timestamp for the next pct interval """
        start = Plan.schedule.start[Plan.block - 1]
        next_cycle_number = (Plan.block_time_elapsed() // (Partsper.partsper * PCT.planned_cycle_time)) + 1
        interval = next_cycle_number * (Partsper.partsper * PCT.planned_cycle_time)
        timestamp = start + datetime.timedelta(seconds=interval)
        return timestamp

    @staticmethod
    def get_summary():
        """ creates a summary string of shift and block, allows last block to display before next shift starts """
        Timer.summary = 'Shift:  %s/%s\nBlock: %s/%s' % (Timer.total_shift_cycles,
                                                         int(Plan.schedule.available_time() // PCT.sequence_time()),
                                                         Timer.total_block_cycles(),
                                                         int(Plan.block_time // PCT.sequence_time()))
        return Timer.summary

    @staticmethod
    def cycle():
        """ this function is called by pressing the pedal """
        cycle_time = int((Plan.now() - Timer.mark).total_seconds())
        if cycle_time >= 2:
            window = Timer.window * Partsper.partsper
            if Timer.tCycle < 0:
                Timer.late += 1
                code = 2
            elif Timer.tCycle > window:
                Timer.early += 1
                code = 0
            else:
                Timer.on_target += 1
                code = 1
            Timer.past_10.append(Timer.countdown_format(int((Plan.now() - Timer.mark).total_seconds())))
            if len(Timer.past_10) > 10:
                Timer.past_10 = Timer.past_10[1:]
            Timer.mark = Plan.now()
            Timer.update_history = True
            Timer.total_shift_cycles += 1
            Timer.last_cycle_difference = Timer.get_last_cycle_difference()
            if not Plan.kpi:
                Plan.kpi = Plan.get_kpi()
            t = Thread(target=DB.cycle, args=(str(Timer.mark), cycle_time, Config.sequence_num, Partsper.partsper,
                                              Timer.total_shift_cycles, code,  Plan.kpi))
            t.start()

    @staticmethod
    def total_block_cycles():
        """ returns the number of cycles that have happened so far this block """
        return Timer.late + Timer.early + Timer.on_target

    @staticmethod
    def adjust_cycles(btn):
        """ manually modifies the number of cycles that have been recorded """
        exec('Timer.%s += 1' % btn)
        Timer.total_shift_cycles += 1

    @staticmethod
    def screen_color():
        """ changes the Timer.color variable to represent current state """
        window = Timer.window * Partsper.partsper
        if Timer.tCycle > window:
            Timer.color = 'light grey'
        elif 0 <= Timer.tCycle <= window:
            Timer.color = 'yellow'
        else:
            Timer.color = 'red'

    @staticmethod
    def reset():
        """ called with a new shift; resets certain variables """
        Plan.new_shift = False
        Andon.andons = 0
        Andon.responded = 0
        Timer.total_shift_cycles = 0

    @staticmethod
    def shut_down(btn):
        """ a button to shut down the raspi or reset the app so the app never needs to be closed completely """
        if btn == 'Shut Down':
            Timer.shut_down_timer = 50
            Timer.shut_down_count += 1
            if Timer.shut_down_timer and Timer.shut_down_count == 3:
                if raspi:
                    os.system('sudo shutdown now')
                else:
                    print('This would normally shut down a Raspberry Pi. Windows is immune!')
        if btn == 'Restart':
            Timer.restart = True


class Plan:
    """ separate class for items related to the schedule """
    schedule = Schedule()
    shift = schedule.shift_select()
    new_shift = True
    schedule_adjusted = False
    block = 0
    block_time = 0
    total_time = 0
    kpi = None
    set_time = False
    adjust_current_time = ('', '')
    update_time = False
    show_schedule_setter = False
    close_schedule_setter = False
    schedule_setter_data = {'block': '1', 'type': 'start', 'input': '', 'AMPM': ''}
    schedule_setter_message = 'Enter the time for block %s to %s.\nEnter in format (HH:MM)'

    @staticmethod
    def block_remaining_time():
        """ returns the number of seconds remaining in the current block """
        return (Plan.schedule.end[Plan.block-1] - Plan.now()).total_seconds()

    @staticmethod
    def block_time_elapsed():
        """ returns the number of seconds that have already passed in the current block """
        return (Plan.now() - Plan.schedule.start[Plan.block-1]).total_seconds()

    @staticmethod
    def new_block():
        """ resets certain variables that need resetting between blocks """
        start = Plan.schedule.start[Plan.block - 1]
        end = Plan.schedule.end[Plan.block - 1]
        available_time = (end - start).total_seconds()
        Timer.on_target = 0
        Timer.late = 0
        Timer.early = 0
        Timer.expected_cycles = int(available_time // PCT.sequence_time())

    @staticmethod
    def now():
        """ shorthand for the current datetime object """
        return datetime.datetime.now()

    @staticmethod
    def set_current_time(btn):
        if btn not in ['current_time', 'update current time']:
            Plan.adjust_current_time = (btn[0], btn[-1])
        elif btn == 'update current time':
            Plan.update_time = True
        Plan.set_time = True

    @staticmethod
    def write_new_datetime(current_time):
        hour = current_time.hour
        minute = current_time.minute
        if raspi:
            os.system(""" sudo date -s "%02d:%02d:00" """ % (hour, minute))
        else:
            print(""" sudo date -s "%02d:%02d:00" \n""" % (hour, minute))

    @staticmethod
    def schedule_format(time):
        """ takes a datetime object and returns str in the specified format (ex. 01:23 PM)"""
        return datetime.datetime.strftime(time, '%I:%M %p')

    @staticmethod
    def time_format(time=None):
        """ takes a datetime object (or uses current time) and returns specified format (ex. 01:23:45 PM) """
        if not time:
            return datetime.datetime.strftime(Plan.now(), '%I:%M:%S %p')
        else:
            return datetime.datetime.strftime(time, '%I:%M:%S %p')

    @staticmethod
    def write_schedule(app):
        """ puts the current schedule on the gui """
        Plan.total_time = 0
        for block in [1, 2, 3, 4]:
            start = Plan.schedule.start[block - 1]
            end = Plan.schedule.end[block - 1]
            time = int((end-start).total_seconds())
            Plan.total_time += time
            app.setLabel('start%s' % block, Plan.schedule_format(start))
            app.setLabel('end%s' % block, Plan.schedule_format(end))
            app.setLabel('block%sTime' % block, '%s seconds' % time)
        app.setLabel('availableTime', '%s Total Seconds' % Plan.total_time)

    @staticmethod
    def adjust_schedule(btn):
        """ handles the button pushes on the schedule tab """
        shifts = {'Grave':  (23, 7),
                  'Day':    (7, 15),
                  'Swing':  (15, 23)
                  }
        delta = datetime.timedelta(minutes=5)
        time = btn[0]
        direction = btn[-2]
        block = int(btn[-3]) - 1
        if time == 's':
            Plan.schedule.start[block] += delta if direction == 'U' else -delta
            if Plan.schedule.start[block] > Plan.schedule.end[block]:
                Plan.schedule.start[block] = Plan.schedule.end[block]
            if block != 0 and Plan.schedule.start[block] < Plan.schedule.end[block-1]:
                Plan.schedule.start[block] += delta
            if Plan.schedule.start[block].hour < shifts[Plan.shift][0]:
                if Plan.shift != 'Grave':
                    Plan.schedule.start[block] += delta
                elif Plan.schedule.start[block].hour == 22:
                    Plan.schedule.start[block] += delta
        elif time == 'e':
            Plan.schedule.end[block] += delta if direction == 'U' else -delta
            if Plan.schedule.start[block] > Plan.schedule.end[block]:
                Plan.schedule.end[block] = Plan.schedule.start[block]
            if block != 3 and Plan.schedule.end[block] > Plan.schedule.start[block+1]:
                Plan.schedule.end[block] -= delta
            if Plan.schedule.end[block].hour == shifts[Plan.shift][1] and Plan.schedule.end[block].minute > 15:
                if Plan.shift != 'Grave':
                    Plan.schedule.end[block] -= delta
                elif Plan.schedule.end[block].hour == 7 and Plan.schedule.end[block].minute > 15:
                    Plan.schedule.end[block] -= delta
        Plan.schedule_adjusted = True
        Plan.block_time = Plan.schedule.block_time()
        Timer.expected_cycles = int(Plan.block_time // PCT.sequence_time())

    @staticmethod
    def schedule_setter_launcher(btn):
        Plan.show_schedule_setter = True
        Plan.schedule_setter_data = {'block': btn[-1],
                                     'type': btn[:-1],
                                     'input': '',
                                     'AMPM': '',
                                     }
        Plan.schedule_setter_message = 'Enter the time for block %s to %s.\nEnter in format (HH:MM)' % \
                                       (Plan.schedule_setter_data['block'], Plan.schedule_setter_data['type'])
        print(btn)

    @staticmethod
    def schedule_setter(btn):
        if btn[-1] in [str(i) for i in range(10)]:
            Plan.schedule_setter_data['input'] += btn[-1]
            if len(Plan.schedule_setter_data['input']) == 1:
                if int(Plan.schedule_setter_data['input']) > 1:
                    Plan.schedule_setter_data['input'] = '0' + Plan.schedule_setter_data['input']
        elif btn[-1] == 'k':
            Plan.schedule_setter_data['input'] = Plan.schedule_setter_data['input'][:-1]
        elif btn[-1] == 'l':
            Plan.close_schedule_setter = True
        elif btn[-2:] == 'AM':
            Plan.schedule_setter_data['AMPM'] = 'AM'
        elif btn[-2:] == 'PM':
            Plan.schedule_setter_data['AMPM'] = 'PM'

    @staticmethod
    def get_kpi(area=None, shift=None, date=None):
        """ connects to api and looks for a kpi object for current shift """
        if Config.server and raspi:
            if not area:
                area = Config.area
            if not shift:
                shift = Plan.shift
            if not date:
                date = Plan.schedule.kpi_date()
            try:
                r = requests.get('https://{}/api/kpi/{}/{}/{}'.format(Config.server, area, shift, date), verify=False)
                try:
                    if r.status_code == 200:
                        kpi = r.json()
                    else:
                        kpi = None
                except:
                    kpi = None
            except ConnectionError:
                kpi = None
                print('Connection Failed')
            return kpi
        else:
            print('Either no db connection has been set or you are running on Windows.')
            return None

    @staticmethod
    def update_schedule(btn):
        """ updates the default schedule for the current shift, stored in schedules.ini """
        if btn == 'Update Default':
            ini = configparser.ConfigParser()
            ini.read('schedules.ini')
            start = ', '.join([datetime.datetime.strftime(time, '%H%M') for time in Plan.schedule.start])
            end = ', '.join([datetime.datetime.strftime(time, '%H%M') for time in Plan.schedule.end])
            ini[Plan.schedule.shift]['start'] = start
            ini[Plan.schedule.shift]['end'] = end
            with open('schedules.ini', 'w') as configfile:
                ini.write(configfile)
        data = {}
        x = 0
        for start, end in [['start' + str(i), 'end' + str(i)] for i in range(1, 5)]:
            data[start] = Plan.schedule.start[x]
            data[end] = Plan.schedule.end[x]
            x += 1
        data['name'] = 'Regular' if btn == 'Update Default' else 'Custom'
        data['schedule_area'] = Config.area
        data['schedule_shift'] = Plan.shift
        DB.update_schedule(data)


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
    def andon(kpi, andon_type):
        if kpi:
            data = {'id_kpi': kpi['id'],
                    'd': str(datetime.datetime.now()),
                    'andon_type': andon_type,
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

    @staticmethod
    def update_schedule(data):
        try:
            s = requests.post('https://{}/api/schedules/config'.format(Config.server), json=data, verify=False)
            DB.adjust_kpi(schedule=s.json()['name'])
            print(s.json())
        except ConnectionError:
            print('server database: connection failed (for update schedule)')
        except KeyError:
            print('server database: That schedule name doesn\'t exist')

    @staticmethod
    def adjust_kpi(schedule=None):
        Plan.kpi['plan_cycle_time'] = PCT.planned_cycle_time
        if not schedule:
            Plan.kpi['schedule'] = 'Regular'
        else:
            Plan.kpi['schedule'] = schedule
        if Plan.kpi:
            try:
                r = requests.post('https://{}/api/kpi'.format(Config.server), json=Plan.kpi, verify=False)
                print(r.json())
            except ConnectionError:
                print('Connection Failed')


def function(app):
    """ the hitherto functionless app is passed to this function to make it... function """
    """ function """

    def counting():
        """ This function is constantly looping making changes
            Other functions above manipulate the data, but only this function changes what is displayed
        """

        if raspi:
            Andon.run_lights()  # only on raspi adjust the gpio pins

        """ First check is to see if the shift has ended, and reset if so """
        if Plan.now() > Plan.schedule.schedule()[-1]:
            Plan.new_shift = True
            Timer.summary = Timer.get_summary()
            Plan.schedule = Schedule()
            Plan.shift = Plan.schedule.shift_select()

        """ When the new shift happens """
        if Plan.new_shift:
            if Config.server and raspi:
                Plan.kpi = Plan.get_kpi()
            Plan.write_schedule(app)
            Timer.reset()

        """ Next check is to see if a new block has started ("block" being available time between two breaks) """
        if Plan.block != Plan.schedule.get_block():
            Plan.block = Plan.schedule.get_block()
            Plan.block_time = Plan.schedule.block_time()
            Plan.new_block()
            Timer.mark = Plan.now()

        """ Timer.tCycle is the main number displaying on the timer """
        Timer.tCycle = Timer.get_tcycle()

        """ This was a quick way to ensure I only updated this list when a new cycle happened, not constantly """
        if Timer.update_history:
            app.changeOptionBox('past_10', Timer.past_10)
            app.setOptionBox('past_10', Timer.past_10[-1])
            Timer.update_history = False

        """ 
        The following is how the timer acts at different times through the shift.
        These three cases are, respectively:
            (1 - 'if'  ) Before available time has started at the beginning of the shift
            (2 - 'elif') During the available time (the majority of functional usage time)
            (3 - 'else') During breaks
        """
        if Plan.now() < Plan.schedule.start[Plan.block-1]:
            Timer.mark = datetime.datetime.now() - datetime.timedelta(seconds=2)
            label = 'Shift: %s\tDate: %s\n\n\tAvailable Time: %s\n\nPCT: %s\t\tParts per Cycle: %s' % (
                Plan.schedule.shift, datetime.date.today(),
                Plan.schedule.available_time(), PCT.planned_cycle_time, Partsper.partsper)
            app.setLabel('tCycle', label)
            app.getLabelWidget('tCycle').config(font='arial 20')
            app.setLabel('ahead', Timer.summary)
            app.getLabelWidget('ahead').config(font='arial 20')
            Timer.color = 'green'
        elif Plan.now() < Plan.schedule.end[Plan.block-1]:
            app.setLabel('tCycle', Timer.countdown_format(Timer.tCycle))
            app.getLabelWidget('tCycle').config(font='arial 148')
            app.setLabel('next_pct_increment', 'Next: ' + Plan.time_format(Timer.get_next_pct_increment()))
            Timer.screen_color()
            ahead = Timer.get_ahead()
            current_expected = int(Plan.block_time_elapsed() // (Partsper.partsper * PCT.planned_cycle_time))
            if ahead >= 0:
                ahead_label = 'Ahead: %s (%s/%s)' % (ahead, Timer.total_block_cycles(), current_expected)
                Timer.catch_up_mode = False
            else:
                ahead_label = 'Behind: %s (%s/%s)' % (-ahead, Timer.total_block_cycles(), current_expected)
            app.setLabel('ahead', ahead_label)
        else:
            app.setLabel('tCycle', '%s / %s' % (Timer.total_block_cycles(), Timer.expected_cycles))
            app.getLabelWidget('tCycle').config(font='arial 64')
            app.setLabel('ahead', Timer.get_summary())
            app.getLabelWidget('ahead').config(font='arial 20')
            app.setLabel('next_pct_increment', 'Break')
            Timer.color = 'green'

        """ raspi is not particularly great at graphical processes, so only assign a new color if needed """
        if Timer.color != app.getLabelBg('tCycle'):
            app.setLabelBg('tCycle', Timer.color)
            print('color change: %s' % Timer.color)

        """ Constantly update the following labels """
        app.setLabel('current_time', Plan.time_format())
        app.setLabel('last_cycle_difference',
                     'Last Cycle: ' + Timer.countdown_format(Timer.last_cycle_difference, force_pos_neg_label=True))
        app.setLabel('late', 'Late: %s' % Timer.late)
        app.setLabel('early', 'Early: %s' % Timer.early)
        app.setLabel('on_target', 'On Time: %s' % Timer.on_target)
        app.setLabel('andons', Andon.get_andons())
        app.setLabel('PCT', PCT.planned_cycle_time)
        app.setLabel('partsper', Partsper.partsper)

        """ Listen for button presses on the schedule tab """
        if Plan.schedule_adjusted:
            Plan.write_schedule(app)
            Plan.schedule_adjusted = False

        """ Listen for button presses related to PCT changes (Everything except the "OK" button) """
        if PCT.adjusted:
            new_pct = app.getEntry('new_pct')
            if PCT.new == '-':
                new_pct = new_pct[0:-1]
            else:
                new_pct += PCT.new
            if new_pct == '0':
                new_pct = ''
            app.setEntry('new_pct', new_pct)
            PCT.adjusted = False
        """ make the change (the "OK" button for PCT) """
        if PCT.adjust:
            if app.getEntry('new_pct') != '' and 3 <= int(app.getEntry('new_pct')) <= Plan.block_time:
                PCT.planned_cycle_time = int(app.getEntry('new_pct'))
                app.setEntry('new_pct', '')
                available_time = (Plan.schedule.end[Plan.block-1] - Plan.schedule.start[Plan.block-1]).total_seconds()
                Timer.expected_cycles = int(available_time // PCT.sequence_time())
            else:
                app.errorBox('Wrong Value', 'Enter a value between 3 seconds and your current block available time.')
                app.setEntry('new_pct', '')
            PCT.adjust = False
            ini = configparser.ConfigParser()
            ini.read('setup.ini')
            ini['Values']['pct'] = str(PCT.planned_cycle_time)
            with open('setup.ini', 'w') as configfile:
                ini.write(configfile)

        """ Listen for button presses related to Partsper changes (Everything except the "OK" button) """
        if Partsper.adjusted:
            new_partsper = app.getEntry('new_partsper')
            if Partsper.new == '-':
                new_partsper = new_partsper[0:-1]
            else:
                new_partsper += Partsper.new
            if new_partsper == '0':
                new_partsper = ''
            app.setEntry('new_partsper', new_partsper)
            Partsper.adjusted = False
        """ make the change (the "OK" button for Partsper) """
        if Partsper.adjust:
            if app.getEntry('new_partsper') != '' and int(app.getEntry('new_partsper')) <= 72:
                Partsper.partsper = int(app.getEntry('new_partsper'))
                app.setEntry('new_partsper', '')
                available_time = (Plan.schedule.end[Plan.block-1] - Plan.schedule.start[Plan.block-1]).total_seconds()
                Timer.expected_cycles = int(available_time // PCT.sequence_time())
            else:
                app.errorBox('Wrong Value', 'Enter a value between 1 and 72.')
                app.setEntry('new_partsper', '')
            Partsper.adjust = False
            ini = configparser.ConfigParser()
            ini.read('setup.ini')
            ini['Values']['partsper'] = str(Partsper.partsper)
            with open('setup.ini', 'w') as configfile:
                ini.write(configfile)

        """ Everything related to the "Catch Up" functionality, where PCT is temporarily changed """
        PCT.catch_up_pct = app.getScale('catch_up_scale')
        app.setScaleRange('catch_up_scale', int(PCT.planned_cycle_time * .6), PCT.planned_cycle_time,
                          curr=PCT.catch_up_pct)
        app.setScaleIncrement('catch_up_scale', 1)
        app.setLabel('cycles_until_caught_up', '%s sec/part will catch\n  you up in %s cycles' %
                     (PCT.catch_up_pct, PCT.cycles_until_caught_up()))
        if Timer.show_catch_up:
            app.setScale('catch_up_scale', PCT.planned_cycle_time)
            app.showSubWindow('Catch Up?')
            Timer.show_catch_up = False
        if Timer.hide_catch_up:
            app.hideSubWindow('Catch Up?')
            Timer.hide_catch_up = False
        if Timer.catch_up_mode:
            app.setStatusbar('Catch Up Mode - PCT %s * %s part(s)' % (PCT.catch_up_pct, Partsper.partsper), 0)
        else:
            app.setStatusbar('PCT %s * %s part(s) = %s' %
                             (PCT.planned_cycle_time, Partsper.partsper, Timer.countdown_format(PCT.sequence_time())),
                             0)
        app.setStatusbar('Block Cycles: %s/%s' % (Timer.total_block_cycles(),
                                                  int(Plan.block_time // PCT.sequence_time())),
                         1)
        app.setStatusbar('Shift Cycles: %s/%s' % (Timer.total_shift_cycles,
                                                  int(Plan.schedule.available_time() // PCT.sequence_time())),
                         2)

        """ "Schedule Setter" functionality """
        if Plan.show_schedule_setter:
            app.showSubWindow('Schedule Setter')
            Plan.show_schedule_setter = False
            app.setMessage('schedule_setter_message', Plan.schedule_setter_message)
        if Plan.close_schedule_setter:
            app.hideSubWindow('Schedule Setter')
            Plan.close_schedule_setter = False

        app.setEntry('schedule_setter_hour', Plan.schedule_setter_data['input'][:2])
        if len(Plan.schedule_setter_data['input']) > 2:
            app.setEntry('schedule_setter_minute', Plan.schedule_setter_data['input'][2:])
        else:
            app.setEntry('schedule_setter_minute', '')
        if len(Plan.schedule_setter_data['input']) == 4:
            if int(Plan.schedule_setter_data['input']) >= 60:
                Plan.schedule_setter_data['input'] = ''
                app.errorBox('Incorrect Minute', 'Minute value must be between 0-59')
            Plan.close_schedule_setter = True
            Plan.schedule_setter_data['input'] = ''


        """ handles the shut down button; helps prevent accidental shut down """
        if Timer.shut_down_timer:
            Timer.shut_down_timer -= 1
            if Timer.shut_down_count == 1:
                app.setButton('Shut Down', 'Are you sure? %s' % Timer.shut_down_timer)
            elif Timer.shut_down_count == 2:
                app.setButton('Shut Down', "Do it again, you won't... %s" % Timer.shut_down_timer)
            if Timer.shut_down_timer == 0:
                app.setButton('Shut Down', 'Shut Down')
                Timer.shut_down_count = 0

        """ checks for password entry and disables/enables entries on data tab """
        if DB.password_attempt == DB.password:
            app.enableOptionBox('db_type')
            if app.getOptionBox('db_type') == 'server - api':
                app.enableEntry('db_server')
                app.enableEntry('db_area')
                app.enableEntry('db_sequence')
                app.enableOptionBox('db_sequence_num')
                for label in ['type', 'server', 'area', 'sequence', 'sequence_num']:
                    app.enableLabel('db_' + label)
            else:
                app.disableEntry('db_server')
                app.disableEntry('db_area')
                app.disableEntry('db_sequence')
                app.disableOptionBox('db_sequence_num')
                for label in ['server', 'area', 'sequence', 'sequence_num']:
                    app.disableLabel('db_' + label)
            app.enableButton('submit')
        else:
            app.disableOptionBox('db_type')
            app.disableEntry('db_server')
            app.disableEntry('db_area')
            app.disableEntry('db_sequence')
            app.disableOptionBox('db_sequence_num')
            for label in ['type', 'server', 'area', 'sequence', 'sequence_num']:
                app.disableLabel('db_' + label)
            app.disableButton('submit')

        """ changes db settings when submitted """
        if DB.db_change:
            server_check = app.getOptionBox('db_type') == 'server - api'
            server = app.getEntry('db_server') if server_check else ''
            area = app.getEntry('db_area') if server_check else ''
            sequence = app.getEntry('db_sequence') if server_check else ''
            sequence_num = app.getOptionBox('db_sequence_num') if server_check else '1'
            db_setting = configparser.ConfigParser()
            db_setting.read('db.ini')
            db_setting['Settings']['server'] = server
            db_setting['Settings']['area'] = area
            db_setting['Settings']['sequence'] = sequence
            db_setting['Settings']['sequence_num'] = sequence_num
            Config.server = server
            Config.area = area
            Config.sequence = sequence
            Config.sequence_num = sequence_num
            with open('db.ini', 'w') as db_setup:
                db_setting.write(db_setup)
            DB.db_change = False
            app.setEntry('db_server', server)
            app.setEntry('db_area', area)
            app.setEntry('db_sequence', sequence)
            app.setOptionBox('db_sequence_num', sequence_num)

        """ restarts timer when necessary changes need made (DB) """
        if Timer.restart:
            print('restarting app')
            app.stop()
            if raspi:
                os.system('cd /home/pi/TaktTimer')
                os.system('python3 main.py')
            else:
                os.system('python main.py')

        """ launches window to set the time (workaround for not having an RTC/internet) """
        if Plan.set_time:
            if Plan.adjust_current_time[0]:
                label = 'current_hour' if Plan.adjust_current_time[0] == 'h' else 'current_minute'
                hour = label == 'current_hour'
                time = int(app.getLabel(label))
                time += (1 if Plan.adjust_current_time[1] == 'p' else -1)
                if hour:
                    time -= 12 if time > 12 else 0
                    time += 12 if time < 1 else 0
                else:
                    time -= 60 if time > 59 else 0
                    time += 60 if time < 0 else 0
                app.setLabel(label, time)
                Plan.adjust_current_time = ('', '')
            else:
                if not Plan.update_time:
                    hour = Plan.now().hour if Plan.now().hour <= 12 else Plan.now().hour - 12
                    hour += (12 if hour == 0 else 0)
                    app.setLabel('current_hour', hour)
                    app.setLabel('current_minute', Plan.now().minute)
                    app.showSubWindow('Time Setter')
            Plan.set_time = False
            if Plan.update_time:
                hour = int(app.getLabel('current_hour'))
                minute = int(app.getLabel('current_minute'))
                am_pm = app.getRadioButton('am_pm')
                hour += 12 if am_pm == 'PM' and hour != 12 else 0
                hour = 0 if (hour == 12 and am_pm == 'AM') else hour
                current_time = datetime.time(hour, minute)
                app.stop()
                t = Thread(target=Plan.write_new_datetime, args=(current_time,))
                t.start()
                if raspi:
                    print('updating time to %02d:%02d' % (hour, minute))
                    os.system('cd /home/pi/TaktTimer')
                    os.system('python3 main.py')
                else:
                    print('new time would be %02d:%02d\n' % (hour, minute))
                    os.system('python main.py')

    app.registerEvent(counting)  # make the "counting" function loop continuously
    app.setPollTime(50)  # the time in milliseconds between each loop of the "counting" function (roughly)
    app.bindKey('<space>', Timer.cycle)
    app.bindKey('1', Timer.cycle)
    return app
